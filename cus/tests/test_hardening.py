"""Hardening tests (Codex audit ports): guards, sanitization, safe print.

Fake /proc trees and injected fakes only. Windows/macOS paths are
exercised through injected ctypes/subprocess fakes (no real machines);
real Windows/macOS behaviour is NOT VERIFIED here.
"""
import ctypes
import io
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.cus import monitor  # noqa: E402
from src.cus.ui import renderer as R  # noqa: E402
from src.cus.ui.layout import display_width, pad, truncate  # noqa: E402
from src.cus.ui.menu import Console  # noqa: E402
from src.cus.ui.theme import color_enabled, strip_controls  # noqa: E402

STAT_1 = "cpu  100 0 100 700 100 0 0 0 0 0\n"
STAT_NEG = "cpu  100 -5 100 700 100 0 0 0 0 0\n"

ROUTE_DEFAULT = (
    "Iface\tDestination\tGateway \tFlags\tRefCnt\tUse\tMetric\tMask\t\tMTU\tWindow\tIRTT\n"
    "eth0\t00000000\t0102A8C0\t0003\t0\t0\t100\t00000000\t0\t0\t0\n"
    "wlan0\t00000000\t0102A8C0\t0003\t0\t0\t600\t00000000\t0\t0\t0\n"
    "eth0\t0002A8C0\t00000000\t0001\t0\t0\t100\t00FFFFFF\t0\t0\t0\n"
)

ROUTE_NO_DEFAULT = (
    "Iface\tDestination\tGateway \tFlags\tRefCnt\tUse\tMetric\tMask\t\tMTU\tWindow\tIRTT\n"
    "eth0\t0002A8C0\t00000000\t0001\t0\t0\t100\t00FFFFFF\t0\t0\t0\n"
)

DEV_HEAD = (
    "Inter-|   Receive                                                |  Transmit\n"
    " face |bytes    packets errs drop fifo frame compressed multicast|bytes    packets errs drop fifo colls carrier compressed\n"
)

DEV_1 = DEV_HEAD + (
    "  eth0: 100000 100 0 0 0 0 0 0 200000 200 0 0 0 0 0 0\n"
    "    lo: 5000 50 0 0 0 0 0 0 5000 50 0 0 0 0 0 0\n"
    " wlan0: 3000 30 0 0 0 0 0 0 4000 40 0 0 0 0 0 0\n"
)

DEV_RESET = DEV_HEAD + (
    "  eth0: 50000 100 0 0 0 0 0 0 100000 200 0 0 0 0 0 0\n"
    "    lo: 5000 50 0 0 0 0 0 0 5000 50 0 0 0 0 0 0\n"
    " wlan0: 3000 30 0 0 0 0 0 0 4000 40 0 0 0 0 0 0\n"
)

DEV_RX_RESET = DEV_HEAD + (
    "  eth0: 50000 100 0 0 0 0 0 0 201000 200 0 0 0 0 0 0\n"
    "    lo: 5000 50 0 0 0 0 0 0 5000 50 0 0 0 0 0 0\n"
    " wlan0: 3000 30 0 0 0 0 0 0 4000 40 0 0 0 0 0 0\n"
)

HOST = {"system": "linux", "os_id": "debian",
        "os_pretty": "Debian GNU/Linux 12 (bookworm)", "arch": "x86_64",
        "manager": "apt", "is_root": True, "has_sudo": True,
        "python": "3.11.2", "termux": False}


class FakeProc(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / "net").mkdir()
        self.write("stat", STAT_1)
        self.write("net/route", ROUTE_NO_DEFAULT)
        self.write("net/dev", DEV_1)

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, rel, text):
        (self.root / rel).write_text(text, encoding="utf-8")


class CpuGuardTests(FakeProc):
    def test_cpu_times_rejects_negative_field(self):
        self.write("stat", STAT_NEG)
        self.assertIsNone(monitor.cpu_times(self.root))

    def test_cpu_percent_none_when_idle_exceeds_total(self):
        # idle delta 150 > total delta 100: impossible, must be N/A.
        self.assertIsNone(monitor.cpu_percent((1000, 800), (1100, 950)))
        # idle delta == total delta is still valid (0% usage).
        self.assertAlmostEqual(
            monitor.cpu_percent((1000, 800), (1100, 900)), 0.0)


class PickIfaceTests(FakeProc):
    def setUp(self):
        super().setUp()
        self.sysroot = Path(self.tmp.name) / "sys"
        for iface in ("eth0", "wlan0"):
            (self.sysroot / "class" / "net" / iface).mkdir(parents=True)

    def _operstate(self, iface, state):
        (self.sysroot / "class" / "net" / iface / "operstate").write_text(
            state, encoding="utf-8")

    def test_up_interface_preferred_over_name_order(self):
        self._operstate("eth0", "down\n")
        self._operstate("wlan0", "up\n")
        self.assertEqual(monitor.pick_iface(self.root, self.sysroot), "wlan0")

    def test_name_order_when_none_up(self):
        self._operstate("eth0", "down\n")
        self._operstate("wlan0", "down\n")
        self.assertEqual(monitor.pick_iface(self.root, self.sysroot), "eth0")

    def test_default_route_still_wins(self):
        self.write("net/route", ROUTE_DEFAULT)
        self._operstate("eth0", "down\n")
        self._operstate("wlan0", "up\n")
        self.assertEqual(monitor.pick_iface(self.root, self.sysroot), "eth0")


