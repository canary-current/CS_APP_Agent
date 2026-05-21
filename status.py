"""
A two-line live status block that floats at the visible bottom of output.

Use set() to update one or both lines — the block redraws in place.
Use emit() to print permanent content above the block; the block is
erased, the content prints, then the block re-renders below it.
Use hide() before input() so the prompt appears on a clean line; the
next set() will re-render the block below the user's typed input.

Uses only relative cursor movement (\\033[2A) and clear-to-end-of-screen
(\\033[0J) — both reliably supported on every VT100-compatible terminal,
including macOS Terminal.app, iTerm2, Linux gnome-terminal, etc.

Falls back to plain print() when stdout is not a TTY.
"""

from __future__ import annotations
import sys

_CSI = "\033["
_top = ""
_bottom = ""
_visible = False


def _is_tty() -> bool:
    try:
        return sys.stdout.isatty()
    except Exception:
        return False


def _erase_block() -> None:
    """Move cursor up 2 lines and clear to end of screen. Caller flushes."""
    sys.stdout.write(f"{_CSI}2A\r{_CSI}0J")


def _draw_block() -> None:
    """Write the two status lines starting at the current cursor position."""
    sys.stdout.write(f"{_top}\n{_bottom}\n")


def set(*, top: str | None = None, bottom: str | None = None) -> None:
    """Update one or both lines; the block redraws in place at the same position."""
    global _top, _bottom, _visible
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

    if _visible:
        _erase_block()
    _draw_block()
    sys.stdout.flush()
    _visible = True


def hide() -> None:
    """Erase the block; the next set() or show() will redraw it."""
    global _visible
    if not _visible or not _is_tty():
        return
    _erase_block()
    sys.stdout.flush()
    _visible = False


def show() -> None:
    """Redraw the block at the current cursor position (no value change)."""
    global _visible
    if _visible or not _is_tty():
        return
    if _top or _bottom:
        _draw_block()
        sys.stdout.flush()
        _visible = True


def emit(text: str = "") -> None:
    """
    Print a message above the floating status block. The block is erased,
    the text prints (may be multi-line), then the block re-renders below.
    """
    global _visible
    if not _is_tty():
        print(text, flush=True)
        return

    was_visible = _visible
    if was_visible:
        _erase_block()
        _visible = False
    if text:
        sys.stdout.write(text + "\n")
    if was_visible:
        _draw_block()
        _visible = True
    sys.stdout.flush()


def enable() -> None:
    """Reserved for setup parity with previous API. Currently a no-op."""
    pass


def disable() -> None:
    """Hide the block cleanly on exit."""
    hide()


def shorten_url(url: str, max_len: int = 80) -> str:
    """Truncate a long URL with a middle ellipsis, preserving both ends."""
    if len(url) <= max_len:
        return url
    keep_head = max_len // 2 - 2
    keep_tail = max_len - keep_head - 3
    return url[:keep_head] + "..." + url[-keep_tail:]
