"""Color accents for the CUS console (group palette, threshold bars,
header/footer painting, SCENES/MODULES counts).

Color is painted only after layout (see paint_header_lines), so tests
compare colored output against the plain render after stripping ANSI:
the layout must be identical with colors on or off.
"""
import io
import unittest
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.cus.catalog import modules, profiles  # noqa: E402
from src.cus.ui.dashboard import paint_system_lines  # noqa: E402
from src.cus.ui.dashboard import render_system  # noqa: E402
from src.cus.ui.menu import render_main_screen  # noqa: E402
from src.cus.ui.theme import (GROUP_STYLES, group_style,  # noqa: E402
                              strip_controls, threshold_style)
from src.cus.ui.theme import Theme  # noqa: E402

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

COUNTS = (len(profiles()), len(modules()))


def high_snap(pct):
    """Snapshot with CPU/RAM/DISK all at pct%."""
    return {"cpu_percent": float(pct), "cpu_cores": 2, "load1": 1.0,
            "memory": {"total_kb": 1000, "used_kb": int(1000 * pct / 100),
                       "percent": float(pct)},
            "disk": {"path": "/", "total": 1000,
                     "used": int(1000 * pct / 100),
                     "percent": float(pct)},
            "network": {"iface": "eth0", "rx_bps": 0, "tx_bps": 0}}


class PaletteTests(unittest.TestCase):
    def test_group_palette_mapping(self):
        self.assertEqual(GROUP_STYLES, {
            "01": "green", "02": "blue", "03": "magenta",
            "04": "yellow", "05": "cyan", "06": "bright_green",
            "07": "gray",
        })

    def test_group_style_lookup(self):
        self.assertEqual(group_style("01"), "green")
        self.assertEqual(group_style("02"), "blue")
        self.assertEqual(group_style("03"), "magenta")
        self.assertEqual(group_style("04"), "yellow")
        self.assertEqual(group_style("05"), "cyan")
        self.assertEqual(group_style("06"), "bright_green")
        self.assertEqual(group_style("07"), "gray")
        self.assertIsNone(group_style("00"))
        self.assertIsNone(group_style("99"))

    def test_threshold_boundaries(self):
        self.assertEqual(threshold_style(0), "green")
        self.assertEqual(threshold_style(59), "green")
        self.assertEqual(threshold_style(59.9), "green")
        self.assertEqual(threshold_style(60), "yellow")
        self.assertEqual(threshold_style(85), "yellow")
        self.assertEqual(threshold_style(85.9), "red")  # >85 is red
        self.assertEqual(threshold_style(86), "red")
        self.assertEqual(threshold_style(100), "red")
        self.assertIsNone(threshold_style(None))


