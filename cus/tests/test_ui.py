"""UI, layout, dashboard and console-loop tests.

Rendering is tested with fake host/snapshot data (no live machine);
the console loop is driven by scripted input; CLI compatibility is
checked through real subprocess calls.
"""
import io
import json
import os
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.cus.runtime import detect  # noqa: E402
from src.cus.ui import renderer as R  # noqa: E402
from src.cus.ui.dashboard import dashboard_data  # noqa: E402
from src.cus.ui.dashboard import render_system  # noqa: E402
from src.cus.ui.layout import display_width, pad, tier, truncate  # noqa: E402
from src.cus.ui.menu import Console, render_main_screen, run_console  # noqa: E402
from src.cus.ui.theme import Theme, color_enabled  # noqa: E402

HOST = {"system": "linux", "os_id": "debian",
        "os_pretty": "Debian GNU/Linux 12 (bookworm)", "arch": "x86_64",
        "manager": "apt", "is_root": True, "has_sudo": True,
        "python": "3.11.2", "termux": False}

SNAP = {"cpu_percent": 24.0, "cpu_cores": 2, "load1": 0.42,
        "memory": {"total_kb": 4194304, "used_kb": 2013266,
                   "percent": 48.0},
        "disk": {"path": "/", "total": 40 * 1024 ** 3,
                 "used": int(12.4 * 1024 ** 3), "percent": 31.0},
        "network": {"iface": "eth0", "rx_bps": 15.8 * 1024,
                    "tx_bps": 2.3 * 1024}}

NA_SNAP = {"cpu_percent": None, "cpu_cores": None, "load1": None,
           "memory": None, "disk": None,
           "network": {"iface": None, "rx_bps": None, "tx_bps": None}}


def scripted(answers):
    """input() replacement: yields answers, then EOF; exceptions raised."""
    it = iter(answers)

    def _input(prompt=""):
        try:
            value = next(it)
        except StopIteration:
            raise EOFError
        if isinstance(value, BaseException):
            raise value
        return value

    return _input


class LayoutTests(unittest.TestCase):
    def test_display_width(self):
        self.assertEqual(display_width("abc"), 3)
        self.assertEqual(display_width("中文"), 4)
        self.assertEqual(display_width("a中b"), 4)
        self.assertEqual(display_width("é"), 1)  # e + combining accent
        self.assertEqual(display_width("\x1b[36mab\x1b[0m"), 2)

    def test_truncate_keeps_whole_glyphs(self):
        self.assertEqual(truncate("abcdef", 4), "abc…")
        self.assertEqual(truncate("中文ab", 3), "中…")
        self.assertEqual(truncate("ab", 10), "ab")

    def test_pad_uses_display_width(self):
        self.assertEqual(pad("中", 4), "中  ")

    def test_tiers(self):
        self.assertEqual(tier(120), "wide")
        self.assertEqual(tier(100), "wide")
        self.assertEqual(tier(99), "standard")
        self.assertEqual(tier(70), "standard")
        self.assertEqual(tier(69), "compact")
        self.assertEqual(tier(40), "compact")
        self.assertEqual(tier(39), "minimal")


class ThemeTests(unittest.TestCase):
    def test_disabled_theme_is_plain(self):
        theme = Theme(enabled=False)
        self.assertEqual(theme.paint("x", "cyan"), "x")

    def test_enabled_theme_adds_ansi(self):
        theme = Theme(enabled=True)
        self.assertIn("\x1b[36m", theme.paint("x", "cyan"))

    def test_no_color_env_disables(self):
        os.environ["NO_COLOR"] = "1"
        try:
            self.assertFalse(color_enabled(io.StringIO()))
        finally:
            del os.environ["NO_COLOR"]

    def test_non_tty_stream_disables(self):
        self.assertFalse(color_enabled(io.StringIO()))


