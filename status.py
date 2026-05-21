"""
Persistent two-line status panel at the bottom of the terminal.

Reserves the last two rows via ANSI scroll-region escape codes:
  • top row    — current operation (e.g. "Reading: https://...")
  • bottom row — field-completeness progress bar

All normal output prints above this panel and scrolls naturally; the panel
updates in place via cursor save/restore. Falls back to a no-op if stdout
is not a TTY (e.g. piped output, CI).
"""

from __future__ import annotations
import atexit
import shutil
import signal
import sys

_CSI = "\033["
_LINES = 2
_active = False
_top = ""
_bottom = ""


def _is_tty() -> bool:
    try:
        return sys.stdout.isatty()
    except Exception:
        return False


def _term_rows() -> int:
    return shutil.get_terminal_size((80, 24)).lines


def _term_cols() -> int:
    return shutil.get_terminal_size((80, 24)).columns


def enable() -> None:
    """Reserve the last two terminal rows. No-op if not a TTY or already enabled."""
    global _active
    if _active or not _is_tty():
        return
    rows = _term_rows()
    # Ensure the panel rows are below any existing content, then set the
    # scroll region to everything above them.
    sys.stdout.write("\n" * _LINES)
    sys.stdout.write(f"{_CSI}{rows - _LINES};1H")
    sys.stdout.write(f"{_CSI}1;{rows - _LINES}r")
    sys.stdout.write(f"{_CSI}{rows - _LINES};1H")
    sys.stdout.flush()
    atexit.register(disable)
    try:
        signal.signal(signal.SIGWINCH, _on_resize)
    except Exception:
        pass  # Windows or restricted environment
    _active = True


def disable() -> None:
    """Restore default scroll region and clear the reserved rows."""
    global _active
    if not _active:
        return
    rows = _term_rows()
    sys.stdout.write(f"{_CSI}r")                       # reset scroll region
    for offset in range(_LINES):
        sys.stdout.write(f"{_CSI}{rows - offset};1H{_CSI}2K")
    sys.stdout.flush()
    _active = False


def render(*, top: str | None = None, bottom: str | None = None) -> None:
    """
    Update the status panel. Either argument may be omitted to leave
    that line unchanged. Falls back to a normal print if not active.
    """
    global _top, _bottom
    if top is not None:
        _top = top
    if bottom is not None:
        _bottom = bottom

    if not _active:
        if top is not None:
            print(top, flush=True)
        if bottom is not None:
            print(bottom, flush=True)
        return

    rows = _term_rows()
    sys.stdout.write(f"{_CSI}s")                       # save cursor
    sys.stdout.write(f"{_CSI}{rows - 1};1H{_CSI}2K{_top}")
    sys.stdout.write(f"{_CSI}{rows};1H{_CSI}2K{_bottom}")
    sys.stdout.write(f"{_CSI}u")                       # restore cursor
    sys.stdout.flush()


def _on_resize(_signum, _frame) -> None:
    """Re-apply the scroll region and redraw after a terminal resize."""
    if not _active:
        return
    rows = _term_rows()
    sys.stdout.write(f"{_CSI}1;{rows - _LINES}r")
    sys.stdout.flush()
    render(top=_top, bottom=_bottom)


def shorten_url(url: str, max_len: int = 80) -> str:
    """Truncate a long URL with an ellipsis in the middle, preserving both ends."""
    if len(url) <= max_len:
        return url
    keep_head = max_len // 2 - 2
    keep_tail = max_len - keep_head - 3
    return url[:keep_head] + "..." + url[-keep_tail:]
