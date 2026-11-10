"""ANSI colors. Auto-off when stdout is not a TTY, TERM is dumb, or
NO_COLOR is set, so piped output and install logs stay clean.
"""
from __future__ import annotations

import os
import re
import sys

RESET = "\033[0m"

CODES = {
    "cyan": "\033[36m",
    "bold_white": "\033[1;37m",
    "green": "\033[32m",
    "yellow": "\033[33m",
    "red": "\033[31m",
    "gray": "\033[90m",
    "reverse": "\033[7m",
    "bold": "\033[1m",
}

ANSI_RE = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")
# Broader ANSI pattern: also covers private/intermediate bytes such as
# "?25l" or "1;2H", which ANSI_RE would leave behind.
ANSI_FULL_RE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")


def strip_ansi(text: str) -> str:
    return ANSI_RE.sub("", text)


def strip_controls(text: str) -> str:
    """Drop ANSI escapes, then replace control characters (ord < 32
    except space, and DEL 127) with a space. Data from files (module /
    profile names, hostnames) must never reach the terminal raw."""
    s = ANSI_FULL_RE.sub("", str(text))
    return "".join(c if c == " " or (ord(c) >= 32 and ord(c) != 127)
                   else " " for c in s)


def color_enabled(stream=None) -> bool:
    if os.environ.get("NO_COLOR") is not None:
        return False
    if os.environ.get("CUS_NO_COLOR") is not None:
        return False
    if os.environ.get("TERM", "") == "dumb":
        return False
    stream = stream if stream is not None else sys.stdout
    try:
        return bool(stream.isatty())
    except Exception:
        return False


class Theme:
    """Paints text only when colors are enabled for the target stream."""

    def __init__(self, enabled: bool | None = None, stream=None):
        if enabled is None:
            enabled = color_enabled(stream)
        self.enabled = enabled

    def paint(self, text: str, style: str) -> str:
        if not self.enabled or style not in CODES:
            return text
        return f"{CODES[style]}{text}{RESET}"

    def title(self, text: str) -> str:
        return self.paint(text, "cyan")

    def heading(self, text: str) -> str:
        return self.paint(text, "bold_white")

    def ok(self, text: str) -> str:
        return self.paint(text, "green")

    def warn(self, text: str) -> str:
        return self.paint(text, "yellow")

    def err(self, text: str) -> str:
        return self.paint(text, "red")

    def dim(self, text: str) -> str:
        return self.paint(text, "gray")

    def selected(self, text: str) -> str:
        return self.paint(text, "reverse")
