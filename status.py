"""
Persistent bottom-of-terminal status bar.

Reserves the last terminal row via ANSI scroll-region escape codes so a
status line survives scrolling. All normal output prints above the bar
and scrolls naturally; the bar updates in place via cursor save/restore.

Falls back to a no-op if stdout is not a TTY (e.g. piped output, CI).
"""

from __future__ import annotations
import atexit
import shutil
import signal
import sys

_CSI = "\033["
_active = False
_last_text = ""


def _is_tty() -> bool:
    try:
        return sys.stdout.isatty()
    except Exception:
        return False


def _term_rows() -> int:
    return shutil.get_terminal_size((80, 24)).lines


def enable() -> None:
    """Reserve the last terminal row. No-op if not a TTY or already enabled."""
    global _active
    if _active or not _is_tty():
        return
    rows = _term_rows()
    # Make sure the status row is below any existing content, then set the
    # scroll region to everything above it.
    sys.stdout.write(f"\n{_CSI}{rows - 1};1H")
    sys.stdout.write(f"{_CSI}1;{rows - 1}r")
    sys.stdout.write(f"{_CSI}{rows - 1};1H")
    sys.stdout.flush()
    atexit.register(disable)
    try:
        signal.signal(signal.SIGWINCH, _on_resize)
    except Exception:
        pass  # Windows or restricted environment
    _active = True


def disable() -> None:
    """Restore default scroll region and clear the status row."""
    global _active
    if not _active:
        return
    rows = _term_rows()
    sys.stdout.write(f"{_CSI}r")           # reset scroll region
    sys.stdout.write(f"{_CSI}{rows};1H")   # move to status row
    sys.stdout.write(f"{_CSI}2K")          # clear it
    sys.stdout.flush()
    _active = False


def render(text: str) -> None:
    """Update the bottom bar; falls back to a normal print if not active."""
    global _last_text
    _last_text = text
    if not _active:
        print(text, flush=True)
        return
    rows = _term_rows()
    sys.stdout.write(f"{_CSI}s")                  # save cursor
    sys.stdout.write(f"{_CSI}{rows};1H")          # move to status row
    sys.stdout.write(f"{_CSI}2K")                 # clear it
    sys.stdout.write(text)
    sys.stdout.write(f"{_CSI}u")                  # restore cursor
    sys.stdout.flush()


def _on_resize(_signum, _frame) -> None:
    """Re-apply the scroll region after a terminal resize."""
    if not _active:
        return
    rows = _term_rows()
    sys.stdout.write(f"{_CSI}1;{rows - 1}r")
    sys.stdout.flush()
    render(_last_text)
