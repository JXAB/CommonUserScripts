import unittest
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from core.security import RiskLevel, SecurityAuditor, SecurityViolationError


class TestSecurity(unittest.TestCase):

    def setUp(self):
        self.auditor = SecurityAuditor()

    def test_risk_level_order(self):
        self.assertLess(RiskLevel.L0, RiskLevel.L1)
        self.assertLess(RiskLevel.L1, RiskLevel.L2)
        self.assertLess(RiskLevel.L2, RiskLevel.L3)
        self.assertLess(RiskLevel.L3, RiskLevel.L4)

    def test_l4_destructive_blocked(self):
        """L4 operations (destructive/unrecoverable) must always be rejected."""
        dangerous_commands = [
            "rm -rf /",
            "rm -rf /*",
            "mkfs.ext4 /dev/sda1",
            "git reset --hard",
            ":(){ :|:& };:"
        ]
        for cmd in dangerous_commands:
            with self.assertRaises(SecurityViolationError):
                self.auditor.validate_command(cmd, RiskLevel.L4)

    def test_sanitize_secrets(self):
        """Tokens, passwords and API keys must be masked in logs and reports."""
        raw_text = "Bearer sk-proj-1234567890abcdef1234567890 and password=mysecretpassword123"
        sanitized = self.auditor.sanitize_output(raw_text)
        self.assertNotIn("sk-proj-1234567890abcdef1234567890", sanitized)
        self.assertNotIn("mysecretpassword123", sanitized)
        self.assertIn("[REDACTED_API_KEY]", sanitized)


if __name__ == "__main__":
    unittest.main()
