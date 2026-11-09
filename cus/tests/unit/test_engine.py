import unittest
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from core.engine import ExecutionEngine, StepResult, ExecutionStatus
from core.security import RiskLevel


class TestEngine(unittest.TestCase):

    def setUp(self):
        self.engine = ExecutionEngine()

    def test_dry_run_mode(self):
        """In dry-run mode, plan is generated but apply phase is skipped safely."""
        plan = self.engine.create_plan(profile_id="daily-ops-cleaner")
        self.assertIsNotNone(plan)
        self.assertEqual(plan["profile_id"], "daily-ops-cleaner")
        self.assertGreater(len(plan["steps"]), 0)

        result = self.engine.execute_plan(plan, dry_run=True, auto_approve=True)
        self.assertEqual(result["status"], ExecutionStatus.SIMULATED)
        for step in result["steps"]:
            self.assertEqual(step["status"], ExecutionStatus.SIMULATED)

    def test_verify_failure_stops_pipeline(self):
        """If verify fails, status must be reported as FAILED, never PASS."""
        fake_step = {
            "module_id": "test-mock-fail",
            "risk_level": "L0",
            "verify_cmd": ["false"]  # guaranteed to exit with non-zero
        }
        step_res = self.engine.run_step(fake_step, dry_run=False)
        self.assertEqual(step_res.status, ExecutionStatus.FAILED)
        self.assertFalse(step_res.verified)


if __name__ == "__main__":
    unittest.main()