class RendererTests(unittest.TestCase):
    def test_format_bytes(self):
        self.assertEqual(R.format_bytes(0), "0 B")
        self.assertEqual(R.format_bytes(1023), "1023 B")
        self.assertEqual(R.format_bytes(1024), "1.0 KB")
        self.assertEqual(R.format_bytes(1536), "1.5 KB")
        self.assertEqual(R.format_bytes(5 * 1024 ** 3), "5.0 GB")
        self.assertEqual(R.format_bytes(None), "N/A")

    def test_format_rate(self):
        self.assertEqual(R.format_rate(10240), "10.0 KB/s")
        self.assertEqual(R.format_rate(None), "N/A")

    def test_format_pair(self):
        self.assertEqual(
            R.format_pair(int(1.9 * 1024 ** 3), int(4.0 * 1024 ** 3)),
            "1.9 / 4.0 GiB")
        self.assertEqual(R.format_pair(None, None), "N/A")

    def test_progress_bar(self):
        self.assertEqual(R.progress_bar(50.0, 10, True), "█████░░░░░")
        self.assertEqual(R.progress_bar(0.0, 10, True), "░░░░░░░░░░")
        self.assertEqual(R.progress_bar(100.0, 10, True), "██████████")
        self.assertEqual(R.progress_bar(None, 10, True), "░░░░░░░░░░")
        self.assertEqual(R.progress_bar(50.0, 10, False), "#####-----")

    def test_box_line_width(self):
        from src.cus.ui.layout import display_width as dw
        self.assertEqual(dw(R.box_line("ab", 10, True)), 10)
        self.assertEqual(dw(R.box_line("ab", 10, False)), 10)


class DashboardRenderTests(unittest.TestCase):
    def test_two_column_system(self):
        text = "\n".join(render_system(HOST, SNAP, 78, True, Theme(False)))
        self.assertIn("Debian GNU/Linux 12", text)
        self.assertIn("24%", text)
        self.assertIn("1.9 / 4.0 GiB", text)
        self.assertIn("12.4 / 40.0 GiB", text)
        self.assertIn("eth0", text)
        self.assertIn("15.8 KB/s", text)
        self.assertIn("2.3 KB/s", text)

    def test_compact_system(self):
        text = "\n".join(render_system(HOST, SNAP, 58, True, Theme(False)))
        self.assertIn("CPU", text)
        self.assertIn("24%", text)

    def test_minimal_system(self):
        text = "\n".join(render_system(HOST, SNAP, 30, True, Theme(False)))
        self.assertIn("CPU 24%", text)
        self.assertNotIn("█", text)

    def test_na_snapshot_never_crashes(self):
        for inner in (78, 58, 30):
            text = "\n".join(
                render_system(HOST, NA_SNAP, inner, True, Theme(False)))
            self.assertIn("N/A", text)

    def test_main_screen_widths(self):
        theme = Theme(False)
        for width in (120, 80):
            lines = render_main_screen(HOST, SNAP, width, True, theme)
            joined = "\n".join(lines)
            self.assertIn("CUS CONSOLE", joined)
            self.assertIn("v2.1", joined)
            self.assertIn("场景部署", joined)
            self.assertIn("8 个场景", joined)
            self.assertIn("系统管理", joined)
            self.assertNotIn("ss://", joined)
            self.assertNotIn("password", joined.lower())
        # Compact and minimal tiers drop the right-hand hints.
        for width in (60, 40, 30):
            joined = "\n".join(render_main_screen(HOST, SNAP, width, True,
                                                   theme))
            self.assertIn("CUS CONSOLE", joined)
            self.assertIn("v2.1", joined)
            self.assertIn("场景部署", joined)
            self.assertIn("系统管理", joined)
            self.assertNotIn("ss://", joined)

    def test_main_screen_ascii_fallback(self):
        lines = render_main_screen(HOST, SNAP, 80, False, Theme(False))
        joined = "\n".join(lines)
        self.assertIn("+", joined.splitlines()[0])
        self.assertNotIn("╭", joined)
        self.assertNotIn("█", joined)

    def test_main_screen_no_ansi_when_disabled(self):
        lines = render_main_screen(HOST, SNAP, 80, True, Theme(False))
        self.assertNotIn("\x1b", "\n".join(lines))

    def test_dashboard_data_shape(self):
        data = dashboard_data(HOST, SNAP)
        self.assertEqual(set(data),
                         {"host", "cpu", "memory", "disk", "network",
                          "collected_at_utc"})
        self.assertEqual(data["cpu"]["percent"], 24.0)
        self.assertEqual(data["network"]["iface"], "eth0")


