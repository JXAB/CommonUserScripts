"""
Security Auditor & Risk Level Controller.
Enforces L0-L4 permission checks, prevents destructive execution, and sanitizes secrets.
"""

from enum import IntEnum
import re
from typing import List, Pattern


class RiskLevel(IntEnum):
    L0 = 0  # Read-only, status, diagnosis
    L1 = 1  # User-space operations (local tools, ~/.bashrc)
    L2 = 2  # System package management (apt/dnf, systemd service)
    L3 = 3  # High-risk system changes (firewall, network ports, purge cache)
    L4 = 4  # Prohibited destructive actions (rm -rf /, format, wipe)


class SecurityViolationError(PermissionError):
    """Raised when an operation violates security boundaries or risk limits."""
    pass


class SecurityAuditor:

    PROHIBITED_PATTERNS: List[Pattern] = [
        re.compile(r"\brm\s+-[rRfF]+\s+(/|\*|/\*)(\s+|$)", re.IGNORECASE),
        re.compile(r"\bmkfs(\.\w+)?\s+/dev/", re.IGNORECASE),
        re.compile(r"\bdd\s+if=.*of=/dev/[svh]d", re.IGNORECASE),
        re.compile(r":\(\)\s*\{\s*:\s*\|\s*:\s*&\s*\}\s*;\s*:", re.IGNORECASE),  # fork bomb
        re.compile(r"\bgit\s+reset\s+--hard\b", re.IGNORECASE),
        re.compile(r"\b(curl|wget)\s+[^|;]+\|\s*(sudo\s+)?(bash|sh)\b", re.IGNORECASE),  # unverified curl|bash
    ]

    SECRET_MASKS: List[tuple] = [
        # sk-... API keys (OpenAI / Anthropic / Gemini style)
        (re.compile(r"(sk-[a-zA-Z0-9_\-]{20,})"), "[REDACTED_API_KEY]"),
        # Generic password in env / parameters
        (re.compile(r"(password|passwd|secret|token)\s*=\s*['\"]?([^'\"\s\n]+)['\"]?", re.IGNORECASE), r"\1=[REDACTED]"),
        # Bearer tokens
        (re.compile(r"Bearer\s+([a-zA-Z0-9_\-\.]{20,})", re.IGNORECASE), "Bearer [REDACTED_TOKEN]"),
    ]

    def validate_command(self, cmd_str: str, risk_level: RiskLevel) -> None:
        """
        Validates if command string is permitted under current security policy.
        L4 commands or known destructive patterns are rejected unconditionally.
        """
        if risk_level >= RiskLevel.L4:
            raise SecurityViolationError(f"Operation with risk level {risk_level.name} is strictly prohibited by AGENTS.md policy.")

        for pat in self.PROHIBITED_PATTERNS:
            if pat.search(cmd_str):
                raise SecurityViolationError(
                    f"Blocked potentially destructive or unverified command pattern: '{cmd_str}'"
                )

    def sanitize_output(self, text: str) -> str:
        """Masks sensitive credentials, keys, and tokens from output."""
        sanitized = text
        for pat, replacement in self.SECRET_MASKS:
            sanitized = pat.sub(replacement, sanitized)
        return sanitized
