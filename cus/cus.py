#!/usr/bin/env python3
"""
CommonUserScripts (CUS) V2 — Universal OS-Aware Environment & Script Manager
Main entrypoint for CLI commands and interactive TUI menu.
"""

import argparse
import json
import sys
import os

from core.platform.os_detect import detect_system
from core.engine import ExecutionEngine, ExecutionStatus


def print_banner():
    banner = r"""
   _____ _    _  _____   __      ______  
  / ____| |  | |/ ____|  \ \    / /___ \ 
 | |    | |  | | (___     \ \  / /  __) |
 | |    | |  | |\___ \     \ \/ /  |__ < 
 | |____| |__| |____) |     \  /   ___) |
  \_____|\____/|_____/       \/   |____/ 
 Universal Environment & Script Orchestrator
"""
    print("\033[36m" + banner + "\033[0m")


def handle_status(args, engine: ExecutionEngine):
    os_info = engine.os_info.to_dict()
    data = {
        "platform": os_info,
        "profiles_count": len(engine.profiles),
        "modules_count": len(engine.modules),
    }

    if args.json:
        print(json.dumps(data, indent=2, ensure_ascii=False))
        return

    print("\033[1;32m=== 系统环境与核心底座状态 ===\033[0m")
    print(f"操作系统 (OS):       {os_info['system']} ({os_info['distribution']} {os_info['version']})")
    print(f"硬件架构 (Arch):     {os_info['arch']}")
    print(f"原生包管理器:        {os_info['pkg_manager']}")
    print(f"管理员特权 (Root):   {'是 (特权运行)' if os_info['is_root'] else '否 (普通用户受控运行)'}")
    print(f"运行环境:            {'WSL' if os_info['is_wsl'] else ('Container' if os_info['is_container'] else '物理机/常规VM')}")
    print(f"已就绪场景 (Profiles):{len(engine.profiles)} 个")
    print(f"原子模块清单:        {len(engine.modules)} 个")


def handle_profile_list(args, engine: ExecutionEngine):
    if args.json:
        print(json.dumps(engine.profiles, indent=2, ensure_ascii=False))
        return

    print("\033[1;32m=== 可用一键场景清单 (Profiles) ===\033[0m\n")
    for idx, p in enumerate(engine.profiles, 1):
        print(f" \033[33m[{idx:02d}]\033[0m \033[1m{p['id']}\033[0m — {p['name']}")
        print(f"      描述: {p['description']}")
        print(f"      包含模块: {', '.join(p['modules'])}\n")


def handle_profile_run(args, engine: ExecutionEngine):
    profile_id = args.profile_id
    dry_run = not args.apply

    try:
        plan = engine.create_plan(profile_id)
    except ValueError as e:
        print(f"\033[31m[错误] {str(e)}\033[0m", file=sys.stderr)
        sys.exit(1)

    if not args.json:
        mode_str = "\033[33m[DRY-RUN 模拟/预检模式]\033[0m" if dry_run else "\033[32m[APPLY 真实执行模式]\033[0m"
        print(f"\033[1;34m[*] 准备场景执行计划: {plan['profile_name']} (ID: {profile_id})\033[0m")
        print(f"[*] 模式: {mode_str}")
        print("[*] 规划步骤:")
        for idx, step in enumerate(plan["steps"], 1):
            print(f"    {idx}. [{step['risk_level']}] {step['name']} ({step['module_id']})")
        print()

    # Execute
    res = engine.execute_plan(plan, dry_run=dry_run, auto_approve=args.apply or dry_run)

    if args.json:
        print(json.dumps(res, indent=2, ensure_ascii=False))
        return

    print("\033[1;32m=== 执行结果报告 ===\033[0m")
    print(f"整体状态: {res['status'].upper()}")
    for step in res["steps"]:
        color = "\033[32m" if step["verified"] else "\033[31m"
        print(f"  {color}●\033[0m [{step['risk_level']}] {step['module_id']}: {step['message']}")

    if dry_run:
        print("\n\033[33m提示: 当前为模拟 (dry-run) 模式，未对系统做出任何更改。追加 `--apply` 参数以确认真实执行。\033[0m")


def interactive_menu(engine: ExecutionEngine):
    print_banner()
    handle_status(argparse.Namespace(json=False), engine)
    print("\n\033[1;33m请选择要执行的操作:\033[0m")
    for idx, p in enumerate(engine.profiles, 1):
        print(f"  {idx}. 一键部署: {p['name']} ({p['id']})")
    print("  0. 退出")

    try:
        choice = input("\n请输入选项编号 [0]: ").strip()
        if not choice or choice == "0":
            print("已退出。")
            return
        idx = int(choice)
        if 1 <= idx <= len(engine.profiles):
            target_profile = engine.profiles[idx - 1]
            args = argparse.Namespace(profile_id=target_profile["id"], apply=False, json=False)
            handle_profile_run(args, engine)
        else:
            print("\033[31m无效输入编号。\033[0m")
    except (ValueError, KeyboardInterrupt):
        print("\n操作已取消。")


def main():
    parser = argparse.ArgumentParser(
        description="CommonUserScripts (CUS) V2 — 全场景操作系统与脚本环境调度器"
    )
    subparsers = parser.add_subparsers(dest="command", help="子命令")

    # status
    p_status = subparsers.add_parser("status", help="查看当前操作系统与环境诊断状态")
    p_status.add_argument("--json", action="store_true", help="以 JSON 格式输出")

    # profile
    p_profile = subparsers.add_parser("profile", help="场景管理 (Profiles)")
    p_profile_subs = p_profile.add_subparsers(dest="profile_action", help="场景动作")

    p_list = p_profile_subs.add_parser("list", help="列出所有可用场景")
    p_list.add_argument("--json", action="store_true", help="以 JSON 格式输出")

    p_run = p_profile_subs.add_parser("run", help="执行指定应用场景")
    p_run.add_argument("profile_id", help="场景 ID (如: vps-init, ai-workstation)")
    p_run.add_argument("--apply", action="store_true", help="显式确认真实执行 (默认仅 dry-run 预检)")
    p_run.add_argument("--json", action="store_true", help="以 JSON 格式输出执行报告")

    args = parser.parse_args()
    engine = ExecutionEngine()

    if not args.command:
        interactive_menu(engine)
        return

    if args.command == "status":
        handle_status(args, engine)
    elif args.command == "profile":
        if args.profile_action == "list":
            handle_profile_list(args, engine)
        elif args.profile_action == "run":
            handle_profile_run(args, engine)
        else:
            p_profile.print_help()
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