class RateGuardTests(FakeProc):
    def _collect_with_dev(self, dev_text):
        def mutating_sleep(_seconds):
            self.write("net/dev", dev_text)

        times = iter([1000.0, 1000.2])
        return monitor.collect(
            interval=0.2, proc_root=self.root,
            sleep=mutating_sleep, monotonic=lambda: next(times))

    def test_counter_reset_is_na_not_zero(self):
        snap = self._collect_with_dev(DEV_RESET)
        self.assertEqual(snap["network"]["iface"], "eth0")
        self.assertIsNone(snap["network"]["rx_bps"])
        self.assertIsNone(snap["network"]["tx_bps"])

    def test_mixed_reset_only_affected_direction_is_na(self):
        snap = self._collect_with_dev(DEV_RX_RESET)
        self.assertIsNone(snap["network"]["rx_bps"])
        # tx grew 1000 B over 0.2 s.
        self.assertAlmostEqual(snap["network"]["tx_bps"], 5000.0)


class StripControlsTests(unittest.TestCase):
    def test_strips_ansi_and_controls(self):
        self.assertEqual(strip_controls("\x1b[31mRED\x1b[0m"), "RED")
        self.assertEqual(strip_controls("a\x07b\x7fc"), "a b c")
        self.assertEqual(strip_controls("a\tb\nc"), "a b c")
        self.assertEqual(strip_controls("plain text"), "plain text")
        self.assertEqual(strip_controls("中文\x1b[1;2H"), "中文")
        # Private-mode sequences are stripped too, not left behind.
        self.assertEqual(strip_controls("\x1b[?25lab"), "ab")

    def test_display_width_ignores_escapes_and_controls(self):
        self.assertEqual(display_width("\x1b[36mab\x1b[0m"), 2)
        self.assertEqual(display_width("a\x07b"), 3)  # bell -> space

    def test_truncate_and_pad_sanitize(self):
        self.assertNotIn("\x1b", truncate("a\x1b[31mRED\x1b[0m", 10))
        self.assertEqual(truncate("a\x1b[31mRED\x1b[0m", 10), "aRED")
        self.assertNotIn("\x07", pad("a\x07b", 5))
        self.assertEqual(display_width(pad("a\x07b", 5)), 5)

    def test_box_line_and_two_columns_sanitize(self):
        line = R.box_line("a\x1b[31mb\x07c", 10, True)
        self.assertNotIn("\x1b", line)
        self.assertNotIn("\x07", line)
        self.assertEqual(display_width(line), 10)
        two = R.two_columns("a\x1b[31m", "b\x07c", 10)
        self.assertNotIn("\x1b", two)
        self.assertNotIn("\x07", two)
        self.assertEqual(display_width(two), 10)


class FakeTty(io.StringIO):
    def isatty(self):
        return True


class NoColorTests(unittest.TestCase):
    def test_cus_no_color_disables(self):
        env = {"TERM": "xterm-256color", "CUS_NO_COLOR": "1"}
        with mock.patch.dict(os.environ, env, clear=True):
            self.assertFalse(color_enabled(FakeTty()))

    def test_tty_without_env_enables(self):
        env = {"TERM": "xterm-256color"}
        with mock.patch.dict(os.environ, env, clear=True):
            self.assertTrue(color_enabled(FakeTty()))


class AsciiStream(io.TextIOBase):
    """A stream that only accepts ASCII, like an old SSH terminal."""
    encoding = "ascii"

    def __init__(self):
        super().__init__()
        self.buf = []

    def write(self, s):
        s.encode("ascii")  # raises UnicodeEncodeError on non-ASCII
        self.buf.append(s)
        return len(s)

    def isatty(self):
        return True

    def getvalue(self):
        return "".join(self.buf)


class SafePrintTests(unittest.TestCase):
    def test_safe_print_degrades_on_ascii_stream(self):
        stream = AsciiStream()
        R.safe_print("CPU ███ 73%", stream=stream)
        self.assertIn("?", stream.getvalue())
        self.assertNotIn("█", stream.getvalue())

    def test_safe_print_passthrough_on_normal_stream(self):
        stream = io.StringIO()
        R.safe_print("CPU ███ 73%", stream=stream)
        self.assertEqual(stream.getvalue(), "CPU ███ 73%\n")

    def test_console_emit_degrades_on_ascii_stream(self):
        stream = AsciiStream()
        console = Console(HOST, input_fn=lambda _: "0", out=stream, width=80)
        console.emit("场景部署 ◈ 测试")
        self.assertIn("?", stream.getvalue())
        self.assertNotIn("◈", stream.getvalue())


