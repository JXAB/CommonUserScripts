"""Box, bar and number formatting. Pure functions: no I/O, no color
decisions beyond the injected Theme (or None for plain text).
"""
from __future__ import annotations

import sys

from .layout import display_width, pad, truncate
from .theme import strip_controls


def safe_print(text: str = "", stream=None) -> None:
    """Write one line. On UnicodeEncodeError (old ASCII-only terminals),
    fall back to 'replace' so output degrades instead of crashing."""
    if stream is None:
        stream = sys.stdout
    try:
        print(text, file=stream)
    except UnicodeEncodeError:
        encoding = getattr(stream, "encoding", None) or "ascii"
        try:
            safe = text.encode(encoding, "replace").decode(encoding, "replace")
        except (LookupError, UnicodeError):
            safe = text.encode("ascii", "replace").decode("ascii", "replace")
        print(safe, file=stream)

UNICODE_BOX = {"tl": "\u256d", "tr": "\u256e", "bl": "\u2570", "br": "\u256f",
               "h": "\u2500", "v": "\u2502", "lt": "\u251c", "rt": "\u2524"}
ASCII_BOX = {"tl": "+", "tr": "+", "bl": "+", "br": "+",
             "h": "-", "v": "|", "lt": "+", "rt": "+"}


def box_chars(unicode_mode: bool) -> dict:
    return UNICODE_BOX if unicode_mode else ASCII_BOX


def glyphs(unicode_mode: bool) -> dict:
    """Bullet / marker glyphs, with an ASCII fallback for each."""
    if unicode_mode:
        return {"bullet": "\u25c8", "dot": "\u25cf", "mid": "\u00b7",
                "full": "\u2588", "empty": "\u2591"}
    return {"bullet": "*", "dot": "*", "mid": "-",
            "full": "#", "empty": "-"}


def format_bytes(n: float | None) -> str:
    """Adaptive unit: B / KB / MB / GB / TB. None renders as N/A."""
    if n is None:
        return "N/A"
    value = float(n)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(value) < 1024 or unit == "TB":
            return f"{value:.0f} {unit}" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} TB"


def format_rate(bps: float | None) -> str:
    """Bytes per second with an adaptive unit."""
    if bps is None:
        return "N/A"
    return format_bytes(bps) + "/s"


def format_pair(used: float | None, total: float | None) -> str:
    """'used / total' in one shared unit (GiB preferred when it fits)."""
    if used is None or total is None:
        return "N/A"
    if total >= 1024 ** 3:
        return f"{used / 1024 ** 3:.1f} / {total / 1024 ** 3:.1f} GiB"
    if total >= 1024 ** 2:
        return f"{used / 1024 ** 2:.1f} / {total / 1024 ** 2:.1f} MiB"
    return f"{format_bytes(used)} / {format_bytes(total)}"


def progress_bar(percent: float | None, width: int = 10,
                 unicode_mode: bool = True) -> str:
    """Fixed-width bar. None (unknown) renders as an empty bar, never as 0%."""
    g = glyphs(unicode_mode)
    if percent is None:
        return g["empty"] * width
    filled = int(round(max(0.0, min(100.0, percent)) / 100.0 * width))
    return g["full"] * filled + g["empty"] * (width - filled)


def percent_text(percent: float | None) -> str:
    return "N/A" if percent is None else f"{percent:.0f}%"


def box_top(width: int, unicode_mode: bool) -> str:
    box = box_chars(unicode_mode)
    return box["tl"] + box["h"] * (width - 2) + box["tr"]


def box_bottom(width: int, unicode_mode: bool) -> str:
    box = box_chars(unicode_mode)
    return box["bl"] + box["h"] * (width - 2) + box["br"]


def box_line(content: str, width: int, unicode_mode: bool) -> str:
    """One bordered row; content is padded (or cut) to the inner width."""
    box = box_chars(unicode_mode)
    inner = width - 2
    return box["v"] + pad(truncate(content, inner), inner) + box["v"]


def section_rule(width: int, title: str = "", unicode_mode: bool = True,
                 theme=None) -> str:
    """Separator with an optional centered title, e.g. |-- SYSTEM --|."""
    box = box_chars(unicode_mode)
    inner = width - 2
    label = f" {title} " if title else ""
    if theme is not None:
        label = theme.paint(label, "bold_white") if title else label
    fill = max(0, inner - display_width(label))
    left = fill // 2
    right = fill - left
    return (box["lt"] + box["h"] * left + label + box["h"] * right
            + box["rt"])


def plain_rule(width: int, unicode_mode: bool = True) -> str:
    box = box_chars(unicode_mode)
    return box["lt"] + box["h"] * (width - 2) + box["rt"]


def two_columns(left: str, right: str, total_width: int) -> str:
    """Left text + right text on one line; right is right-aligned.
    Both sides are sanitized first (truncate/pad already sanitize the
    left; the right side is appended raw, so it needs its own pass)."""
    left = strip_controls(left)
    right = strip_controls(right)
    right_w = display_width(right)
    left_w = total_width - right_w
    return pad(truncate(left, left_w), left_w) + right
