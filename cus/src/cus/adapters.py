"""Install adapters for non-package module kinds (M1).

Stdlib only. Adapters are data-driven: data/modules.json carries the
adapter parameters (npm package, installer URL + pinned sha256, fnm
release, backup defaults); this module only implements the mechanics.
Nothing here runs on import. Every adapter is idempotent (re-running a
satisfied module is a no-op) and verifies its own result.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
import shlex
import shutil
import socket
import subprocess
import sys
import urllib.request
import zipfile
from pathlib import Path


# ------------------------------------------------------------ environment --
class AdapterEnv:
    """Everything an adapter touches, injectable for tests.

    home: user home (all adapter paths derive from it).
    host: runtime.detect() dict.
    use_sudo: prefix privileged steps with sudo (only when the adapter
        declares needs_root and the host is not root).
    runner: (argv, **kw) -> object with .returncode/.stdout/.stderr.
        Defaults to subprocess.run. Tests inject a recorder.
    which: executable lookup (default shutil.which).
    connect: TCP connect used by the firewall verifier
        (default socket.create_connection).
    log: progress output (default print).
    """

    def __init__(self, home=None, host=None, use_sudo=False,
                 runner=None, which=None, connect=None, log=None):
        self.home = Path(home) if home is not None else Path.home()
        self.host = host or {}
        self.use_sudo = use_sudo
        self.runner = runner or subprocess.run
        self.which = which or shutil.which
        self.connect = connect or socket.create_connection
        self.log = log or print

    @property
    def cache_dir(self) -> Path:
        return self.home / ".cache" / "commonuserscripts"

    @property
    def config_dir(self) -> Path:
        return self.home / ".config" / "commonuserscripts"

    @property
    def local_bin(self) -> Path:
        return self.home / ".local" / "bin"

    @property
    def fnm_dir(self) -> Path:
        return self.home / ".local" / "share" / "fnm"

    def run(self, argv, **kw):
        return self.runner([str(a) for a in argv], **kw)

    def priv(self, argv):
        """Prefix sudo when this env runs privileged steps unprivileged."""
        argv = [str(a) for a in argv]
        return (["sudo"] + argv) if self.use_sudo else argv


def default_env(host: dict, use_sudo: bool = False) -> AdapterEnv:
    return AdapterEnv(home=Path.home(), host=host, use_sudo=use_sudo)


# ---------------------------------------------------------------- helpers --
def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def download(url: str, dest: Path, timeout: int = 120) -> Path:
    """Download url to dest with urllib (no curl dependency)."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(
        url, headers={"User-Agent": "CommonUserScripts/2.1"})
    with urllib.request.urlopen(req, timeout=timeout) as resp, \
            dest.open("wb") as f:
        shutil.copyfileobj(resp, f)
    return dest


def download_verified(url: str, dest: Path, expected_sha256: str,
                      log=print) -> bool:
    """Download + sha256 check. On mismatch the file is deleted and
    False is returned; the caller must never execute it."""
    download(url, dest)
    actual = sha256_file(dest)
    if actual.lower() != expected_sha256.lower():
        log(f"Checksum mismatch for {url}: expected "
            f"{expected_sha256[:12]}..., got {actual[:12]}...; "
            "refusing to execute.")
        try:
            dest.unlink()
        except OSError:
            pass
        return False
    return True


def version_tuple(text: str) -> tuple:
    m = re.search(r"(\d+)(?:\.(\d+))?(?:\.(\d+))?", text or "")
    if not m:
        return ()
    return tuple(int(g) for g in m.groups() if g is not None)