class FakeKernel32:
    """Stand-in for ctypes.windll.kernel32; fills FILETIME /
    MEMORYSTATUSEX structs through the byref objects' _obj."""

    def __init__(self, cpu_samples=None, mem=None, ok=True):
        self.cpu_samples = list(cpu_samples or [])
        self.mem = mem
        self.ok = ok

    def GetSystemTimes(self, idle, kernel, user):
        if not self.ok or not self.cpu_samples:
            return 0
        i, k, u = self.cpu_samples.pop(0)
        for arg, value in ((idle, i), (kernel, k), (user, u)):
            arg._obj.dwLowDateTime = value & 0xFFFFFFFF
            arg._obj.dwHighDateTime = (value >> 32) & 0xFFFFFFFF
        return 1

    def GlobalMemoryStatusEx(self, status):
        if not self.ok or self.mem is None:
            return 0
        total, avail = self.mem
        obj = status._obj
        obj.ullTotalPhys = total
        obj.ullAvailPhys = avail
        return 1


class FakeWindll:
    def __init__(self, kernel32):
        self.kernel32 = kernel32


def _patch_windll(kernel32):
    return mock.patch.object(monitor.ctypes, "windll",
                             FakeWindll(kernel32), create=True)


class WindowsTests(unittest.TestCase):
    def test_win_cpu_times_assembles_64bit(self):
        # Values above 2**32 prove the high word is used.
        k32 = FakeKernel32(
            cpu_samples=[(5_000_000_000, 9_000_000_000, 3_000_000_000)])
        with _patch_windll(k32):
            self.assertEqual(monitor._win_cpu_times(),
                             (12_000_000_000, 5_000_000_000))

    def test_win_cpu_times_none_when_api_fails(self):
        with _patch_windll(FakeKernel32(ok=False)):
            self.assertIsNone(monitor._win_cpu_times())

    def test_windows_memory_shape(self):
        total = 8 * 1024 ** 3
        avail = 2 * 1024 ** 3
        with _patch_windll(FakeKernel32(mem=(total, avail))):
            mem = monitor._windows_memory()
        self.assertEqual(mem["total_kb"], total // 1024)
        self.assertEqual(mem["used_kb"], (total - avail) // 1024)
        self.assertAlmostEqual(mem["percent"], 75.0)

    def test_windows_memory_none_when_api_fails(self):
        with _patch_windll(FakeKernel32(ok=False)):
            self.assertIsNone(monitor._windows_memory())

    def test_windows_cpu_sample_percent(self):
        # sample 1: total 1000, idle 800; sample 2: total 1100, idle 870.
        k32 = FakeKernel32(cpu_samples=[(800, 200, 800), (870, 230, 870)])
        with _patch_windll(k32):
            pct = monitor._windows_cpu_sample(0.2, lambda _s: None)
        self.assertAlmostEqual(pct, 30.0)

    def test_collect_windows_branch(self):
        total = 8 * 1024 ** 3
        k32 = FakeKernel32(cpu_samples=[(800, 200, 800), (870, 230, 870)],
                           mem=(total, 2 * 1024 ** 3))
        with _patch_windll(k32), \
                mock.patch.object(monitor.sys, "platform", "win32"):
            snap = monitor.collect(interval=0.2, sleep=lambda _s: None)
        self.assertAlmostEqual(snap["cpu_percent"], 30.0)
        self.assertEqual(snap["memory"]["total_kb"], total // 1024)
        self.assertIsNone(snap["network"]["iface"])
        self.assertIsNone(snap["network"]["rx_bps"])


class DarwinMemoryTests(unittest.TestCase):
    def test_darwin_memory_total_only(self):
        run = mock.Mock()
        run.returncode = 0
        run.stdout = "17179869184\n"
        with mock.patch.object(monitor.subprocess, "run", return_value=run):
            mem = monitor._memory_darwin()
        self.assertEqual(mem["total_kb"], 17179869184 // 1024)
        self.assertIsNone(mem["used_kb"])
        self.assertIsNone(mem["percent"])

    def test_darwin_memory_none_on_failure(self):
        run = mock.Mock()
        run.returncode = 1
        run.stdout = ""
        with mock.patch.object(monitor.subprocess, "run", return_value=run):
            self.assertIsNone(monitor._memory_darwin())
        with mock.patch.object(monitor.subprocess, "run",
                               side_effect=OSError):
            self.assertIsNone(monitor._memory_darwin())

    def test_memory_dispatches_darwin(self):
        run = mock.Mock()
        run.returncode = 0
        run.stdout = "17179869184\n"
        with mock.patch.object(monitor.sys, "platform", "darwin"), \
                mock.patch.object(monitor.subprocess, "run",
                                  return_value=run):
            mem = monitor.memory()
        self.assertIsNotNone(mem["total_kb"])
        self.assertIsNone(mem["used_kb"])
        self.assertIsNone(mem["percent"])


if __name__ == "__main__":
    unittest.main()
