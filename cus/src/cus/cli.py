"""Safe starter CLI: explicit apply, no guessed success, no remote execution.

Console UI lives in src/cus/ui/; resource sampling in src/cus/monitor.py.
This module keeps the command surface and JSON output unchanged.
"""
from __future__ import annotations
import argparse
import datetime
import json
import subprocess
import sys
from . import __version__
from .adapters import AdapterEnv, get_adapter
from .catalog import modules, plan_module, profiles, status
from .monitor import collect
from .runtime import detect, state_path
from .ui.dashboard import (dashboard_data, format_plan,
                           render_dashboard_page, render_doctor)
from .ui.layout import terminal_size, use_unicode
from .ui.menu import run_console
from .ui.renderer import safe_print
from .ui.theme import Theme

VERSION = __version__


def log_event(obj: dict) -> None:
    p = state_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    record = {"utc": datetime.datetime.now(datetime.timezone.utc).isoformat(), **obj}
    # No args, configs, keys or sensitive environment variables are logged.
    with p.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


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
    print(format_plan(plan))


def attempt(mid: str, host: dict, apply: bool, yes: bool) -> int:
    module = modules()[mid]
    adapter = get_adapter(module["kind"])
    env = AdapterEnv() if adapter is not None else None
    p = plan_module(mid, host, env)
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
    if adapter is not None:
        # Adapter path: same confirmation gate as packages, then dispatch.
        # Adapters enforce their own root/sudo and refusal rules.
        if adapter.needs_root and not (host["is_root"] or host["has_sudo"]):
            print("BLOCKED: root/sudo required for this adapter.", file=sys.stderr)
            return 2
        try:
            code, message = adapter.run(module, host, env)
        except (OSError, KeyboardInterrupt) as e:
            print(f"Execution failed: {type(e).__name__}", file=sys.stderr)
            code, message = (130 if isinstance(e, KeyboardInterrupt) else 127), None
        log_event({"event": "module_install", "module": mid, "return_code": code,
                   "result": "command_success" if code == 0 else "command_failed"})
        if message:
            print(message)
        if code == 0:
            state, _ = status(module, host, env)
            print("Adapter completed; post-install detection:", state)
        else:
            print("FAILED: see output above. No success claimed.", file=sys.stderr)
        return code
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
    for line in render_doctor(host):
        print(line)


def menu(host: dict) -> int:
    if not sys.stdin.isatty():
        print("The interactive menu requires a terminal; use list/plan/doctor.", file=sys.stderr)
        return 2
    return run_console(host)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Cross-platform, safety-first script manager starter")
    parser.add_argument("--json", action="store_true", help="structured output for AI/CI")
    sub = parser.add_subparsers(dest="cmd")
    p_doctor = sub.add_parser("doctor")
    p_doctor.add_argument("--json", action="store_true", default=argparse.SUPPRESS)
    p_list = sub.add_parser("list")
    p_list.add_argument("--json", action="store_true", default=argparse.SUPPRESS)
    sub.add_parser("menu")
    p_history = sub.add_parser("history")
    p_history.add_argument("--json", action="store_true", default=argparse.SUPPRESS)
    sub.add_parser("version")
    p_dash = sub.add_parser("dashboard")
    p_dash.add_argument("--json", action="store_true", default=argparse.SUPPRESS)
    p_show = sub.add_parser("show")
    p_show.add_argument("module")
    p_show.add_argument("--json", action="store_true", default=argparse.SUPPRESS)
    p_plan = sub.add_parser("plan")
    p_plan.add_argument("profile", help="profile ID")
    p_plan.add_argument("--json", action="store_true", default=argparse.SUPPRESS)
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
        elif args.cmd == "dashboard":
            snap = collect()
            if args.json:
                emit(dashboard_data(host, snap), True)
            else:
                width, _ = terminal_size()
                theme = Theme()
                counts = (len(profiles()), len(modules()))
                for line in render_dashboard_page(
                        host, snap, width, use_unicode(), theme, counts):
                    safe_print(line)
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