def node_env(home: Path, which) -> dict:
    """Resolve node/npm/npx/fnm. fnm-managed Node wins, then PATH.

    Returns {"node", "npm", "npx", "fnm", "node_version", "path_dirs"}.
    node_version comes from the fnm directory name when available.
    """
    out = {"node": None, "npm": None, "npx": None, "fnm": None,
           "node_version": (), "path_dirs": []}
    fnm_bin = Path(home) / ".local" / "share" / "fnm" / "fnm"
    if fnm_bin.exists():
        out["fnm"] = fnm_bin
    versions_dir = Path(home) / ".local" / "share" / "fnm" / "node-versions"
    best = None
    if versions_dir.is_dir():
        for entry in versions_dir.iterdir():
            # Real fnm layout: <version>/installation/bin/node
            # (older hand-made layouts used <version>/bin/node directly).
            node = entry / "installation" / "bin" / "node"
            if not node.exists():
                node = entry / "bin" / "node"
            if node.exists():
                ver = version_tuple(entry.name)
                if ver and (best is None or ver > best[0]):
                    best = (ver, node.parent)
    if best is not None:
        out["node_version"] = best[0]
        out["path_dirs"].append(str(best[1]))
        for name in ("node", "npm", "npx"):
            p = best[1] / name
            if p.exists():
                out[name] = p
    for name in ("node", "npm", "npx"):
        if out[name] is None:
            found = which(name)
            if found:
                out[name] = Path(found)
    return out


def node_version(node_path, runner) -> tuple:
    """Run `node --version` and parse it. () when it cannot run."""
    try:
        r = runner([str(node_path), "--version"],
                   capture_output=True, text=True, timeout=15)
        if r.returncode == 0:
            return version_tuple(r.stdout or "")
    except (OSError, subprocess.SubprocessError):
        pass
    return ()


def run_verify(argv, env: AdapterEnv, extra_path=(), timeout: int = 30) -> tuple:
    """Run a --version style check. Returns (ok, first output line).

    timeout is a bound against hangs, not an SLA: first runs of big
    Node CLIs (gemini --version, npx downloads) are slow on small
    machines, so npm/npx verifications pass a longer timeout.
    """
    path = os.environ.get("PATH", "")
    if extra_path:
        path = os.pathsep.join([*extra_path, path])
    try:
        r = env.run(argv, capture_output=True, text=True, timeout=timeout,
                    env={**os.environ, "PATH": path})
    except subprocess.TimeoutExpired:
        return False, f"timed out after {timeout}s"
    except (OSError, subprocess.SubprocessError):
        return False, ""
    out = ((r.stdout or "") + "\n" + (r.stderr or "")).strip().splitlines()
    return r.returncode == 0, out[0].strip() if out else ""


def path_env(env: AdapterEnv, extra_dirs) -> dict:
    """os.environ with extra dirs prepended to PATH."""
    path = os.environ.get("PATH", "")
    if extra_dirs:
        path = os.pathsep.join([*extra_dirs, path])
    return {**os.environ, "PATH": path}


# ---------------------------------------------------------------- registry --
class Adapter:
    kind = ""
    needs_root = False

    def ready(self, module, host, env) -> tuple:
        """(status, reason). status is the catalog vocabulary:
        "available" or "unsupported". reason doubles as the plan detail."""
        raise NotImplementedError

    def commands(self, module, host, env) -> list:
        """Planned argv steps, for display in plan output."""
        raise NotImplementedError

    def run(self, module, host, env) -> tuple:
        """Execute. Returns (exit code, one-line summary)."""
        raise NotImplementedError


ADAPTERS: dict = {}


def register(adapter: Adapter) -> Adapter:
    ADAPTERS[adapter.kind] = adapter
    return adapter


def get_adapter(kind: str):
    return ADAPTERS.get(kind)