class ConsoleTests(unittest.TestCase):
    def run_console(self, answers, width=80):
        out = io.StringIO()
        code = run_console(detect(), input_fn=scripted(answers), out=out,
                           err=io.StringIO(), interval=0, width=width)
        return code, out.getvalue()

    def test_invalid_input_then_exit(self):
        code, out = self.run_console(["9", "0"])
        self.assertEqual(code, 0)
        self.assertIn("Unknown selection", out)

    def test_profile_list_and_back(self):
        code, out = self.run_console(["1", "0", "0"])
        self.assertEqual(code, 0)
        self.assertIn("新 VPS 最小初始化", out)
        self.assertIn("minimal-vps", out)

    def test_scenario_detail_and_plan(self):
        code, out = self.run_console(["1", "1", "p", "b", "b", "0", "0"])
        self.assertEqual(code, 0)
        self.assertIn("ID: minimal-vps", out)
        self.assertIn("SCENARIO: 新 VPS 最小初始化 (no changes)", out)

    def test_scenario_detect_refresh(self):
        code, out = self.run_console(["1", "1", "d", "b", "0", "0"])
        self.assertEqual(code, 0)
        self.assertIn("ID: minimal-vps", out)

    def test_module_list_and_detail(self):
        code, out = self.run_console(["2", "1", "b", "0", "0"])
        self.assertEqual(code, 0)
        self.assertIn("── 开发环境 ──", out)
        self.assertIn("ID:", out)
        self.assertIn("[B] 返回", out)

    def test_tools_version(self):
        code, out = self.run_console(["7", "3", "b", "0", "0"])
        self.assertEqual(code, 0)
        self.assertIn("2.1.0", out)

    def test_tools_doctor(self):
        code, out = self.run_console(["7", "1", "b", "0", "0"])
        self.assertEqual(code, 0)
        self.assertIn("host diagnostics", out)

    def test_help_page(self):
        code, out = self.run_console(["h", "", "0"])
        self.assertEqual(code, 0)
        self.assertIn("导航", out)

    def test_enter_exits_main_menu(self):
        code, _ = self.run_console([""])
        self.assertEqual(code, 0)

    def test_q_exits(self):
        code, _ = self.run_console(["q"])
        self.assertEqual(code, 0)

    def test_eof_exits_cleanly(self):
        code, _ = self.run_console([])
        self.assertEqual(code, 0)

    def test_ctrl_c_exits_130(self):
        code, out = self.run_console([KeyboardInterrupt()])
        self.assertEqual(code, 130)
        self.assertIn("Interrupted", out)

    def test_refresh_then_exit(self):
        code, _ = self.run_console(["r", "0"])
        self.assertEqual(code, 0)


class CliCompatTests(unittest.TestCase):
    def run_cli(self, *args, stdin=None):
        # DEVNULL stdin: the menu must see a non-TTY even when the test
        # runner itself runs inside a terminal.
        return subprocess.run(
            [sys.executable, str(ROOT / "cus.py"), *args],
            capture_output=True, text=True,
            stdin=subprocess.DEVNULL if stdin is None else stdin)

    def test_json_list_unchanged(self):
        p = self.run_cli("--json", "list")
        self.assertEqual(p.returncode, 0)
        data = json.loads(p.stdout)
        self.assertEqual(len(data), 50)
        self.assertEqual(set(data[0]),
                         {"id", "name", "kind", "status", "detail",
                          "commands", "install_ready"})

    def test_json_list_postfix_flag(self):
        p = self.run_cli("list", "--json")
        self.assertEqual(p.returncode, 0)
        self.assertEqual(len(json.loads(p.stdout)), 50)

    def test_json_plan_unchanged(self):
        p = self.run_cli("--json", "plan", "ai-agent")
        self.assertEqual(p.returncode, 0)
        data = json.loads(p.stdout)
        self.assertIn("items", data)
        self.assertIn("plan-only", data["mode"])

    def test_dashboard_json_prefix_and_postfix(self):
        for args in (("--json", "dashboard"), ("dashboard", "--json")):
            p = self.run_cli(*args)
            self.assertEqual(p.returncode, 0, args)
            self.assertNotIn("\x1b", p.stdout)
            data = json.loads(p.stdout)
            self.assertEqual(set(data),
                             {"host", "cpu", "memory", "disk", "network",
                              "collected_at_utc"})
            self.assertIn("os_pretty", data["host"])

    def test_dashboard_text_no_ansi_when_piped(self):
        p = self.run_cli("dashboard")
        self.assertEqual(p.returncode, 0)
        self.assertNotIn("\x1b", p.stdout)
        self.assertIn("CUS CONSOLE", p.stdout)
        self.assertIn("SYSTEM", p.stdout)
        self.assertNotIn("ss://", p.stdout)

    def test_menu_requires_terminal(self):
        p = self.run_cli()
        self.assertEqual(p.returncode, 2)
        self.assertIn("requires a terminal", p.stderr)

    def test_version(self):
        p = self.run_cli("version")
        self.assertEqual(p.stdout.strip(), "2.1.0")


if __name__ == "__main__":
    unittest.main()
