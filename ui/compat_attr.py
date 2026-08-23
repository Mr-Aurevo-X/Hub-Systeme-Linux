# SPDX-License-Identifier: GPL-3.0-or-later
"""GI-free hasattr helpers for Mint 21.3 / CachyOS widget fallbacks."""

from __future__ import annotations

from typing import Any


def first_attr(obj: object, *names: str) -> Any:
    """Return the first present attribute, else None. Modern names first."""
    for name in names:
        value = getattr(obj, name, None)
        if value is not None:
            return value
    return None


def call_if_present(obj: object, name: str, *args: Any, **kwargs: Any) -> bool:
    """Call ``obj.name(*args, **kwargs)`` when it exists. Return True if called."""
    fn = getattr(obj, name, None)
    if not callable(fn):
        return False
    fn(*args, **kwargs)
    return True