# -------------------------------------------------------------------- npm --
class NpmAdapter(Adapter):
    kind = "npm"

    def _node(self, env):
        return node_env(env.home, env.which)

    def _verify(self, module):
        return [str(v) for v in
                (module.get("verify", {}).get("command")
                 or [module["detect"][0], "--version"])]

    def ready(self, module, host, env):
        ne = self._node(env)
        if ne["node"] is None or ne["npm"] is None:
            return "unsupported", "node/npm not found; install dev-node first"
        ver = ".".join(map(str, ne["node_version"])) or "unknown"
        return "available", (f"npm install -g {module.get('npm_package')} "
                      f"(node {ver})")

    def commands(self, module, host, env):
        ne = self._node(env)
        npm = str(ne["npm"]) if ne["npm"] else "npm"
        return [[npm, "install", "-g", module["npm_package"]],
                self._verify(module)]

    def run(self, module, host, env):
        pkg = module["npm_package"]
        verify = self._verify(module)
        ne = self._node(env)
        if ne["node"] is None or ne["npm"] is None:
            return 2, "BLOCKED: node/npm not found; install dev-node first."
        extra = list(ne["path_dirs"]) + [str(env.local_bin)]
        ok, line = run_verify(verify, env, extra, timeout=120)
        if ok:
            return 0, f"SKIPPED: {verify[0]} already installed ({line})."
        env.log(f"Installing {pkg} with npm (global, user level)...")
        r = env.run([str(ne["npm"]), "install", "-g", pkg],
                    env=path_env(env, extra))
        if r.returncode != 0:
            return r.returncode or 1, \
                f"FAILED: npm install -g {pkg} exited {r.returncode}."
        ok, line = run_verify(verify, env, extra, timeout=120)
        if not ok:
            return 1, (f"FAILED: npm exited 0 but {verify[0]} --version "
                       "does not run.")
        return 0, f"Installed {pkg}; {line}."


register(NpmAdapter())


# -------------------------------------------------------------------- npx --
class NpxAdapter(Adapter):
    kind = "npx"

    def ready(self, module, host, env):
        ne = node_env(env.home, env.which)
        if ne["npx"] is None:
            return "unsupported", "npx not found; install dev-node first"
        return "available", (f"run {module.get('npx_package')} via npx "
                      "(no global install)")

    def commands(self, module, host, env):
        ne = node_env(env.home, env.which)
        npx = str(ne["npx"]) if ne["npx"] else "npx"
        return [[npx, "-y", module["npx_package"], "--version"]]

    def run(self, module, host, env):
        pkg = module["npx_package"]
        ne = node_env(env.home, env.which)
        if ne["npx"] is None:
            return 2, "BLOCKED: npx not found; install dev-node first."
        extra = list(ne["path_dirs"]) + [str(env.local_bin)]
        env.log(f"Verifying {pkg} runs via npx (downloads on first run)...")
        ok, line = run_verify([str(ne["npx"]), "-y", pkg, "--version"],
                              env, extra, timeout=300)
        if not ok:
            return 1, f"FAILED: npx -y {pkg} --version did not run."
        return 0, f"{pkg} runs via npx ({line}); no global install needed."


register(NpxAdapter())


# -------------------------------------------------------------- installer --
class InstallerAdapter(Adapter):
    """Official installer scripts: download, verify sha256, then run.

    The installer is never executed when the checksum does not match
    the pinned value in data/modules.json. No curl|bash piping: the
    script is downloaded to the cache first, verified, then run.
    """
    kind = "installer"

    def _spec(self, module):
        return module.get("installer", {}) or {}

    def _cache_file(self, module, env):
        return env.cache_dir / "installers" / f"{module['id']}-install.sh"

    def _verify(self, module):
        return [str(v) for v in
                (module.get("verify", {}).get("command")
                 or [module["detect"][0], "--version"])]

    def ready(self, module, host, env):
        spec = self._spec(module)
        if not spec.get("url") or not spec.get("sha256"):
            return "unsupported", "no pinned installer (url/sha256) for this module"
        if env.which("bash") is None:
            return "unsupported", "bash not found; installer needs bash"
        return "available", (f"download {spec['url']}, verify sha256 "
                      f"{spec['sha256'][:12]}..., run with bash")

    def commands(self, module, host, env):
        return [["bash", str(self._cache_file(module, env))],
                self._verify(module)]

    def run(self, module, host, env):
        spec = self._spec(module)
        verify = self._verify(module)
        extra = [str(env.local_bin), str(env.home / ".grok" / "bin")]
        ok, line = run_verify(verify, env, extra)
        if ok:
            return 0, f"SKIPPED: {verify[0]} already installed ({line})."
        dest = self._cache_file(module, env)
        env.log(f"Downloading installer for {module['id']}...")
        try:
            good = download_verified(spec["url"], dest, spec["sha256"],
                                     log=env.log)
        except (OSError, ValueError):
            return 2, "BLOCKED: installer download failed."
        if not good:
            return 2, ("BLOCKED: installer checksum mismatch; "
                       "refusing to execute.")
        dest.chmod(0o700)
        ienv = path_env(env, extra)
        for key, val in (spec.get("env") or {}).items():
            ienv[key] = str(val).replace("~", str(env.home))
        env.log(f"Running installer for {module['id']} (sha256 verified)...")
        r = env.run(["bash", str(dest)], env=ienv)
        if r.returncode != 0:
            return r.returncode or 1, \
                f"FAILED: installer exited {r.returncode}."
        ok, line = run_verify(verify, env, extra)
        if not ok:
            return 1, (f"FAILED: installer exited 0 but {verify[0]} "
                       "--version does not run.")
        return 0, f"Installed {verify[0]} ({line})."


