"""Terminal size, display width (CJK-aware) and layout tiers.

Never use len() for layout: ANSI escapes, full-width CJK and combining
marks all break it. Widths here are visible columns.
"""
from __future__ import annotations

import os
import shutil
import sys
import unicodedata

from .theme import strip_controls


def display_width(text: str) -> int:
    """Visible columns: East Asian W/F count 2, combining marks 0.
    ANSI escapes and control characters are stripped before measuring,
    so injected sequences can never inflate or break the layout."""
    width = 0
    for ch in strip_controls(text):
        if unicodedata.combining(ch):
            continue
        width += 2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1
    return width


def pad(text: str, width: int) -> str:
    text = strip_controls(text)
    return text + " " * max(0, width - display_width(text))


def truncate(text: str, width: int, ellipsis: str = "\u2026") -> str:
    """Cut text to at most `width` visible columns, keeping whole glyphs.
    Input is sanitized first: no ANSI escape or control character
    survives into the terminal."""
    text = strip_controls(text)
    if display_width(text) <= width:
        return text
    budget = width - display_width(ellipsis)
    out, used = "", 0
    for ch in text:
        if unicodedata.combining(ch):
            out += ch
            continue
        cw = 2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1
        if used + cw > budget:
            break
        out += ch
        used += cw
    return out + ellipsis


def terminal_size(fallback: tuple[int, int] = (80, 24)) -> tuple[int, int]:
    size = shutil.get_terminal_size(fallback=fallback)
    return size.columns, size.lines


def tier(columns: int) -> str:
    """Layout tier: wide >= 100, standard 70-99, compact 40-69, minimal < 40."""
    if columns >= 100:
        return "wide"
    if columns >= 70:
        return "standard"
    if columns >= 40:
        return "compact"
    return "minimal"


def use_unicode(stream=None) -> bool:
    """True when the output encoding can render box-drawing and blocks.
    CUS_ASCII=1 forces the pure-ASCII fallback."""
    if os.environ.get("CUS_ASCII") == "1":
        return False
    stream = stream if stream is not None else sys.stdout
    encoding = (getattr(stream, "encoding", None) or "").lower()
    if encoding and "utf" in encoding:
        return True
    lang = (os.environ.get("LANG", "") + os.environ.get("LC_ALL", "")).lower()
    return "utf-8" in lang or "utf8" in lang
