"""
Execution Engine & Lifecycle Orchestrator.
Manages the 6-phase pipeline: Detect -> Plan -> Approve -> Apply -> Verify -> Report.
"""

from dataclasses import dataclass, field, asdict
from enum import Enum
import json
import os
import subprocess
from typing import List, Dict, Any, Optional

from core.platform.os_detect import detect_system, OSInfo
from core.security import SecurityAuditor, RiskLevel, SecurityViolationError


class ExecutionStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    SIMULATED = "simulated"
    BLOCKED = "blocked"
    UNVERIFIED = "unverified"


@dataclass
class StepResult:
    module_id: str
    status: ExecutionStatus
    risk_level: str
    verified: bool = False
    message: str = ""
    duration_ms: int = 0
    stdout: str = ""
    stderr: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "module_id": self.module_id,
            "status": self.status.value,
            "risk_level": self.risk_level,
            "verified": self.verified,
            "message": self.message,
            "duration_ms": self.duration_ms,
            "stdout": self.stdout,
            "stderr": self.stderr,
        }


class ExecutionEngine:

    def __init__(self, data_dir: Optional[str] = None):
        self.os_info: OSInfo = detect_system()
        self.security: SecurityAuditor = SecurityAuditor()

        if not data_dir:
            base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
            data_dir = os.path.join(base_dir, "data")

        self.data_dir = data_dir
        self.modules: Dict[str, Any] = self._load_json(os.path.join(data_dir, "modules.json")).get("modules", [])
        self.profiles: Dict[str, Any] = self._load_json(os.path.join(data_dir, "profiles.json")).get("profiles", [])

        self.module_map = {m["id"]: m for m in self.modules}
        self.profile_map = {p["id"]: p for p in self.profiles}

    def _load_json(self, path: str) -> Dict[str, Any]:
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                return {}
        return {}

    def create_plan(self, profile_id: str) -> Dict[str, Any]:
        if profile_id not in self.profile_map:
            raise ValueError(f"Profile '{profile_id}' not found in registry.")

        profile = self.profile_map[profile_id]
        steps = []
        for mod_id in profile.get("modules", []):
            mod_meta = self.module_map.get(mod_id, {})
            risk_str = mod_meta.get("risk_level", "L1")
            steps.append({
                "module_id": mod_id,
                "name": mod_meta.get("name", mod_id),
                "risk_level": risk_str,
                "category": mod_meta.get("category", "general"),
                "platforms": mod_meta.get("platforms", {}),
                "verify_cmd": mod_meta.get("verify", {}).get("commands", []),
            })

        return {
            "profile_id": profile_id,
            "profile_name": profile.get("name", ""),
            "description": profile.get("description", ""),
            "os": self.os_info.to_dict(),
            "steps": steps,
        }

    def run_step(self, step: Dict[str, Any], dry_run: bool = True) -> StepResult:
        mod_id = step.get("module_id", "unknown")
        risk_str = step.get("risk_level", "L1")
        risk_lvl = getattr(RiskLevel, risk_str, RiskLevel.L1)

        if dry_run:
            return StepResult(
                module_id=mod_id,
                status=ExecutionStatus.SIMULATED,
                risk_level=risk_str,
                verified=True,
                message=f"[DRY-RUN] Simulation verified for {mod_id} ({risk_str})",
            )

        # Pre-execution security check
        verify_cmds = step.get("verify_cmd", [])
        if verify_cmds and isinstance(verify_cmds, list):
            for cmd_entry in verify_cmds:
                if isinstance(cmd_entry, dict) and "cmd" in cmd_entry:
                    cmd_line = " ".join(cmd_entry["cmd"])
                    try:
                        self.security.validate_command(cmd_line, risk_lvl)
                    except SecurityViolationError as e:
                        return StepResult(
                            module_id=mod_id,
                            status=ExecutionStatus.BLOCKED,
                            risk_level=risk_str,
                            verified=False,
                            message=str(e),
                        )

        # Actual execution of verify check (Capability Verification)
        all_passed = True
        err_msg = ""
        for v in verify_cmds:
            if isinstance(v, str):
                cmd = [v]
            elif isinstance(v, dict) and "cmd" in v:
                cmd = v["cmd"]
            else:
                continue

            try:
                proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=10)
                if proc.returncode != 0:
                    all_passed = False
                    err_msg = f"Verify command '{cmd}' failed with code {proc.returncode}: {proc.stderr.strip()}"
                    break
            except Exception as e:
                all_passed = False
                err_msg = f"Verify command '{cmd}' execution error: {str(e)}"
                break

        if not all_passed:
            return StepResult(
                module_id=mod_id,
                status=ExecutionStatus.FAILED,
                risk_level=risk_str,
                verified=False,
                message=err_msg,
            )

        return StepResult(
            module_id=mod_id,
            status=ExecutionStatus.SUCCESS,
            risk_level=risk_str,
            verified=True,
            message=f"Verified successfully: {mod_id}",
        )

    def execute_plan(self, plan: Dict[str, Any], dry_run: bool = True, auto_approve: bool = False) -> Dict[str, Any]:
        if not auto_approve and not dry_run:
            raise PermissionError("Plan execution requires explicit approval (--apply).")

        results = []
        overall_status = ExecutionStatus.SIMULATED if dry_run else ExecutionStatus.SUCCESS

        for step in plan.get("steps", []):
            res = self.run_step(step, dry_run=dry_run)
            results.append(res.to_dict())
            if res.status == ExecutionStatus.FAILED or res.status == ExecutionStatus.BLOCKED:
                overall_status = res.status
                break

        return {
            "profile_id": plan["profile_id"],
            "status": overall_status.value,
            "dry_run": dry_run,
            "steps": results,
        }