register(InstallerAdapter())


# -------------------------------------------------------------------- fnm --
class FnmAdapter(Adapter):
    """Node.js via fnm (release binary + Node LTS), NodeSource fallback.

    Primary path is user-level: the fnm binary goes to
    ~/.local/share/fnm, Node LTS is installed with `fnm install --lts`,
    and the shell snippet is appended to ~/.bashrc idempotently.
    The NodeSource fallback needs apt + root/sudo and is only used when
    the fnm path fails.
    """
    kind = "fnm"
    NODE_MIN = (20, 0, 0)

    def _asset(self, module, host):
        arch = (host.get("arch") or "").lower()
        key = None
        if arch in ("x86_64", "amd64"):
            key = "x86_64"
        elif arch in ("aarch64", "arm64"):
            key = "aarch64"
        assets = (module.get("fnm") or {}).get("assets", {}) or {}
        return key, assets.get(key or "")

    def ready(self, module, host, env):
        key, asset = self._asset(module, host)
        if host.get("system") not in ("linux", "darwin") or not asset:
            return "unsupported", "no pinned fnm release for this OS/arch"
        ver = (module.get("fnm") or {}).get("version", "?")
        return "available", (f"download fnm {ver}, verify sha256, "
                      "install Node LTS")

    def commands(self, module, host, env):
        fnm = str(env.fnm_dir / "fnm")
        return [[fnm, "install", "--lts"], ["node", "--version"]]

    def _ensure_shell_snippet(self, env) -> bool:
        line = 'eval "$(fnm env --use-on-cd --shell bash)"'
        rc = env.home / ".bashrc"
        try:
            text = rc.read_text(encoding="utf-8") if rc.exists() else ""
        except OSError:
            return False
        if "fnm env" in text:
            return False
        try:
            with rc.open("a", encoding="utf-8") as f:
                if text and not text.endswith("\n"):
                    f.write("\n")
                f.write(f"\n# Added by CommonUserScripts (fnm)\n{line}\n")
            return True
        except OSError:
            return False

    def _nodesource_fallback(self, module, host, env, reason):
        """Add the NodeSource apt repo and install nodejs (apt only)."""
        if host.get("manager") != "apt":
            return 2, (f"BLOCKED: {reason}; NodeSource fallback "
                       "needs apt.")
        if not (host.get("is_root") or host.get("has_sudo")):
            return 2, (f"BLOCKED: {reason}; NodeSource fallback "
                       "needs root/sudo.")
        if env.which("gpg") is None:
            return 2, (f"BLOCKED: {reason}; NodeSource fallback "
                       "needs gpg to verify the repo key.")
        major = str((module.get("nodesource") or {}).get("node_major", "22"))
        key_url = "https://deb.nodesource.com/gpgkey/nodesource-repo.gpg.key"
        keyring = Path("/etc/apt/keyrings/nodesource.gpg")
        env.log(f"fnm path failed ({reason}); falling back to "
                f"NodeSource node_{major}.x (apt)...")
        try:
            key_file = env.cache_dir / "installers" / "nodesource-repo.gpg.key"
            download(key_url, key_file)
            key_bytes = key_file.read_bytes()
        except (OSError, ValueError):
            return 2, "BLOCKED: NodeSource key download failed."
        r = env.run(env.priv(["mkdir", "-p", "/etc/apt/keyrings"]),
                    capture_output=True, text=True)
        if r.returncode != 0:
            return 2, "BLOCKED: cannot create /etc/apt/keyrings."
        r = env.run(env.priv(["gpg", "--dearmor", "-o", str(keyring)]),
                    input=key_bytes, capture_output=True)
        if r.returncode != 0:
            return 2, "BLOCKED: NodeSource key verification failed."
        repo_line = (f"deb [signed-by={keyring}] "
                     f"https://deb.nodesource.com/node_{major}.x "
                     "nodistro main\n")
        r = env.run(env.priv(["tee", "/etc/apt/sources.list.d/nodesource.list"]),
                    input=repo_line.encode(), capture_output=True)
        if r.returncode != 0:
            return 2, "BLOCKED: cannot write NodeSource repo file."
        for argv in (["apt-get", "update"],
                     ["apt-get", "install", "-y", "nodejs"]):
            r = env.run(env.priv(argv))
            if r.returncode != 0:
                return 2, (f"BLOCKED: NodeSource fallback failed at "
                           f"{' '.join(argv)}.")
        ne = node_env(env.home, env.which)
        if ne["node"] is None:
            return 1, "FAILED: NodeSource installed nodejs but node is missing."
        ver = node_version(ne["node"], env.runner)
        if ver < self.NODE_MIN:
            return 1, (f"FAILED: NodeSource node {ver} is below minimum "
                       f"{self.NODE_MIN}.")
        return 0, (f"Installed Node {'.'.join(map(str, ver))} via "
                   f"NodeSource (fallback).")

    def run(self, module, host, env):
        ne = node_env(env.home, env.which)
        if ne["node"] is not None:
            ver = node_version(ne["node"], env.runner)
            if ver >= self.NODE_MIN:
                return 0, (f"SKIPPED: node {'.'.join(map(str, ver))} "
                           "already available.")
        key, asset = self._asset(module, host)
        if not asset:
            return 2, "BLOCKED: no pinned fnm release for this OS/arch."
        fnm_path = env.fnm_dir / "fnm"
        if not fnm_path.exists():
            ver = (module.get("fnm") or {}).get("version", "?")
            zpath = (env.cache_dir / "installers"
                     / f"fnm-{ver}-{key}.zip")
            env.log(f"Downloading fnm {ver} ({key})...")
            try:
                good = download_verified(asset["url"], zpath,
                                         asset["sha256"], log=env.log)
            except (OSError, ValueError):
                return self._nodesource_fallback(
                    module, host, env, "fnm download failed")
            if not good:
                return self._nodesource_fallback(
                    module, host, env, "fnm checksum mismatch")
            try:
                env.fnm_dir.mkdir(parents=True, exist_ok=True)
                with zipfile.ZipFile(zpath) as zf:
                    zf.extract("fnm", env.fnm_dir)
                fnm_path.chmod(0o755)
            except (OSError, zipfile.BadZipFile) as e:
                return self._nodesource_fallback(
                    module, host, env, f"fnm extract failed ({e})")
        env.log("Installing Node LTS with fnm...")
        fenv = {**os.environ, "FNM_DIR": str(env.fnm_dir),
                "PATH": os.pathsep.join([str(env.fnm_dir),
                                         os.environ.get("PATH", "")])}
        r = env.run([str(fnm_path), "install", "--lts"], env=fenv)
        if r.returncode != 0:
            return self._nodesource_fallback(
                module, host, env, "fnm install --lts failed")
        versions_dir = env.fnm_dir / "node-versions"
        installed = sorted(
            (d.name for d in versions_dir.iterdir() if d.is_dir()),
            key=version_tuple) if versions_dir.is_dir() else []
        if installed:
            env.run([str(fnm_path), "default", installed[-1]], env=fenv)
        if self._ensure_shell_snippet(env):
            env.log("Added fnm shell snippet to ~/.bashrc.")
        ne = node_env(env.home, env.which)
        if ne["node"] is None:
            return 1, "FAILED: fnm installed Node but node is not resolvable."
        ver = node_version(ne["node"], env.runner)
        if ver < self.NODE_MIN:
            # Surface the real reason (e.g. a missing shared library)
            # instead of only reporting the unparsed version.
            detail = ""
            try:
                r = env.run([str(ne["node"]), "--version"],
                            capture_output=True, text=True, timeout=15)
                err = ((r.stderr or "").strip().splitlines() or [""])[0]
                if err:
                    detail = f" ({err})"
            except (OSError, subprocess.SubprocessError):
                pass
            return 1, (f"FAILED: installed node {ver} is below minimum "
                       f"{self.NODE_MIN}.{detail}")
        return 0, (f"Installed Node {'.'.join(map(str, ver))} "
                   "via fnm (LTS).")


