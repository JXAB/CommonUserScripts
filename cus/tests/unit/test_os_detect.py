import unittest
from unittest.mock import patch, mock_open
import os
import sys

# Add parent directory to sys.path so we can import core
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from core.platform.os_detect import OSInfo, detect_system, PackageManager


class TestOSDetect(unittest.TestCase):

    def test_current_system_detection(self):
        """Current platform must be detected without raising exceptions."""
        info = detect_system()
        self.assertIsInstance(info, OSInfo)
        self.assertIn(info.system, ["linux", "darwin", "windows", "unknown"])
        self.assertTrue(len(info.arch) > 0)
        self.assertIsInstance(info.is_root, bool)

    @patch("platform.system", return_value="Linux")
    @patch("platform.machine", return_value="x86_64")
    @patch("os.path.exists")
    @patch("builtins.open", new_callable=mock_open, read_data='ID=ubuntu\nVERSION_ID="24.04"\nNAME="Ubuntu"')
    def test_ubuntu_detection(self, mock_file, mock_exists, mock_arch, mock_sys):
        mock_exists.side_effect = lambda p: p == "/etc/os-release"
        info = detect_system()
        self.assertEqual(info.system, "linux")
        self.assertEqual(info.distribution, "ubuntu")
        self.assertEqual(info.version, "24.04")
        self.assertEqual(info.pkg_manager, PackageManager.APT)

    @patch("platform.system", return_value="Linux")
    @patch("platform.machine", return_value="aarch64")
    @patch("os.path.exists")
    @patch("builtins.open", new_callable=mock_open, read_data='ID=debian\nVERSION_ID="12"')
    def test_debian_detection(self, mock_file, mock_exists, mock_arch, mock_sys):
        mock_exists.side_effect = lambda p: p == "/etc/os-release"
        info = detect_system()
        self.assertEqual(info.system, "linux")
        self.assertEqual(info.distribution, "debian")
        self.assertEqual(info.version, "12")
        self.assertEqual(info.pkg_manager, PackageManager.APT)

    @patch("platform.system", return_value="Linux")
    @patch("platform.machine", return_value="x86_64")
    @patch("os.path.exists")
    @patch("builtins.open", new_callable=mock_open, read_data='ID=fedora\nVERSION_ID="40"')
    def test_fedora_detection(self, mock_file, mock_exists, mock_arch, mock_sys):
        mock_exists.side_effect = lambda p: p == "/etc/os-release"
        info = detect_system()
        self.assertEqual(info.system, "linux")
        self.assertEqual(info.distribution, "fedora")
        self.assertEqual(info.pkg_manager, PackageManager.DNF)

    @patch("shutil.which", return_value="/opt/homebrew/bin/brew")
    @patch("platform.system", return_value="Darwin")
    @patch("platform.machine", return_value="arm64")
    @patch("platform.mac_ver", return_value=("14.5", ("", "", ""), ""))
    def test_macos_detection(self, mock_mac_ver, mock_arch, mock_sys, mock_which):
        info = detect_system()
        self.assertEqual(info.system, "darwin")
        self.assertEqual(info.distribution, "macos")
        self.assertEqual(info.pkg_manager, PackageManager.BREW)


if __name__ == "__main__":
    unittest.main()
