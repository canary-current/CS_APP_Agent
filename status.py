"""
Two-line in-place status updater.

render(top=..., bottom=...) prints two lines below the current output.
Subsequent render() calls overwrite those two lines in place via cursor
movement — useful for showing "current URL" + "progress bar" that update
many times during one tool-calling loop without flooding the scrollback.

seal() commits the current block: the next render() starts a fresh
two-line block below whatever has been printed since. Call seal() before
any output that should appear permanently in scrollback (agent reply,
errors, saved-file messages, the next "You:" prompt).

No scroll regions, no cursor save/restore — both of those are flaky on
macOS Terminal.app. This module relies only on relative cursor movement
(\\033[2A) and line erase (\\033[2K), which every VT100-compatible
terminal supports reliably.

If stdout is not a TTY, render() falls back to plain print() so logs
and CI output still look reasonable.
"""

from __future__ import annotations
import sys

_CSI = "\033["
_top = ""
_bottom = ""
_committed = True  # True = no live status block; next render starts fresh


def _is_tty() -> bool:
    try:
        return sys.stdout.isatty()
    except Exception:
        return False


def render(*, top: str | None = None, bottom: str | None = None) -> None:
    """Update one or both lines of the live status block."""
    global _top, _bottom, _committed
    if top is not None:
        _top = top
    if bottom is not None:
        _bottom = bottom

    if not _is_tty():
        if top is not None:
            print(top, flush=True)
        if bottom is not None:
            print(bottom, flush=True)
        return

    if not _committed:
        # Move cursor up to the start of the existing status block.
        sys.stdout.write(f"{_CSI}2A\r")

    sys.stdout.write(f"{_CSI}2K{_top}\n")
    sys.stdout.write(f"\r{_CSI}2K{_bottom}\n")
    sys.stdout.flush()
    _committed = False


def seal() -> None:
    """
    Commit the current status block. Subsequent prints scroll normally
    below it, and the next render() starts a fresh block.
    """
    global _committed
    _committed = True


def clear() -> None:
    """Erase the live status block (if any) and reset to a sealed state."""
    global _committed, _top, _bottom
    if not _committed and _is_tty():
        sys.stdout.write(f"{_CSI}2A\r{_CSI}2K\n\r{_CSI}2K\n{_CSI}2A\r")
        sys.stdout.flush()
    _committed = True
    _top = ""
    _bottom = ""


# Compatibility shims for the old scroll-region API.
def enable() -> None:
    pass


def disable() -> None:
    global _committed
    if not _committed and _is_tty():
        sys.stdout.write("\n")
        sys.stdout.flush()
    _committed = True


def shorten_url(url: str, max_len: int = 80) -> str:
    """Truncate a long URL with a middle ellipsis, preserving both ends."""
    if len(url) <= max_len:
        return url
    keep_head = max_len // 2 - 2
    keep_tail = max_len - keep_head - 3
    return url[:keep_head] + "..." + url[-keep_tail:]
