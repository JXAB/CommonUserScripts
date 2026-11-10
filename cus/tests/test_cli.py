import json
import subprocess
import sys
import unittest
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.cus.catalog import modules, profiles, package_command


class CatalogTests(unittest.TestCase):
    def test_all_profiles_reference_valid_modules(self):
        all_mods = modules()
        for profile in profiles().values():
            for m in profile['modules']:
                self.assertIn(m, all_mods)

    def test_unsupported_adapter_never_returns_install_command(self):
        self.assertIsNone(package_command(modules()['dev-android'], {'manager': 'apt'}))
        self.assertIsNone(package_command(modules()['git'], {'manager': 'unknown'}))

    def test_only_known_package_manager_commands(self):
        cmd = package_command(modules()['git'], {'manager':'apt'})
        self.assertEqual(cmd, ['apt','install','-y','--','git'])

    def test_cli_plan_is_json_and_non_mutating(self):
        p = subprocess.run([sys.executable, str(ROOT / 'cus.py'),'--json','plan','ai-agent'],
                           capture_output=True, text=True, check=True)
        data = json.loads(p.stdout)
        self.assertIn('items', data)
        self.assertIn('plan-only', data['mode'])

    def test_external_install_blocked(self):
        p = subprocess.run([sys.executable, str(ROOT / 'cus.py'),'install','net-shadowsocks','--apply','--yes'],
                           capture_output=True, text=True)
        self.assertEqual(p.returncode, 2)
        self.assertIn('BLOCKED', p.stderr)


if __name__ == '__main__':
    unittest.main()