class MainScreenColorTests(unittest.TestCase):
    def colored(self, snap=None, width=80):
        return "\n".join(render_main_screen(
            HOST, snap or SNAP, width, True, Theme(True)))

    def test_group_accents(self):
        text = self.colored()
        # Number + bullet in each group's accent color.
        self.assertIn("\x1b[32m01\x1b[0m", text)   # green
        self.assertIn("\x1b[34m02\x1b[0m", text)   # blue
        self.assertIn("\x1b[35m03\x1b[0m", text)   # magenta
        self.assertIn("\x1b[33m04\x1b[0m", text)   # yellow
        self.assertIn("\x1b[36m05\x1b[0m", text)   # cyan
        self.assertIn("\x1b[92m06\x1b[0m", text)   # bright green
        self.assertIn("\x1b[90m07\x1b[0m", text)   # gray
        self.assertIn("\x1b[32m◈\x1b[0m", text)
        self.assertIn("\x1b[34m◈\x1b[0m", text)
        self.assertIn("\x1b[35m◈\x1b[0m", text)
        # Names bright white, hints gray, exit row gray, no accent on it.
        self.assertIn("\x1b[1;37m场景部署\x1b[0m", text)
        self.assertIn("\x1b[90m8 个场景\x1b[0m", text)
        self.assertIn("\x1b[90m  00  退出\x1b[0m", text)
        self.assertNotIn("\x1b[32m00\x1b[0m", text)

    def test_header_colors(self):
        text = self.colored()
        self.assertIn("\x1b[1;37mCUS\x1b[0m", text)
        self.assertIn("\x1b[32m Console\x1b[0m", text)
        self.assertIn("\x1b[90mv2.1\x1b[0m", text)
        self.assertIn("\x1b[90mCommonUserScripts · Universal System "
                      "Toolkit\x1b[0m", text)

    def test_footer_colors(self):
        text = self.colored()
        self.assertIn("\x1b[32m●\x1b[0m Ready", text)
        self.assertIn("\x1b[90m· 无新增依赖\x1b[0m", text)
        self.assertIn("[0] Exit   [R] Refresh   [H] Help", text)

    def test_scenes_modules_row_is_real(self):
        # Strip ANSI first: painting wraps SCENES/8 in separate spans.
        text = strip_controls(self.colored())
        self.assertIn("SCENES", text)
        self.assertIn("MODULES", text)
        self.assertIn(f"SCENES {COUNTS[0]}", text)
        self.assertIn(f"MODULES {COUNTS[1]}", text)
        self.assertEqual(COUNTS, (8, 50))

    def test_threshold_colors(self):
        low = self.colored()
        self.assertIn("\x1b[32m██░░░░░░░░\x1b[0m", low)  # CPU 24% green
        mid = self.colored(high_snap(70))
        self.assertIn("\x1b[33m███████░░░\x1b[0m", mid)  # 70% yellow
        high = self.colored(high_snap(90))
        self.assertIn("\x1b[31m█████████░\x1b[0m", high)  # 90% red
        self.assertIn("\x1b[31m90%\x1b[0m", high)

    def test_color_does_not_change_layout(self):
        colored = self.colored()
        plain = "\n".join(render_main_screen(
            HOST, SNAP, 80, True, Theme(False)))
        self.assertEqual(strip_controls(colored), strip_controls(plain))

    def test_disabled_theme_has_no_ansi(self):
        plain = "\n".join(render_main_screen(
            HOST, SNAP, 80, True, Theme(False)))
        self.assertNotIn("\x1b", plain)


class SystemPaintTests(unittest.TestCase):
    def painted(self, snap, counts=COUNTS, width=78):
        rows = render_system(HOST, snap, width, True, Theme(False), counts)
        return paint_system_lines(rows, HOST, snap, Theme(True), True,
                                  counts)

    def test_labels_gray_values_bright(self):
        text = "\n".join(self.painted(SNAP))
        self.assertIn("\x1b[90mOS\x1b[0m", text)
        self.assertIn("\x1b[1;37mDebian GNU/Linux 12 (bookworm)\x1b[0m",
                      text)
        self.assertIn("\x1b[90mARCH\x1b[0m", text)
        self.assertIn("\x1b[1;37mx86_64\x1b[0m", text)
        self.assertIn("\x1b[90mNET\x1b[0m", text)
        self.assertIn("\x1b[1;37meth0\x1b[0m", text)

    def test_none_percent_has_no_threshold_color(self):
        na = {"cpu_percent": None, "cpu_cores": None, "load1": None,
              "memory": None, "disk": None,
              "network": {"iface": None, "rx_bps": None, "tx_bps": None}}
        text = "\n".join(self.painted(na))
        self.assertIn("N/A", text)
        self.assertNotIn("\x1b[32m", text)
        self.assertNotIn("\x1b[33m", text)
        self.assertNotIn("\x1b[31m", text)

    def test_compact_and_minimal_rows_painted(self):
        compact = "\n".join(self.painted(SNAP, width=58))
        self.assertIn("\x1b[90mCPU\x1b[0m", compact)
        self.assertIn("\x1b[32m", compact)  # 24% bar green
        minimal = "\n".join(self.painted(SNAP, width=30))
        self.assertIn("\x1b[90mCPU\x1b[0m", minimal)
        self.assertIn("\x1b[32m24%\x1b[0m", minimal)

    def test_counts_row_without_counts_is_absent(self):
        rows = render_system(HOST, SNAP, 78, True, Theme(False))
        self.assertNotIn("SCENES", "\n".join(rows))


if __name__ == "__main__":
    unittest.main()
