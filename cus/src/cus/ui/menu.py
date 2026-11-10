"""Looping multi-level console.

Navigation: 0/B back (main menu exits), R refresh, H help, Q quit,
Ctrl+C safe exit, Enter on the main menu exits, invalid input re-prompts.
The console only plans and detects; it never installs anything itself.
"""
from __future__ import annotations

import sys

from ..catalog import modules, plan_module, profiles, status
from ..runtime import state_path
from . import renderer as R
from .dashboard import (format_plan, paint_header_lines, render_doctor,
                        render_header, render_system, short_version)
from .layout import display_width, pad, tier, terminal_size, truncate
from .layout import use_unicode
from ..monitor import collect
from .theme import Theme

# Console groups, built from the real `category` field in data/modules.json.
# (group, subtitle hint, kind, categories)
GROUPS = [
    ("01", "场景部署", None, "profiles", None),
    ("02", "开发环境", "Python / Node / JDK / Go", "categories",
     ["基础工具", "开发基础", "开发环境", "移动开发", "数据库", "Web 服务"]),
    ("03", "AI Agent \u00b7 API 网关", "Claude / Codex / Gemini", "categories",
     ["AI Agent", "API 网关"]),
    ("04", "网络服务", "SS / WireGuard / Tailscale", "categories",
     ["网络服务", "云平台"]),
    ("05", "容器 \u00b7 自动化", "Docker / Git Sync / Cron", "categories",
     ["容器", "自动化"]),
    ("06", "系统管理 \u00b7 维护", "清理 / 诊断 / 备份", "categories",
     ["系统管理", "维护", "监控"]),
    ("07", "历史记录与设置", "日志 / 诊断 / 版本", "tools", None),
]

TOOLS = [
    ("01", "系统诊断", "doctor"),
    ("02", "历史记录", "history"),
    ("03", "版本信息", "version"),
]


def group_modules(categories) -> list:
    """Modules of the given categories, grouped in category order
    (catalog order inside each category). The catalog lists modules
    interleaved across categories, so grouping here is what keeps each
    category header appearing exactly once."""
    by_cat: dict[str, list] = {}
    for mod in modules().values():
        by_cat.setdefault(mod.get("category"), []).append(mod)
    out = []
    for cat in categories:
        out.extend(by_cat.get(cat, []))
    return out


def render_main_screen(host: dict, snap: dict, width: int,
                       unicode_mode: bool, theme=None) -> list[str]:
    """Full main screen. Pure: no I/O, no sampling."""
    if tier(width) == "minimal":
        return _main_minimal(host, snap, width, unicode_mode, theme)
    box_w = max(38, min(width, 98))
    inner = box_w - 2
    lines = [R.box_top(box_w, unicode_mode)]
    header = [R.box_line(line, box_w, unicode_mode)
              for line in render_header(inner, unicode_mode)]
    lines += paint_header_lines(header, theme, unicode_mode)
    lines.append(R.section_rule(box_w, "SYSTEM", unicode_mode, theme))
    for row in render_system(host, snap, inner, unicode_mode, theme):
        lines.append(R.box_line(row, box_w, unicode_mode))
    lines.append(R.section_rule(box_w, "WORKSPACE", unicode_mode, theme))
    lines.append(R.box_line("", box_w, unicode_mode))
    glyph = R.glyphs(unicode_mode)
    compact = tier(width) == "compact"
    for gid, name, hint, kind, _ in GROUPS:
        if kind == "profiles":
            hint = f"{len(profiles())} 个场景"
        left = f"  {gid}  {glyph['bullet']}  {name}"
        text = left if compact else R.two_columns(left, hint or "", inner)
        lines.append(R.box_line(text, box_w, unicode_mode))
    lines.append(R.box_line("", box_w, unicode_mode))
    lines.append(R.box_line("  00  退出", box_w, unicode_mode))
    lines.append(R.box_line("", box_w, unicode_mode))
    lines.append(R.plain_rule(box_w, unicode_mode))
    footer = R.two_columns("  [0] Exit   [R] Refresh   [H] Help",
                           f"{glyph['dot']} Ready", inner)
    lines.append(R.box_line(footer, box_w, unicode_mode))
    lines.append(R.box_bottom(box_w, unicode_mode))
    return lines


