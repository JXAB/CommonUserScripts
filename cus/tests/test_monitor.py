"""Monitor tests: fake /proc trees only, never the live machine.

CPU / memory / network math is checked against hand-computed values;
the shared sampling window is driven by an injected sleep that rewrites
the fake counters and an injected monotonic clock.
"""
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.cus import monitor  # noqa: E402

STAT_1 = "cpu  100 0 100 700 100 0 0 0 0 0\n"
STAT_2 = "cpu  120 0 110 760 110 0 0 0 0 0\n"
# guest/guest_nice (50/10) must NOT be added to the total.
STAT_GUEST = "cpu  100 0 100 700 100 0 0 0 50 10\n"

MEMINFO = (
    "MemTotal:       4096000 kB\n"
    "MemFree:         512000 kB\n"
    "MemAvailable:   2048000 kB\n"
)

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

DEV_1 = (
    "Inter-|   Receive                                                |  Transmit\n"
    " face |bytes    packets errs drop fifo frame compressed multicast|bytes    packets errs drop fifo colls carrier compressed\n"
    "  eth0: 100000 100 0 0 0 0 0 0 200000 200 0 0 0 0 0 0\n"
    "    lo: 5000 50 0 0 0 0 0 0 5000 50 0 0 0 0 0 0\n"
    " wlan0: 3000 30 0 0 0 0 0 0 4000 40 0 0 0 0 0 0\n"
)

DEV_2 = DEV_1.replace("100000", "102000").replace("200000", "201000")


class FakeProc(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / "net").mkdir()
        self.write("stat", STAT_1)
        self.write("meminfo", MEMINFO)
        self.write("net/route", ROUTE_DEFAULT)
        self.write("net/dev", DEV_1)

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, rel, text):
        (self.root / rel).write_text(text, encoding="utf-8")


class CpuTests(FakeProc):
    def test_cpu_times_parses_and_ignores_guest(self):
        total, idle = monitor.cpu_times(self.root)
        self.assertEqual((total, idle), (1000, 800))
        self.write("stat", STAT_GUEST)
        total, idle = monitor.cpu_times(self.root)
        self.assertEqual((total, idle), (1000, 800))

    def test_cpu_percent_math(self):
        # dt=100, di=70 -> 30%
        self.assertAlmostEqual(
            monitor.cpu_percent((1000, 800), (1100, 870)), 30.0)
        self.assertAlmostEqual(
            monitor.cpu_percent((1000, 800), (1100, 800)), 100.0)
        self.assertAlmostEqual(
            monitor.cpu_percent((1000, 800), (1100, 900)), 0.0)

    def test_cpu_percent_none_on_bad_input(self):
        self.assertIsNone(monitor.cpu_percent(None, (1100, 870)))
        self.assertIsNone(monitor.cpu_percent((1000, 800), None))
        self.assertIsNone(monitor.cpu_percent((1000, 800), (1000, 800)))
        self.assertIsNone(monitor.cpu_percent((1000, 800), (900, 700)))
        self.assertIsNone(monitor.cpu_percent((1000, 800), (1100, 750)))

    def test_cpu_times_missing_file(self):
        self.assertIsNone(monitor.cpu_times(Path("/nonexistent-proc")))


class MemoryTests(FakeProc):
    def test_memory_uses_available_not_free(self):
        mem = monitor._memory_linux(self.root)
        self.assertEqual(mem["total_kb"], 4096000)
        # used = Total - Available (2048000), NOT Total - Free (3584000).
        self.assertEqual(mem["used_kb"], 2048000)
        self.assertAlmostEqual(mem["percent"], 50.0)

    def test_memory_missing_file(self):
        self.assertIsNone(monitor._memory_linux(Path("/nonexistent-proc")))


class NetworkTests(FakeProc):
    def test_default_iface_lowest_metric(self):
        self.assertEqual(monitor.default_iface(self.root), "eth0")

    def test_default_iface_none_without_default(self):
        self.write("net/route", ROUTE_NO_DEFAULT)
        self.assertIsNone(monitor.default_iface(self.root))

    def test_net_counters_parse_rx_tx(self):
        self.assertEqual(monitor.net_counters(self.root, "eth0"),
                         ("eth0", 100000, 200000))
        self.assertIsNone(monitor.net_counters(self.root, "nope"))

    def test_pick_iface_falls_back_without_default_route(self):
        self.write("net/route", ROUTE_NO_DEFAULT)
        self.assertEqual(monitor.pick_iface(self.root), "eth0")

    def test_pick_iface_none_when_only_loopback(self):
        self.write("net/route", ROUTE_NO_DEFAULT)
        self.write("net/dev", DEV_1.replace("  eth0:", "    lo:")
                  .replace(" wlan0:", "    lo:"))
        self.assertIsNone(monitor.pick_iface(self.root))


class CollectTests(FakeProc):
    def test_collect_shared_window_rates(self):
        # The injected sleep rewrites the fake counters between t0 and t1;
        # the injected clock makes the elapsed time exactly 0.2s.
        def mutating_sleep(_seconds):
            self.write("stat", STAT_2)
            self.write("net/dev", DEV_2)

        times = iter([1000.0, 1000.2])
        snap = monitor.collect(
            interval=0.2, proc_root=self.root,
            sleep=mutating_sleep, monotonic=lambda: next(times))
        self.assertAlmostEqual(snap["cpu_percent"], 30.0)
        self.assertEqual(snap["network"]["iface"], "eth0")
        # dt_rx 2000 B / 0.2 s = 10000 B/s; dt_tx 1000 B / 0.2 s = 5000 B/s.
        self.assertAlmostEqual(snap["network"]["rx_bps"], 10000.0)
        self.assertAlmostEqual(snap["network"]["tx_bps"], 5000.0)
        # Memory math is covered by MemoryTests via _memory_linux; on
        # macOS collect() reads real memory, so it is not asserted here.
        self.assertIn("percent", snap["disk"])

    def test_collect_empty_proc_is_na_not_crash(self):
        with tempfile.TemporaryDirectory() as empty:
            snap = monitor.collect(interval=0, proc_root=Path(empty))
        self.assertIsNone(snap["cpu_percent"])
        self.assertIsNone(snap["network"]["iface"])
        self.assertIsNone(snap["network"]["rx_bps"])

    def test_collect_zero_interval_no_crash(self):
        snap = monitor.collect(interval=0, proc_root=self.root)
        self.assertIsNone(snap["cpu_percent"])  # zero delta -> N/A
        self.assertEqual(snap["network"]["iface"], "eth0")

    def test_disk_shape(self):
        disk = monitor.disk("/")
        self.assertIn("total", disk)
        self.assertIn("used", disk)
        self.assertGreaterEqual(disk["percent"], 0.0)
        self.assertLessEqual(disk["percent"], 100.0)


if __name__ == "__main__":
    unittest.main()
