"""Mock tests for the M1 install adapters (src/cus/adapters.py).

No real installs, no network, no host changes: subprocess, filesystem
lookups and TCP connects are all faked through AdapterEnv. Each adapter
is covered for success, failure and refusal branches.
"""
import hashlib
import io
import json
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.cus import __version__, adapters
from src.cus.adapters import AdapterEnv, get_adapter
from src.cus.catalog import modules as load_modules
from src.cus.catalog import plan_module


class FakeResult:
    def __init__(self, returncode=0, stdout="", stderr=""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


class FakeRunner:
    """Records argv; answers from a handler(argv, kw) -> FakeResult."""

    def __init__(self, handler=None):
        self.calls = []
        self.handler = handler or (lambda argv, kw: FakeResult())

    def __call__(self, argv, **kw):
        argv = [str(a) for a in argv]
        self.calls.append((argv, kw))
        return self.handler(argv, kw)

    def called_with(self, prefix):
        return [c for c, _ in self.calls if c[:len(prefix)] == prefix]


class FakeConn:
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def close(self):
        pass


def make_env(tmp, which_map=None, runner=None, connect=None, host=None):
    which_map = which_map or {}
    return AdapterEnv(
        home=tmp, host=host or {},
        runner=runner or FakeRunner(),
        which=lambda name: which_map.get(name),
        connect=connect or (lambda addr, timeout=None: FakeConn()),
        log=lambda *a: None)


def ok_result(argv, kw):
    return FakeResult(0)


def version_runner(versions):
    """Handler: `X --version` returns versions[X]; everything else 0."""
    def handler(argv, kw):
        if len(argv) == 2 and argv[1] == "--version":
            out = versions.get(argv[0])
            if out is None:
                return FakeResult(1, "", "not found")
            return FakeResult(0, out + "\n")
        return FakeResult(0)
    return handler


HOST_APT_ROOT = {"manager": "apt", "system": "linux", "arch": "x86_64",
                 "is_root": True, "has_sudo": True}
HOST_APT_USER = {"manager": "apt", "system": "linux", "arch": "x86_64",
                 "is_root": False, "has_sudo": True}


class RegistryTests(unittest.TestCase):
    def test_six_adapters_registered(self):
        self.assertEqual(
            {get_adapter(k).kind for k in
             ("npm", "npx", "installer", "fnm", "service", "backup")},
            {"npm", "npx", "installer", "fnm", "service", "backup"})

    def test_no_adapter_for_package_or_planned(self):
        self.assertIsNone(get_adapter("package"))
        self.assertIsNone(get_adapter("planned"))
        self.assertIsNone(get_adapter("nope"))

    def test_version_stays_2_1_0(self):
        self.assertEqual(__version__, "2.1.0")


class NpmAdapterTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Path(self.tmp.name)
        self.module = load_modules()["ai-codex"]
        self.adapter = get_adapter("npm")

    def tearDown(self):
        self.tmp.cleanup()

    def test_ready_false_without_node(self):
        env = make_env(self.home)
        ok, detail = self.adapter.ready(self.module, HOST_APT_ROOT, env)
        self.assertEqual(ok, "unsupported")
        self.assertIn("dev-node", detail)

    def test_ready_true_with_node_npm(self):
        env = make_env(self.home, which_map={
            "node": "/usr/bin/node", "npm": "/usr/bin/npm"})
        ok, detail = self.adapter.ready(self.module, HOST_APT_ROOT, env)
        self.assertEqual(ok, "available")
        self.assertIn("@openai/codex", detail)

    def test_run_blocked_without_npm(self):
        env = make_env(self.home)
        code, msg = self.adapter.run(self.module, HOST_APT_ROOT, env)
        self.assertEqual(code, 2)
        self.assertIn("BLOCKED", msg)

    def test_run_skipped_when_already_installed(self):
        runner = FakeRunner(version_runner({"codex": "codex-cli 0.167.0"}))
        env = make_env(self.home, which_map={
            "node": "/usr/bin/node", "npm": "/usr/bin/npm"}, runner=runner)
        code, msg = self.adapter.run(self.module, HOST_APT_ROOT, env)
        self.assertEqual(code, 0)
        self.assertIn("SKIPPED", msg)
        self.assertEqual(runner.called_with(["npm"]), [])

    def test_run_verify_timeout_is_failure_not_crash(self):
        import subprocess

        def handler(argv, kw):
            raise subprocess.TimeoutExpired(argv, kw.get("timeout", 30))
        env = make_env(self.home, runner=FakeRunner(handler))
        ok, line = adapters.run_verify(["gemini", "--version"], env)
        self.assertFalse(ok)
        self.assertEqual(line, "timed out after 30s")
        ok, line = adapters.run_verify(["gemini", "--version"], env,
                                       timeout=120)
        self.assertFalse(ok)
        self.assertEqual(line, "timed out after 120s")
        timeouts = [kw.get("timeout") for _, kw in env.runner.calls]
        self.assertEqual(timeouts, [30, 120])

    def test_run_success_installs_then_verifies(self):
        calls = {"verified": False}

        def handler(argv, kw):
            if argv[:2] == ["codex", "--version"]:
                return FakeResult(0, "codex-cli 0.167.0\n") \
                    if calls["verified"] else FakeResult(1, "", "nope")
            if argv[1:3] == ["install", "-g"]:
                calls["verified"] = True
                return FakeResult(0)
            return FakeResult(0)
        runner = FakeRunner(handler)
        env = make_env(self.home, which_map={
            "node": "/usr/bin/node", "npm": "/usr/bin/npm"}, runner=runner)
        code, msg = self.adapter.run(self.module, HOST_APT_ROOT, env)
        self.assertEqual(code, 0)
        self.assertIn("Installed @openai/codex", msg)
        self.assertEqual(
            runner.called_with(["/usr/bin/npm", "install", "-g"]),
            [["/usr/bin/npm", "install", "-g", "@openai/codex"]])
        # First-run CLI checks get the longer timeout (gemini --version
        # exceeded the old 30s cap in container verification).
        verify_timeouts = [kw.get("timeout") for argv, kw in runner.calls
                           if argv[:2] == ["codex", "--version"]]
        self.assertEqual(verify_timeouts, [120, 120])

    def test_run_failure_npm_exits_nonzero(self):
        def handler(argv, kw):
            if argv[:2] == ["codex", "--version"]:
                return FakeResult(1, "", "nope")
            return FakeResult(1, "", "npm ERR!")
        env = make_env(self.home, which_map={
            "node": "/usr/bin/node", "npm": "/usr/bin/npm"},
            runner=FakeRunner(handler))
        code, msg = self.adapter.run(self.module, HOST_APT_ROOT, env)
        self.assertEqual(code, 1)
        self.assertIn("FAILED", msg)

    def test_run_failure_verify_fails_after_install(self):
        def handler(argv, kw):
            if argv[:2] == ["codex", "--version"]:
                return FakeResult(1, "", "nope")
            return FakeResult(0)
        env = make_env(self.home, which_map={
            "node": "/usr/bin/node", "npm": "/usr/bin/npm"},
            runner=FakeRunner(handler))
        code, msg = self.adapter.run(self.module, HOST_APT_ROOT, env)
        self.assertEqual(code, 1)
        self.assertIn("FAILED", msg)


class NpxAdapterTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Path(self.tmp.name)
        self.module = load_modules()["ai-zcf"]
        self.adapter = get_adapter("npx")

    def tearDown(self):
        self.tmp.cleanup()

    def test_ready_false_without_npx(self):
        env = make_env(self.home)
        ok, _ = self.adapter.ready(self.module, HOST_APT_ROOT, env)
        self.assertEqual(ok, "unsupported")

    def test_run_success(self):
        def handler(argv, kw):
            if argv[:2] == ["npx", "-y"]:
                return FakeResult(0, "zcf 3.7.3\n")
            return FakeResult(0)
        env = make_env(self.home, which_map={"npx": "/usr/bin/npx"},
                       runner=FakeRunner(handler))
        code, msg = self.adapter.run(self.module, HOST_APT_ROOT, env)
        self.assertEqual(code, 0)
        self.assertIn("runs via npx", msg)
        # First npx run downloads the package and zcf itself is slow to
        # start (~80s warm on a small box), so the verify gets 300s.
        self.assertEqual(
            [kw.get("timeout") for argv, kw in env.runner.calls
             if argv[1:2] == ["-y"]],
            [300])

    def test_run_failure(self):
        def handler(argv, kw):
            return FakeResult(1, "", "npx ERR!")
        env = make_env(self.home, which_map={"npx": "/usr/bin/npx"},
                       runner=FakeRunner(handler))
        code, msg = self.adapter.run(self.module, HOST_APT_ROOT, env)
        self.assertEqual(code, 1)
        self.assertIn("FAILED", msg)


class InstallerAdapterTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Path(self.tmp.name)
        self.module = load_modules()["ai-claude"]
        self.adapter = get_adapter("installer")

    def tearDown(self):
        self.tmp.cleanup()

    def _env(self, runner=None, bash=True):
        which = {"bash": "/usr/bin/bash"} if bash else {}
        return make_env(self.home, which_map=which,
                        runner=runner or FakeRunner())

    def test_ready_false_without_pinned_hash(self):
        mod = dict(self.module, installer={"url": "https://x/"})
        env = self._env()
        ok, _ = self.adapter.ready(mod, HOST_APT_ROOT, env)
        self.assertEqual(ok, "unsupported")

    def test_ready_false_without_bash(self):
        env = self._env(bash=False)
        ok, _ = self.adapter.ready(self.module, HOST_APT_ROOT, env)
        self.assertEqual(ok, "unsupported")

    def test_ready_true_with_pinned_installer(self):
        env = self._env()
        ok, detail = self.adapter.ready(self.module, HOST_APT_ROOT, env)
        self.assertEqual(ok, "available")
        self.assertIn("sha256", detail)

    def test_run_refuses_on_checksum_mismatch(self):
        def handler(argv, kw):
            if argv[:2] == ["claude", "--version"]:
                return FakeResult(1, "", "not installed")
            return FakeResult(0)
        runner = FakeRunner(handler)
        env = self._env(runner)
        with mock.patch.object(adapters, "download_verified",
                               return_value=False) as dv:
            code, msg = self.adapter.run(self.module, HOST_APT_ROOT, env)
        self.assertEqual(code, 2)
        self.assertIn("BLOCKED", msg)
        self.assertIn("checksum", msg)
        dv.assert_called_once()
        # The initial --version probe ran, but the installer was never executed.
        self.assertEqual(runner.called_with(["bash"]), [])

    def test_run_success_after_verified_download(self):
        def fake_download(url, dest, expected, log=None):
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text("#!/bin/sh\necho installed\n")
            return True

        installed = {"done": False}

        def handler(argv, kw):
            if argv[:2] == ["claude", "--version"]:
                return FakeResult(0, "2.0.0 (Claude Code)\n") \
                    if installed["done"] else FakeResult(1, "", "nope")
            if argv[0] == "bash":
                installed["done"] = True
            return FakeResult(0)
        runner = FakeRunner(handler)
        env = self._env(runner)
        with mock.patch.object(adapters, "download_verified",
                               side_effect=fake_download):
            code, msg = self.adapter.run(self.module, HOST_APT_ROOT, env)
        self.assertEqual(code, 0)
        self.assertIn("Installed claude", msg)
        self.assertTrue(runner.called_with(["bash"]))

    def test_run_skipped_when_already_installed(self):
        runner = FakeRunner(version_runner({"claude": "2.0.0"}))
        env = self._env(runner)
        code, msg = self.adapter.run(self.module, HOST_APT_ROOT, env)
        self.assertEqual(code, 0)
        self.assertIn("SKIPPED", msg)
        self.assertEqual(runner.called_with(["bash"]), [])

    def test_run_failure_installer_exits_nonzero(self):
        def fake_download(url, dest, expected, log=None):
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text("#!/bin/sh\n")
            return True

        def handler(argv, kw):
            if argv[:2] == ["claude", "--version"]:
                return FakeResult(1, "", "nope")
            return FakeResult(3, "", "boom")
        env = self._env(FakeRunner(handler))
        with mock.patch.object(adapters, "download_verified",
                               side_effect=fake_download):
            code, msg = self.adapter.run(self.module, HOST_APT_ROOT, env)
        self.assertEqual(code, 3)
        self.assertIn("FAILED", msg)

    def test_run_failure_verify_fails_after_install(self):
        def fake_download(url, dest, expected, log=None):
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text("#!/bin/sh\n")
            return True

        def handler(argv, kw):
            return FakeResult(0) if argv[0] == "bash" else FakeResult(1)
        env = self._env(FakeRunner(handler))
        with mock.patch.object(adapters, "download_verified",
                               side_effect=fake_download):
            code, msg = self.adapter.run(self.module, HOST_APT_ROOT, env)
        self.assertEqual(code, 1)
        self.assertIn("FAILED", msg)


if __name__ == "__main__":
    unittest.main()


class FnmAdapterTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Path(self.tmp.name)
        self.module = load_modules()["dev-node"]
        self.adapter = get_adapter("fnm")

    def tearDown(self):
        self.tmp.cleanup()

    def test_ready_false_for_unknown_arch(self):
        host = dict(HOST_APT_ROOT, arch="riscv64")
        env = make_env(self.home)
        ok, _ = self.adapter.ready(self.module, host, env)
        self.assertEqual(ok, "unsupported")

    def test_ready_true_for_x86_64_linux(self):
        env = make_env(self.home)
        ok, detail = self.adapter.ready(self.module, HOST_APT_ROOT, env)
        self.assertEqual(ok, "available")
        self.assertIn("fnm 1.39.0", detail)

    def test_run_skipped_when_node_new_enough(self):
        def handler(argv, kw):
            if argv == ["/usr/bin/node", "--version"]:
                return FakeResult(0, "v22.1.0\n")
            return FakeResult(0)
        env = make_env(self.home, which_map={"node": "/usr/bin/node",
                                             "npm": "/usr/bin/npm"},
                       runner=FakeRunner(handler))
        code, msg = self.adapter.run(self.module, HOST_APT_ROOT, env)
        self.assertEqual(code, 0)
        self.assertIn("SKIPPED", msg)
        self.assertIn("22.1.0", msg)

    def _fake_fnm_zip(self, url, dest, expected, log=None):
        dest.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(dest, "w") as zf:
            zf.writestr("fnm", "#!/bin/sh\necho fnm\n")
        return True

    def test_run_success_via_fnm(self):
        def handler(argv, kw):
            fnm = str(self.home / ".local" / "share" / "fnm" / "fnm")
            if argv[:2] == [fnm, "install"]:
                # Simulate fnm creating a Node installation. Real fnm
                # layout: node-versions/<ver>/installation/bin/node.
                bindir = (self.home / ".local" / "share" / "fnm"
                          / "node-versions" / "v24.5.0" / "installation" / "bin")
                bindir.mkdir(parents=True, exist_ok=True)
                for name in ("node", "npm", "npx"):
                    (bindir / name).write_text("#!/bin/sh\n")
                return FakeResult(0)
            if argv[1:] == ["--version"] and "node-versions" in argv[0]:
                return FakeResult(0, "v24.5.0\n")
            return FakeResult(0)
        env = make_env(self.home, runner=FakeRunner(handler))
        with mock.patch.object(adapters, "download_verified",
                               side_effect=self._fake_fnm_zip):
            code, msg = self.adapter.run(self.module, HOST_APT_ROOT, env)
        self.assertEqual(code, 0)
        self.assertIn("via fnm", msg)
        self.assertIn("24.5.0", msg)
        self.assertTrue((self.home / ".local" / "share" / "fnm" / "fnm").exists())
        self.assertIn("fnm env", (self.home / ".bashrc").read_text())

    def test_run_failure_message_names_missing_library(self):
        """A node binary that cannot start (e.g. missing libatomic)
        must fail loudly WITH the underlying error, not a bare ()."""
        def handler(argv, kw):
            fnm = str(self.home / ".local" / "share" / "fnm" / "fnm")
            if argv[:2] == [fnm, "install"]:
                bindir = (self.home / ".local" / "share" / "fnm"
                          / "node-versions" / "v24.5.0" / "installation" / "bin")
                bindir.mkdir(parents=True, exist_ok=True)
                for name in ("node", "npm", "npx"):
                    (bindir / name).write_text("#!/bin/sh\n")
                return FakeResult(0)
            if argv[1:] == ["--version"] and "node-versions" in argv[0]:
                return FakeResult(127, "", "node: error while loading "
                                  "shared libraries: libatomic.so.1: "
                                  "cannot open shared object file")
            return FakeResult(0)
        env = make_env(self.home, runner=FakeRunner(handler))
        with mock.patch.object(adapters, "download_verified",
                               side_effect=self._fake_fnm_zip):
            code, msg = self.adapter.run(self.module, HOST_APT_ROOT, env)
        self.assertEqual(code, 1)
        self.assertIn("libatomic.so.1", msg)

    def test_run_checksum_mismatch_falls_back_to_nodesource(self):
        def fake_download(url, dest, log=None):
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(b"key-bytes")
            return dest

        which_map = {"gpg": "/usr/bin/gpg"}

        def handler(argv, kw):
            if argv == ["/usr/bin/node", "--version"]:
                return FakeResult(0, "v22.0.0\n")
            if argv[:3] == ["apt-get", "install", "-y"]:
                # Simulate apt installing nodejs: node appears on PATH.
                which_map["node"] = "/usr/bin/node"
            return FakeResult(0)
        env = make_env(self.home, which_map=which_map,
                       runner=FakeRunner(handler))
        with mock.patch.object(adapters, "download_verified",
                               return_value=False), \
                mock.patch.object(adapters, "download",
                                  side_effect=fake_download):
            code, msg = self.adapter.run(self.module, HOST_APT_ROOT, env)
        self.assertEqual(code, 0)
        self.assertIn("NodeSource", msg)
        self.assertIn("22.0.0", msg)

    def test_run_fallback_blocked_without_apt(self):
        host = dict(HOST_APT_ROOT, manager="brew")
        env = make_env(self.home)
        with mock.patch.object(adapters, "download_verified",
                               return_value=False):
            code, msg = self.adapter.run(self.module, host, env)
        self.assertEqual(code, 2)
        self.assertIn("BLOCKED", msg)
        self.assertIn("apt", msg)

    def test_run_fallback_blocked_without_root_or_sudo(self):
        host = dict(HOST_APT_USER, is_root=False, has_sudo=False)
        env = make_env(self.home)
        with mock.patch.object(adapters, "download_verified",
                               return_value=False):
            code, msg = self.adapter.run(self.module, host, env)
        self.assertEqual(code, 2)
        self.assertIn("BLOCKED", msg)


class FirewallAdapterTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Path(self.tmp.name)
        self.module = load_modules()["net-firewall"]
        self.adapter = get_adapter("service")

    def tearDown(self):
        self.tmp.cleanup()

    def _env(self, which_map=None, runner=None, connect=None):
        if which_map is None:
            which_map = {"ufw": "/usr/sbin/ufw"}
        return make_env(self.home, which_map=which_map,
                        runner=runner, connect=connect)

    def test_ready_false_without_root(self):
        env = self._env()
        ok, _ = self.adapter.ready(self.module, HOST_APT_USER | {"has_sudo": False}, env)
        self.assertEqual(ok, "unsupported")

    def test_ready_false_without_backend(self):
        env = self._env(which_map={})
        ok, _ = self.adapter.ready(self.module, HOST_APT_ROOT, env)
        self.assertEqual(ok, "unsupported")

    def test_ready_true_with_ufw(self):
        env = self._env()
        ok, detail = self.adapter.ready(self.module, HOST_APT_ROOT, env)
        self.assertEqual(ok, "available")
        self.assertIn("ufw", detail)

    def test_run_blocked_without_backend(self):
        env = self._env(which_map={})
        code, msg = self.adapter.run(self.module, HOST_APT_ROOT, env)
        self.assertEqual(code, 2)
        self.assertIn("BLOCKED", msg)

    def test_run_blocked_when_ssh_unreachable(self):
        def dead(addr, timeout=None):
            raise OSError("connection refused")
        env = self._env(connect=dead)
        code, msg = self.adapter.run(self.module, HOST_APT_ROOT, env)
        self.assertEqual(code, 2)
        self.assertIn("BLOCKED", msg)

    def test_run_success_ufw(self):
        runner = FakeRunner()
        env = self._env(runner=runner)
        # Port comes from the host's sshd_config (26182 on ohio-08, 22 default).
        port = self.adapter._ssh_port(env)
        code, msg = self.adapter.run(self.module, HOST_APT_ROOT, env)
        self.assertEqual(code, 0)
        self.assertIn("ufw", msg)
        self.assertIn("verified reachable", msg)
        self.assertIn(str(port), msg)
        self.assertEqual(runner.called_with(["ufw", "allow"]),
                         [["ufw", "allow", f"{port}/tcp"]])
        self.assertTrue(runner.called_with(["ufw", "--force", "enable"]))

    def test_run_refuses_after_allow_when_ssh_dies(self):
        # First connect (pre-check) ok, second (post-allow) refused.
        answers = iter([True, False])

        def flaky(addr, timeout=None):
            if next(answers):
                return FakeConn()
            raise OSError("connection refused")
        runner = FakeRunner()
        env = self._env(runner=runner, connect=flaky)
        code, msg = self.adapter.run(self.module, HOST_APT_ROOT, env)
        self.assertEqual(code, 1)
        self.assertIn("FAILED", msg)
        # Never reached the enable step.
        self.assertEqual(runner.called_with(["ufw", "--force", "enable"]), [])

    def test_run_failure_ufw_allow_exits_nonzero(self):
        def handler(argv, kw):
            return FakeResult(1, "", "ufw ERR") if argv[:2] == ["ufw", "allow"] \
                else FakeResult(0)
        env = self._env(runner=FakeRunner(handler))
        code, msg = self.adapter.run(self.module, HOST_APT_ROOT, env)
        self.assertEqual(code, 1)
        self.assertIn("FAILED", msg)

    def test_run_iptables_requires_established_rule(self):
        def handler(argv, kw):
            if argv[:3] == ["iptables", "-C", "INPUT"]:
                return FakeResult(1)  # no conntrack/state rule
            return FakeResult(0)
        env = self._env(which_map={"iptables": "/usr/sbin/iptables"},
                        runner=FakeRunner(handler))
        code, msg = self.adapter.run(self.module, HOST_APT_ROOT, env)
        self.assertEqual(code, 2)
        self.assertIn("BLOCKED", msg)
        self.assertIn("ESTABLISHED", msg)

    def test_run_iptables_success_with_established_rule(self):
        runner = FakeRunner()
        env = self._env(which_map={"iptables": "/usr/sbin/iptables"},
                        runner=runner)
        # Default FakeRunner returns 0 for everything, so the -C check passes.
        code, msg = self.adapter.run(self.module, HOST_APT_ROOT, env)
        self.assertEqual(code, 0)
        self.assertIn("iptables", msg)
        self.assertTrue(runner.called_with(["iptables", "-P", "INPUT", "DROP"]))


class BackupAdapterTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Path(self.tmp.name)
        self.module = load_modules()["backup"]
        self.adapter = get_adapter("backup")

    def tearDown(self):
        self.tmp.cleanup()

    def _env(self, restic=True, runner=None):
        which = {"restic": "/usr/bin/restic"} if restic else {}
        return make_env(self.home, which_map=which, runner=runner)

    def test_ready_false_without_restic(self):
        env = self._env(restic=False)
        ok, detail = self.adapter.ready(self.module, HOST_APT_ROOT, env)
        self.assertEqual(ok, "unsupported")
        self.assertIn("ops-backup-remote", detail)

    def test_run_blocked_without_restic(self):
        env = self._env(restic=False)
        code, msg = self.adapter.run(self.module, HOST_APT_ROOT, env)
        self.assertEqual(code, 2)
        self.assertIn("BLOCKED", msg)

    def test_run_success_writes_config_and_runs_backup(self):
        def handler(argv, kw):
            if argv[:2] == ["restic", "-r"]:
                return FakeResult(0, "abc12345 2026-11-10 10:00:00  host\n"
                                     "def67890 2026-11-10 11:00:00  host\n")
            return FakeResult(0)
        runner = FakeRunner(handler)
        env = self._env(runner=runner)
        code, msg = self.adapter.run(self.module, HOST_APT_ROOT, env)
        self.assertEqual(code, 0)
        self.assertIn("2 snapshot(s)", msg)
        cfg_path = self.home / ".config" / "commonuserscripts" / "backup.json"
        cfg = json.loads(cfg_path.read_text())
        self.assertEqual(cfg["keep_daily"], 7)
        self.assertEqual(cfg["keep_weekly"], 4)
        self.assertEqual(cfg["keep_monthly"], 6)
        pw = self.home / ".config" / "commonuserscripts" / "backup-password"
        self.assertTrue(pw.exists())
        self.assertEqual(oct(pw.stat().st_mode & 0o777), "0o600")
        script = self.home / ".local" / "share" / "cus" / "backup" / "run-backup.sh"
        self.assertTrue(script.exists())
        self.assertTrue(script.stat().st_mode & 0o111)
        text = script.read_text()
        self.assertIn("restic backup", text)
        self.assertIn("restic forget --prune", text)
        self.assertIn("--exclude", text)
        self.assertTrue(runner.called_with(["bash", str(script)]))

    def test_run_failure_backup_exits_nonzero(self):
        def handler(argv, kw):
            if argv[0] == "bash":
                return FakeResult(1, "", "restic ERR")
            return FakeResult(0)
        env = self._env(runner=FakeRunner(handler))
        code, msg = self.adapter.run(self.module, HOST_APT_ROOT, env)
        self.assertEqual(code, 1)
        self.assertIn("FAILED", msg)

    def test_user_config_merged_and_password_preserved(self):
        cfg_dir = self.home / ".config" / "commonuserscripts"
        cfg_dir.mkdir(parents=True)
        (cfg_dir / "backup.json").write_text(json.dumps({
            "repo": "/mnt/myrepo", "keep_daily": 3,
            "custom_key": "keep-me"}))
        (cfg_dir / "backup-password").write_text("existing-secret\n")
        env = self._env()
        code, _ = self.adapter.run(self.module, HOST_APT_ROOT, env)
        self.assertEqual(code, 0)
        cfg = json.loads((cfg_dir / "backup.json").read_text())
        self.assertEqual(cfg["repo"], "/mnt/myrepo")
        self.assertEqual(cfg["keep_daily"], 3)
        self.assertEqual(cfg["custom_key"], "keep-me")
        self.assertEqual((cfg_dir / "backup-password").read_text(),
                         "existing-secret\n")


class CatalogIntegrationTests(unittest.TestCase):
    """plan_module() integration: adapter gating end to end.

    catalog.status() checks detect with the real shutil.which, so these
    tests patch it to None: adapter readiness must come from the fake
    env only, never from whatever happens to be installed on the host.
    """
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Path(self.tmp.name)
        self._which_patch = mock.patch("shutil.which", return_value=None)
        self._which_patch.start()

    def tearDown(self):
        self._which_patch.stop()
        self.tmp.cleanup()

    def test_plan_module_key_set_unchanged(self):
        env = make_env(self.home)
        plan = plan_module("ai-codex", HOST_APT_ROOT, env)
        self.assertEqual(set(plan),
                         {"id", "name", "kind", "status", "detail",
                          "commands", "install_ready"})

    def test_minimal_vps_ready_with_ufw(self):
        env = make_env(self.home, which_map={"ufw": "/usr/sbin/ufw"})
        plans = {m: plan_module(m, HOST_APT_ROOT, env)
                 for m in ("base-cli", "git", "python", "net-firewall",
                           "diagnostics")}
        self.assertTrue(plans["net-firewall"]["install_ready"])
        self.assertEqual(plans["net-firewall"]["kind"], "service")
        # diagnostics is builtin: ready by design, never install_ready.
        self.assertEqual(plans["diagnostics"]["status"], "ready")
        self.assertFalse(plans["diagnostics"]["install_ready"])

    def test_ai_agent_blocked_before_node_then_ready_after(self):
        env = make_env(self.home, which_map={"bash": "/usr/bin/bash"})
        before = {m: plan_module(m, HOST_APT_ROOT, env)
                  for m in ("dev-node", "ai-codex", "ai-gemini",
                            "ai-claude", "ai-grok", "ai-zcf")}
        self.assertTrue(before["dev-node"]["install_ready"])
        self.assertTrue(before["ai-claude"]["install_ready"])
        self.assertTrue(before["ai-grok"]["install_ready"])
        for mid in ("ai-codex", "ai-gemini", "ai-zcf"):
            self.assertFalse(before[mid]["install_ready"],
                             f"{mid} must wait for dev-node")
        env2 = make_env(self.home, which_map={
            "node": "/usr/bin/node", "npm": "/usr/bin/npm",
            "npx": "/usr/bin/npx"})
        after = {m: plan_module(m, HOST_APT_ROOT, env2)
                 for m in ("ai-codex", "ai-gemini", "ai-zcf")}
        for mid, plan in after.items():
            self.assertTrue(plan["install_ready"], mid)

    def test_backup_ready_only_with_restic(self):
        env = make_env(self.home)
        self.assertFalse(plan_module("backup", HOST_APT_ROOT, env)["install_ready"])
        env2 = make_env(self.home, which_map={"restic": "/usr/bin/restic"})
        self.assertTrue(plan_module("backup", HOST_APT_ROOT, env2)["install_ready"])

    def test_planned_modules_stay_planned_without_adapter(self):
        env = make_env(self.home)
        for mid in ("dev-go", "dev-android", "net-shadowsocks", "docker",
                    "agent-mcp", "sys-ssh"):
            plan = plan_module(mid, HOST_APT_ROOT, env)
            self.assertEqual(plan["status"], "planned", mid)
            self.assertFalse(plan["install_ready"], mid)


class NodeEnvTests(unittest.TestCase):
    """node_env() must find fnm's real layout:
    node-versions/<ver>/installation/bin/node."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def _make_node(self, version, layout="installation"):
        if layout == "installation":
            bindir = (self.home / ".local" / "share" / "fnm"
                      / "node-versions" / version / "installation" / "bin")
        else:
            bindir = (self.home / ".local" / "share" / "fnm"
                      / "node-versions" / version / "bin")
        bindir.mkdir(parents=True)
        for name in ("node", "npm", "npx"):
            (bindir / name).write_text("#!/bin/sh\n")
        return bindir

    def test_finds_installation_layout(self):
        bindir = self._make_node("v24.5.0", "installation")
        env = adapters.node_env(self.home, lambda n: None)
        self.assertEqual(env["node"], bindir / "node")
        self.assertEqual(env["node_version"], (24, 5, 0))
        self.assertEqual(env["path_dirs"], [str(bindir)])

    def test_falls_back_to_direct_bin_layout(self):
        bindir = self._make_node("v22.1.0", "direct")
        env = adapters.node_env(self.home, lambda n: None)
        self.assertEqual(env["node"], bindir / "node")
        self.assertEqual(env["node_version"], (22, 1, 0))

    def test_prefers_newest_version(self):
        self._make_node("v22.1.0", "installation")
        bindir = self._make_node("v26.13.0", "installation")
        env = adapters.node_env(self.home, lambda n: None)
        self.assertEqual(env["node"], bindir / "node")
        self.assertEqual(env["node_version"], (26, 13, 0))

    def test_falls_back_to_path_when_no_fnm(self):
        env = adapters.node_env(
            self.home, lambda n: "/usr/bin/node" if n == "node" else None)
        self.assertEqual(str(env["node"]), "/usr/bin/node")
        self.assertEqual(env["node_version"], ())
