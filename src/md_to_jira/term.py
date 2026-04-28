"""Terminal styling helpers — ANSI colours that no-op when output isn't a TTY.

We don't take a dep on `rich` or `colorama`. The colour set is small —
exactly what we need for the CLI's interactive surfaces (init, whoami,
lint). Respects the [NO_COLOR convention](https://no-color.org/) and
auto-disables when stdout isn't a TTY (so piped output and CI logs stay
clean).
"""

from __future__ import annotations

import os
import sys

# ANSI escape sequences. Keep the palette small — too much colour is
# worse than none at all.
_RESET = "\033[0m"
_BOLD = "\033[1m"
_DIM = "\033[2m"
_RED = "\033[31m"
_GREEN = "\033[32m"
_YELLOW = "\033[33m"
_BLUE = "\033[34m"
_MAGENTA = "\033[35m"
_CYAN = "\033[36m"
_GRAY = "\033[90m"


def _enabled() -> bool:
    """Decide whether to emit colour codes at all.

    Honours NO_COLOR (any value), FORCE_COLOR (any value, overrides TTY
    check — useful for tests and CI dashboards that *do* render colour),
    and otherwise falls back to "is stdout a real TTY".
    """
    if "NO_COLOR" in os.environ:
        return False
    if os.environ.get("FORCE_COLOR"):
        return True
    return sys.stdout.isatty()


def _wrap(code: str, text: str) -> str:
    if not _enabled():
        return text
    return f"{code}{text}{_RESET}"


def bold(text: str) -> str:
    return _wrap(_BOLD, text)


def dim(text: str) -> str:
    return _wrap(_DIM, text)


def red(text: str) -> str:
    return _wrap(_RED, text)


def green(text: str) -> str:
    return _wrap(_GREEN, text)


def yellow(text: str) -> str:
    return _wrap(_YELLOW, text)


def blue(text: str) -> str:
    return _wrap(_BLUE, text)


def magenta(text: str) -> str:
    return _wrap(_MAGENTA, text)


def cyan(text: str) -> str:
    return _wrap(_CYAN, text)


def gray(text: str) -> str:
    return _wrap(_GRAY, text)


# Pre-baked semantic helpers — easier to read at the call site than
# `green("✓") + " " + bold(...)` repeated everywhere.


def tick(text: str = "") -> str:
    """Green checkmark — for successes."""
    mark = green("✓")
    return f"{mark} {text}" if text else mark


def cross(text: str = "") -> str:
    """Red cross — for failures."""
    mark = red("✗")
    return f"{mark} {text}" if text else mark


def warn(text: str = "") -> str:
    """Yellow exclamation — for warnings, not errors."""
    mark = yellow("!")
    return f"{mark} {text}" if text else mark


def header(text: str) -> str:
    """Bold magenta heading — for section titles in init / whoami."""
    return bold(magenta(text))


def prompt_label(text: str) -> str:
    """Cyan label for an interactive prompt question."""
    return cyan(text)


def hint(text: str) -> str:
    """Dim gray helper text — for parenthetical guidance."""
    return gray(text)


def value(text: str) -> str:
    """Bold for emphasised values (keys, URLs, paths)."""
    return bold(text)