def _main_minimal(host: dict, snap: dict, width: int,
                  unicode_mode: bool, theme=None) -> list[str]:
    lines = ["CUS CONSOLE v" + short_version()]
    lines += render_system(host, snap, width, unicode_mode, theme)
    lines.append("")
    for gid, name, _hint, _kind, _cats in GROUPS:
        lines.append(f" {gid} {name}")
    lines.append(" 00 退出")
    lines.append("")
    lines.append("[0] Exit  [R] Refresh  [H] Help")
    return lines


class _ExitConsole(Exception):
    """Internal: EOF on stdin means leave the console cleanly."""

    def __init__(self, code: int = 0):
        super().__init__(code)
        self.code = code


class Console:
    """Stateful console; input/output are injectable for tests."""

    def __init__(self, host: dict, input_fn=None, out=None, err=None,
                 interval: float = 0.2, width: int | None = None):
        self.host = host
        self.input_fn = input_fn if input_fn is not None else input
        self.out = out if out is not None else sys.stdout
        self.err = err if err is not None else sys.stderr
        self.interval = interval
        self._width_override = width
        self.snap: dict | None = None
        self.theme = Theme(stream=self.out)
        self.unicode_mode = use_unicode(self.out)
        self.width = width if width is not None else terminal_size()[0]
        self._mods = modules()
        self._profiles = profiles()

    # ------------------------------------------------------------ basics ---
    def emit(self, text: str = "") -> None:
        # Safe print: an old ASCII-only terminal degrades (replace)
        # instead of crashing on UnicodeEncodeError.
        R.safe_print(text, stream=self.out)

    def refresh(self) -> None:
        self.snap = collect(interval=self.interval)
        if self._width_override is None:
            self.width = terminal_size()[0]
        self.unicode_mode = use_unicode(self.out)
        self.theme = Theme(stream=self.out)

    def prompt(self, text: str) -> str:
        try:
            return self.input_fn(text)
        except EOFError:
            raise _ExitConsole(0)
        except KeyboardInterrupt:
            raise

    def box_width(self) -> int:
        return max(38, min(self.width, 98))

    def _boxed(self, title: str, body: list[str]) -> list[str]:
        """Wrap body lines in a box with a title header row."""
        box_w = self.box_width()
        inner = box_w - 2
        plain_title = "  " + title
        lines = [R.box_top(box_w, self.unicode_mode),
                 R.box_line(pad(truncate(plain_title, inner), inner),
                            box_w, self.unicode_mode),
                 R.plain_rule(box_w, self.unicode_mode)]
        for row in body:
            lines.append(R.box_line(row, box_w, self.unicode_mode))
        lines.append(R.box_bottom(box_w, self.unicode_mode))
        if self.theme is not None:
            # Paint after boxing: strip_controls in truncate()/pad()
            # would otherwise eat our own ANSI codes. No-op when the
            # title was truncated away.
            lines[1] = lines[1].replace(
                plain_title, self.theme.heading(plain_title), 1)
        return lines

    def _show_boxed(self, title: str, body: list[str]) -> None:
        for line in self._boxed(title, body):
            self.emit(line)

    def _wait_back(self) -> None:
        self.prompt("[B] 返回: ")

    # ------------------------------------------------------------ pages ----
    def run(self) -> int:
        try:
            self.refresh()
            return self.main_menu()
        except _ExitConsole as exc:
            return exc.code
        except KeyboardInterrupt:
            self.emit("")
            self.emit("Interrupted; leaving safely.")
            return 130

    def main_menu(self) -> int:
        while True:
            for line in render_main_screen(
                    self.host, self.snap or {}, self.width,
                    self.unicode_mode, self.theme):
                self.emit(line)
            raw = self.prompt("请选择操作 [0-7]: ")
            choice = raw.strip().lower()
            if choice in {"", "0", "00", "q", "exit"}:
                self.emit("Exited without cleanup or other side effects.")
                return 0
            if choice == "r":
                self.refresh()
                continue
            if choice == "h":
                self.help_page()
                continue
            if choice.isdigit() and 1 <= int(choice) <= len(GROUPS):
                code = self.group_page(GROUPS[int(choice) - 1])
                if code is not None:
                    return code
                continue
            self.emit("Unknown selection; please retry.")

    def group_page(self, group) -> int | None:
        """Return None to go back to the main menu, 0 to exit the console."""
        _gid, name, _hint, kind, cats = group
        while True:
            if kind == "profiles":
                items = list(self._profiles.values())
                body = self._list_rows(
                    [(i, p["name"], p["id"]) for i, p in enumerate(items, 1)])
                body.append("")
                body.append("  00  返回")
                self._show_boxed(name, body)
                raw = self.prompt("请选择场景 [0 返回]: ")
                choice = raw.strip().lower()
                if choice in {"0", "00", "b"}:
                    return None
                if choice == "r":
                    self.refresh()
                    continue
                if choice == "h":
                    self.help_page()
                    continue
                if choice.isdigit() and 1 <= int(choice) <= len(items):
                    code = self.scenario_detail(items[int(choice) - 1])
                    if code is not None:
                        return code
                    continue
                self.emit("Unknown selection; please retry.")
            elif kind == "tools":
                body = self._list_rows(
                    [(i, t[1], "") for i, t in enumerate(TOOLS, 1)])
                body.append("")
                body.append("  00  返回")
                self._show_boxed(name, body)
                raw = self.prompt("请选择 [0 返回]: ")
                choice = raw.strip().lower()
                if choice in {"0", "00", "b"}:
                    return None
                if choice == "r":
                    self.refresh()
                    continue
                if choice == "h":
                    self.help_page()
                    continue
                if choice.isdigit() and 1 <= int(choice) <= len(TOOLS):
                    code = self.tool_page(TOOLS[int(choice) - 1])
                    if code is not None:
                        return code
                    continue
                self.emit("Unknown selection; please retry.")
            else:
                mods = group_modules(cats)
                body: list[str] = []
                current_cat = None
                for index, mod in enumerate(mods, 1):
                    cat = mod.get("category", "")
                    if cat != current_cat:
                        current_cat = cat
                        body.append(f"── {cat} ──")
                    state, _ = status(mod, self.host)
                    body.append(f" {index:2d}  {mod['name']} [{state}]")
                body.append("")
                body.append("  planned = 仅可预览计划，尚未实现安装；"
                            "available = 可用包管理器安装。")
                body.append("  00  返回")
                self._show_boxed(name, body)
                raw = self.prompt("请选择模块 [0 返回]: ")
                choice = raw.strip().lower()
                if choice in {"0", "00", "b"}:
                    return None
                if choice == "r":
                    self.refresh()
                    continue
                if choice == "h":
                    self.help_page()
                    continue
                if choice.isdigit() and 1 <= int(choice) <= len(mods):
                    code = self.module_detail(mods[int(choice) - 1])
                    if code is not None:
                        return code
                    continue
                self.emit("Unknown selection; please retry.")

    def _list_rows(self, entries) -> list[str]:
        """Numbered two-column rows: (number, name, right-aligned text)."""
        inner = self.box_width() - 2
        rows = []
        for num, name, right in entries:
            left = f" {num:2d}  {name}"
            if inner >= 50 and right:
                rows.append(R.two_columns(left, right, inner))
            else:
                suffix = f" ({right})" if right else ""
                rows.append(truncate(f"{left}{suffix}", inner))
        return rows

    def scenario_detail(self, profile: dict) -> int | None:
        """Scenario detail: [P] plan, [D] detect, [B] back."""
        while True:
            body = [f"  ID: {profile['id']}", ""]
            body.append("  依赖模块:")
            for index, mid in enumerate(profile["modules"], 1):
                mod = self._mods.get(mid)
                if mod is None:
                    body.append(f" {index:2d}  {mid} [unknown]")
                    continue
                state, _ = status(mod, self.host)
                body.append(f" {index:2d}  {mod['name']} [{state}]")
            body.append("")
            body.append(" [P] 预览计划   [D] 检测状态   [B] 返回")
            self._show_boxed(profile["name"], body)
            raw = self.prompt("请选择 [P/D/B]: ")
            choice = raw.strip().lower()
            if choice in {"b", "0", "00"}:
                return None
            if choice == "p":
                self.emit(f"SCENARIO: {profile['name']} (no changes)")
                for mid in profile["modules"]:
                    self.emit(format_plan(plan_module(mid, self.host)))
                self._wait_back()
                continue
            if choice == "d":
                self.refresh()
                continue
            if choice == "r":
                self.refresh()
                continue
            if choice == "h":
                self.help_page()
                continue
            self.emit("Unknown selection; please retry.")

    def module_detail(self, mod: dict) -> int | None:
        """One module: plan text + the real CLI install hint (no execution)."""
        plan = plan_module(mod["id"], self.host)
        body = [f"  ID: {mod['id']} · {mod['kind']} · {plan['status']}", ""]
        body += format_plan(plan).splitlines()
        body.append("")
        if plan["install_ready"]:
            body.append(f"安装方式: cus install {mod['id']} --apply")
            body.append("注意: --apply 执行包管理器命令并做能力验证，"
                        "验证通过不等于安装成功。")
        else:
            body.append("未实现: 仅可预览计划，见 docs/ROADMAP.md。")
        body.append("")
        body.append(" [B] 返回")
        self._show_boxed(mod["name"], body)
        try:
            self.prompt("[B] 返回: ")
        except _ExitConsole as exc:
            return exc.code
        return None

    def tool_page(self, tool) -> int | None:
        _tid, name, kind = tool
        if kind == "doctor":
            for line in render_doctor(self.host):
                self.emit(line)
        elif kind == "history":
            path = state_path()
            lines = (path.read_text(encoding="utf-8").splitlines()[-30:]
                     if path.exists() else [])
            self.emit("\n".join(lines) if lines else
                      "No executed installation actions have been recorded.")
        elif kind == "version":
            from .. import __version__
            self.emit(f"CommonUserScripts {__version__}")
            self.emit("Console v" + short_version())
        try:
            self._wait_back()
        except _ExitConsole as exc:
            return exc.code
        return None

    def help_page(self) -> None:
        lines = [
            "导航:",
            "  0 / B   返回上一级（主菜单则退出）",
            "  R       刷新系统数据",
            "  H       打开本帮助",
            "  Q       退出",
            "  Enter   主菜单默认退出",
            "",
            "说明:",
            "  · 本控制台只做计划与检测；安装需在终端运行",
            "    cus install <模块> --apply。",
            "  · --apply 执行包管理器命令并做能力验证，",
            "    验证通过不等于安装成功。",
            "  · 不会显示或记录任何密码、密钥与订阅链接。",
        ]
        self._show_boxed("帮助", lines)
        try:
            self.prompt("按任意键返回: ")
        except _ExitConsole:
            raise


def run_console(host: dict, input_fn=None, out=None, err=None,
                interval: float = 0.2, width: int | None = None) -> int:
    """Entry point for `cus` / `cus menu`."""
    console = Console(host, input_fn=input_fn, out=out, err=err,
                      interval=interval, width=width)
    return console.run()