register(FnmAdapter())


# -------------------------------------------------------------- firewall --
class FirewallAdapter(Adapter):
    """Firewall setup with a safety order: never drop the current SSH
    session.

    Backend preference: ufw, then firewalld, then iptables.
    At plan time only the backend *binary* is checked. At run time the
    order is: read the SSH port from sshd_config (default 22) -> add
    an allow rule for that port -> verify a fresh TCP connection to
    it -> then enable the firewall / set the default-deny policy ->
    re-verify the connection. The firewall is never enabled before a
    fresh connection proves the allow rule works, and the current
    ESTABLISHED session is never dropped (INPUT DROP without a
    verified ESTABLISHED rule is refused).
    IPv6 is out of scope.
    """
    kind = "service"
    BACKENDS = ("ufw", "firewalld", "iptables")

    def _backend(self, env):
        for name in self.BACKENDS:
            if env.which(name) is not None:
                return name
        return None

    def _ssh_port(self, env) -> int:
        for cand in (Path("/etc/ssh/sshd_config"),
                     env.home / ".ssh" / "sshd_config"):
            try:
                for line in cand.read_text(
                        encoding="utf-8", errors="replace").splitlines():
                    s = line.strip()
                    if s.lower().startswith("port "):
                        return int(s.split()[1])
            except (OSError, ValueError, IndexError):
                continue
        return 22

    def _tcp_ok(self, env, port: int) -> bool:
        try:
            with env.connect(("127.0.0.1", port), timeout=5):
                return True
        except OSError:
            return False

    def _established_rule_ok(self, env) -> bool:
        """iptables: does INPUT accept ESTABLISHED/RELATED traffic?"""
        r = env.run(env.priv(
            ["iptables", "-C", "INPUT", "-m", "conntrack", "--ctstate",
             "RELATED,ESTABLISHED", "-j", "ACCEPT"]),
            capture_output=True)
        if r.returncode == 0:
            return True
        if r.returncode == 1:  # rule missing, or match unsupported
            env.log("iptables conntrack match unavailable or rule missing; "
                    "checking for state match...")
            r = env.run(env.priv(
                ["iptables", "-C", "INPUT", "-m", "state", "--state",
                 "RELATED,ESTABLISHED", "-j", "ACCEPT"]),
                capture_output=True)
            return r.returncode == 0
        return False  # other error: match not supported -> refuse

    def ready(self, module, host, env):
        if not (host.get("is_root") or host.get("has_sudo")):
            return "unsupported", "firewall setup needs root/sudo"
        backend = self._backend(env)
        if backend is None:
            return "unsupported", "no firewall backend (ufw/firewalld/iptables)"
        return "available", (f"backend {backend}; allow SSH "
                      f"{self._ssh_port(env)}, verify, then enable")

    def commands(self, module, host, env):
        backend = self._backend(env) or "ufw"
        port = self._ssh_port(env)
        if backend == "ufw":
            return [["ufw", "allow", f"{port}/tcp"],
                    ["ufw", "status"], ["ufw", "enable"]]
        if backend == "firewalld":
            return [["firewall-cmd", "--permanent", "--add-service=ssh"],
                    ["firewall-cmd", "--reload"]]
        return [["iptables", "-A", "INPUT", "-p", "tcp", "--dport",
                 str(port), "-j", "ACCEPT"],
                ["iptables", "-L", "INPUT"]]

    def run(self, module, host, env):
        if not (host.get("is_root") or host.get("has_sudo")):
            return 2, "BLOCKED: firewall setup needs root/sudo."
        backend = self._backend(env)
        if backend is None:
            return 2, ("BLOCKED: no firewall backend found "
                       "(ufw/firewalld/iptables).")
        port = self._ssh_port(env)
        if not self._tcp_ok(env, port):
            return 2, (f"BLOCKED: cannot connect to local SSH port {port}; "
                       "refusing to touch the firewall without a live "
                       "SSH service to protect.")
        if backend == "ufw":
            steps = ([["ufw", "allow", f"{port}/tcp"],
                      ["ufw", "--force", "enable"]])
        elif backend == "firewalld":
            steps = ([["firewall-cmd", "--permanent",
                       "--add-service=ssh"],
                      ["firewall-cmd", "--reload"]])
        else:
            if not self._established_rule_ok(env):
                return 2, ("BLOCKED: iptables has no verified "
                           "ESTABLISHED/RELATED accept rule and the "
                           "conntrack/state match is unavailable; "
                           "refusing to set a default-deny policy.")
            steps = ([["iptables", "-A", "INPUT", "-p", "tcp",
                       "--dport", str(port), "-m", "conntrack",
                       "--ctstate", "NEW", "-j", "ACCEPT"],
                      ["iptables", "-P", "INPUT", "DROP"]])
        for argv in steps[:-1]:
            r = env.run(env.priv(argv))
            if r.returncode != 0:
                return 1, f"FAILED: {' '.join(argv)} exited {r.returncode}."
            if not self._tcp_ok(env, port):
                return 1, (f"FAILED: after {' '.join(argv)} the local SSH "
                           f"port {port} no longer accepts connections; "
                           "stopping before enabling the firewall.")
        r = env.run(env.priv(steps[-1]))
        if r.returncode != 0:
            return 1, (f"FAILED: {' '.join(steps[-1])} exited "
                       f"{r.returncode}.")
        if not self._tcp_ok(env, port):
            return 1, (f"FAILED: firewall enabled but SSH port {port} "
                       "no longer accepts connections; investigate "
                       "before proceeding.")
        return 0, (f"Firewall enabled via {backend}; SSH port {port} "
                   "verified reachable after enable.")


