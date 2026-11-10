"""Safe starter CLI: explicit apply, no guessed success, no remote execution."""
from __future__ import annotations
import argparse
import datetime
import json
import os
import shlex
import shutil
import subprocess
import sys
from pathlib import Path
from .runtime import detect
from .catalog import modules, profiles, status, package_command

VERSION = "0.1.0-starter"


def state_path() -> Path:
    if sys.platform == "win32":
        base = os.getenv("LOCALAPPDATA") or str(Path.home())
        return Path(base) / "CommonUserScripts" / "events.jsonl"
    base = os.getenv("XDG_STATE_HOME") or str(Path.home() / ".local" / "state")
    return Path(base) / "commonuserscripts" / "events.jsonl"


def log_event(obj: dict) -> None:
    p = state_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    record = {"utc": datetime.datetime.now(datetime.timezone.utc).isoformat(), **obj}
    # No args, configs, keys or sensitive environment variables are logged.
    with p.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def plan_module(mid: str, host: dict) -> dict:
    catalog = modules()
    if mid not in catalog:
        raise ValueError(f"Unknown module: {mid}")
    item = catalog[mid]
    state, reason = status(item, host)
    command = package_command(item, host)
    return {"id": mid, "name": item["name"], "kind": item["kind"],
            "status": state, "detail": reason, "commands": [command] if command else [],
            "install_ready": item["kind"] == "package" and command is not None}


def emit(value, json_mode=False):
    if json_mode:
        print(json.dumps(value, ensure_ascii=False, indent=2))
    elif isinstance(value, str):
        print(value)
    else:
        print(json.dumps(value, ensure_ascii=False, indent=2))


def show_plan(plan: dict, json_mode: bool = False) -> None:
    if json_mode:
        emit(plan, True)
        return
    print(f"[{plan['id']}] {plan['name']} | {plan['status']}: {plan['detail']}")
    for cmd in plan["commands"]:
        print("  planned command:", shlex.join(cmd))
    if not plan["install_ready"]:
        print("  not executable in this starter; see docs/ROADMAP.md")


def attempt(mid: str, host: dict, apply: bool, yes: bool) -> int:
    p = plan_module(mid, host)
    show_plan(p)
    if not apply:
        print("DRY RUN: no changes were made. Add --apply to install a supported module.")
        return 0
    if not p["install_ready"]:
        print("BLOCKED: no verified installation adapter for this module/OS.", file=sys.stderr)
        return 2
    if mid == "git" and p["status"] == "detected":
        print("SKIPPED: detected installed executables; no changes made.")
        return 0
    if not yes:
        if not sys.stdin.isatty():
            print("BLOCKED: noninteractive apply requires --yes.", file=sys.stderr)
            return 2
        confirmation = input(f"Type INSTALL {mid} to proceed: ").strip()
        if confirmation != f"INSTALL {mid}":
            print("Cancelled")
            return 2
    cmd = p["commands"][0]
    is_brew = host["manager"] == "brew"
    is_winget = host["manager"] == "winget"
    if not (host["is_root"] or is_brew or is_winget):
        if host["has_sudo"]:
            cmd = ["sudo", *cmd]
        else:
            print("BLOCKED: root/sudo required for native OS package install.", file=sys.stderr)
            return 2
    try:
        code = subprocess.run(cmd, check=False).returncode
    except (OSError, KeyboardInterrupt) as e:
        print(f"Execution failed: {type(e).__name__}", file=sys.stderr)
        code = 130 if isinstance(e, KeyboardInterrupt) else 127
    log_event({"event": "module_install", "module": mid, "return_code": code,
               "result": "command_success" if code == 0 else "command_failed"})
    if code == 0:
        state, _ = status(modules()[mid], host)
        print("Package command completed; post-install detection:", state)
        # Successful package manager return does not assert every target is functional.
    else:
        print("FAILED: see package manager output above. No success claimed.", file=sys.stderr)
    return code


def print_doctor(host: dict, json_mode: bool = False) -> None:
    if json_mode:
        emit(host, True)
        return
    print("CommonUserScripts host diagnostics (read-only)")
    for k, v in host.items():
        print(f"  {k:12} : {v}")
    print(f"  disk_free_gb : {shutil.disk_usage(Path.home()).free / 1024**3:.1f}")
    print(f"  history      : {state_path()}")
    if not host["manager"]:
        print("  NOTE: no supported package adapter detected; read-only mode.")


def menu(host: dict) -> int:
    if not sys.stdin.isatty():
        print("The interactive menu requires a terminal; use list/plan/doctor.", file=sys.stderr)
        return 2
    mods = modules()
    while True:
        print("\n=== CommonUserScripts (starter) ===")
        for i, module in enumerate(mods.values(), 1):
            state, _ = status(module, host)
            print(f"{i:2d}. {module['name']:<30} [{state}]")
        print(" D. System diagnostics | P. Scenario plans | 0. Exit")
        raw = input("Select: ").strip().lower()
        if raw in {"0", "q", "exit"}:
            print("Exited without cleanup or other side effects.")
            return 0
        if raw == "d":
            print_doctor(host)
        elif raw == "p":
            for profile in profiles().values():
                print(f"{profile['id']:<20} {profile['name']}")
        elif raw.isdigit() and 1 <= int(raw) <= len(mods):
            mid = list(mods)[int(raw)-1]
            show_plan(plan_module(mid, host))
            print("For installation: python3 cus.py install", mid, "--apply")
        else:
            print("Unknown selection; please retry.")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Cross-platform, safety-first script manager starter")
    parser.add_argument("--json", action="store_true", help="structured output for AI/CI")
    sub = parser.add_subparsers(dest="cmd")
    sub.add_parser("doctor")
    sub.add_parser("list")
    sub.add_parser("menu")
    sub.add_parser("history")
    sub.add_parser("version")
    p_show = sub.add_parser("show")
    p_show.add_argument("module")
    p_plan = sub.add_parser("plan")
    p_plan.add_argument("profile", help="profile ID")
    p_ins = sub.add_parser("install")
    p_ins.add_argument("module")
    p_ins.add_argument("--apply", action="store_true")
    p_ins.add_argument("--yes", action="store_true")
    args = parser.parse_args(argv)
    host = detect()
    try:
        if args.cmd in (None, "menu"):
            return menu(host)
        if args.cmd == "doctor":
            print_doctor(host, args.json)
        elif args.cmd == "list":
            emit([plan_module(mid, host) for mid in modules()], args.json)
        elif args.cmd == "show":
            show_plan(plan_module(args.module, host), args.json)
        elif args.cmd == "plan":
            p = profiles().get(args.profile)
            if not p:
                raise ValueError(f"Unknown profile: {args.profile}")
            result = {"profile": p, "items": [plan_module(mid, host) for mid in p["modules"]],
                      "mode": "plan-only (no scenario auto apply in starter)"}
            if args.json:
                emit(result, True)
            else:
                print(f"SCENARIO: {p['name']} (no changes)")
                for item in result["items"]:
                    show_plan(item)
        elif args.cmd == "install":
            return attempt(args.module, host, args.apply, args.yes)
        elif args.cmd == "history":
            p = state_path()
            lines = p.read_text(encoding="utf-8").splitlines()[-30:] if p.exists() else []
            if args.json:
                emit([json.loads(l) for l in lines], True)
            else:
                print("\n".join(lines) if lines else "No executed installation actions have been recorded.")
        elif args.cmd == "version":
            print(VERSION)
        return 0
    except (ValueError, KeyError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("\nInterrupted; leaving safely.", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
