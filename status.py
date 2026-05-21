"""
A two-line live status block that floats at the visible bottom of output.

set(top=, bottom=)   update one or both lines; the block redraws in place
hide()               erase the block; next set() will redraw it
emit(text)           print text above the block, then redraw the block
shorten_url(url)     middle-ellipsis truncation for long URLs

Each rendered line is hard-truncated to terminal width so that the
in-place redraw (cursor move up exactly two physical rows) is reliable.
Wrapping is what makes "in-place" stop working — once any status line
wraps to a second row, the cursor calculation is off and old content
gets stranded in scrollback.

Only relative cursor moves and line clears are used (\\033[2A,
\\033[0J, \\033[2K) — supported on every VT100-compatible terminal.
Falls back to plain print() when stdout is not a TTY.
"""

from __future__ import annotations
import re
import shutil
import sys

_CSI = "\033["
_ANSI = re.compile(r"\033\[[0-9;]*m")

_top = ""
_bottom = ""
_visible = False


def _is_tty() -> bool:
    try:
        return sys.stdout.isatty()
    except Exception:
        return False


def _term_cols() -> int:
    return shutil.get_terminal_size((80, 24)).columns


def _visible_len(s: str) -> int:
    """Length of s ignoring ANSI colour escape sequences."""
    return len(_ANSI.sub("", s))


def _truncate(s: str, max_cols: int) -> str:
    """Truncate to max_cols visible characters, keeping ANSI codes intact."""
    if _visible_len(s) <= max_cols:
        return s
    out: list[str] = []
    seen = 0
    i = 0
    n = len(s)
    limit = max(1, max_cols - 1)  # leave room for the ellipsis
    while i < n:
        m = _ANSI.match(s, i)
        if m:
            out.append(m.group())
            i = m.end()
            continue
        if seen >= limit:
            break
        out.append(s[i])
        seen += 1
        i += 1
    out.append("…\033[0m")
    return "".join(out)


def _erase_block() -> None:
    """
    Cursor is one row below the bottom of the block. Walk up two rows,
    clearing each line explicitly. More reliable than \\033[0J which has
    inconsistent semantics across terminals when the cursor sits at the
    bottom of the screen and a scroll is implied.
    """
    sys.stdout.write(f"{_CSI}1A\r{_CSI}2K")
    sys.stdout.write(f"{_CSI}1A\r{_CSI}2K")


def _draw_block() -> None:
    """Write the two truncated status lines from the current cursor position."""
    cols = _term_cols() - 1
    top_line = _truncate(_top, cols) if _top else ""
    bot_line = _truncate(_bottom, cols) if _bottom else ""
    sys.stdout.write(f"{top_line}\n{bot_line}\n")


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
    """Erase the block; next set() or show() will redraw it."""
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
    Print text above the floating status block (multi-line text supported).
    The block is erased, the text prints, then the block redraws below it.

    Each printed physical row is hard-truncated to terminal width so a long
    string can't wrap and desynchronise the next _erase_block (which moves
    up exactly two physical rows). Embedded \\n is honoured and each line
    is truncated independently.
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
        cols = _term_cols() - 1
        for line in text.split("\n"):
            sys.stdout.write(_truncate(line, cols) + "\n")
    if was_visible:
        _draw_block()
        _visible = True
    sys.stdout.flush()


def enable() -> None:
    pass


def disable() -> None:
    hide()


def shorten_url(url: str, max_len: int = 80) -> str:
    """Truncate a long URL with a middle ellipsis, preserving both ends."""
    if len(url) <= max_len:
        return url
    keep_head = max_len // 2 - 2
    keep_tail = max_len - keep_head - 3
    return url[:keep_head] + "..." + url[-keep_tail:]