register(FirewallAdapter())


# ----------------------------------------------------------------- backup --
class BackupAdapter(Adapter):
    """restic-based backup: config, encrypted repo, run, retention.

    Config: ~/.config/commonuserscripts/backup.json (defaults merged
    with the user file; unknown user keys are preserved). Password:
    ~/.config/commonuserscripts/backup-password (0600, generated with
    secrets.token_hex(32), never printed). Default repo
    ~/.local/share/cus/backups/main; default sources
    ~/.config/commonuserscripts and ~/.local/share/cus; retention
    keep_daily 7 / keep_weekly 4 / keep_monthly 6. The run script
    ~/.local/share/cus/backup/run-backup.sh does init (idempotent),
    backup, and forget+prune; the repo path itself is always excluded
    from sources. restic must exist first (install ops-backup-remote).
    """
    kind = "backup"

    def _paths(self, env):
        cfg_dir = env.home / ".config" / "commonuserscripts"
        return {
            "config": cfg_dir / "backup.json",
            "password": cfg_dir / "backup-password",
            "repo": env.home / ".local" / "share" / "cus" / "backups" / "main",
            "script": env.home / ".local" / "share" / "cus" / "backup"
                      / "run-backup.sh",
        }

    def _defaults(self, env):
        p = self._paths(env)
        return {
            "repo": str(p["repo"]),
            "sources": [str(env.home / ".config" / "commonuserscripts"),
                        str(env.home / ".local" / "share" / "cus")],
            "password_file": str(p["password"]),
            "keep_daily": 7, "keep_weekly": 4, "keep_monthly": 6,
        }

    def _load_config(self, module, env) -> dict:
        cfg = self._defaults(env)
        field = module.get("backup") or {}
        for key in ("keep_daily", "keep_weekly", "keep_monthly"):
            if key in field:
                cfg[key] = field[key]
        path = self._paths(env)["config"]
        try:
            if path.exists():
                user = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(user, dict):
                    cfg.update(user)
        except (OSError, ValueError):
            pass
        return cfg

    def ready(self, module, host, env):
        if env.which("restic") is None:
            return "unsupported", "restic not found; install ops-backup-remote first"
        return "available", "write backup config, init repo, run backup + prune"

    def commands(self, module, host, env):
        p = self._paths(env)
        return [["cat", str(p["config"])],
                ["bash", str(p["script"])],
                ["restic", "-r", str(self._load_config(module, env)["repo"]),
                 "snapshots"]]

    def run(self, module, host, env):
        if env.which("restic") is None:
            return 2, ("BLOCKED: restic not found; "
                       "install ops-backup-remote first.")
        cfg = self._load_config(module, env)
        p = self._paths(env)
        cfg_dir = p["config"].parent
        try:
            cfg_dir.mkdir(parents=True, exist_ok=True)
            p["script"].parent.mkdir(parents=True, exist_ok=True)
            p["config"].write_text(json.dumps(cfg, indent=2) + "\n",
                                   encoding="utf-8")
            pw = p["password"]
            if not pw.exists():
                pw.write_text(secrets.token_hex(32) + "\n",
                              encoding="utf-8")
            pw.chmod(0o600)
        except OSError as e:
            return 1, f"FAILED: cannot write backup config ({e})."
        repo = cfg["repo"]
        sources = [s for s in cfg["sources"]
                   if not Path(s).resolve().is_relative_to(Path(repo).resolve())]
        keep = (f"--keep-daily {int(cfg['keep_daily'])} "
                f"--keep-weekly {int(cfg['keep_weekly'])} "
                f"--keep-monthly {int(cfg['keep_monthly'])}")
        script = (
            "#!/bin/sh\n"
            "# CommonUserScripts backup runner (generated by cus).\n"
            "# Password file: 0600, never echoed.\n"
            "set -eu\n"
            f"export RESTIC_REPOSITORY={shlex.quote(repo)}\n"
            f"export RESTIC_PASSWORD_FILE={shlex.quote(str(p['password']))}\n"
            f"if [ ! -f {shlex.quote(repo + '/config')} ]; then\n"
            "  restic init\n"
            "fi\n"
            f"restic backup {' '.join(shlex.quote(s) for s in sources)} "
            f"--exclude {shlex.quote(repo)}\n"
            f"restic forget --prune {keep}\n"
        )
        try:
            p["script"].write_text(script, encoding="utf-8")
            p["script"].chmod(0o755)
        except OSError as e:
            return 1, f"FAILED: cannot write run script ({e})."
        renv = {**os.environ,
                "RESTIC_REPOSITORY": repo,
                "RESTIC_PASSWORD_FILE": str(p["password"])}
        r = env.run(["bash", str(p["script"])], env=renv)
        if r.returncode != 0:
            return 1, (f"FAILED: backup run exited {r.returncode}; "
                       f"config is at {p['config']}, run manually with "
                       f"{p['script']}.")
        r = env.run(["restic", "-r", repo, "snapshots"],
                    env=renv, capture_output=True, text=True)
        count = "unknown"
        if r.returncode == 0:
            count = str(sum(
                1 for line in (r.stdout or "").splitlines()
                if line.strip()
                and len(line.split()[0]) >= 8
                and all(c in "0123456789abcdef"
                        for c in line.split()[0][:8])))
        return 0, (f"Backup complete ({count} snapshot(s) in repo). "
                   f"Config {p['config']}; rerun with {p['script']}.")


register(BackupAdapter())
