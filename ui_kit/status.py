# SPDX-License-Identifier: GPL-3.0-or-later
"""Semantic status classes for labels and log lines."""

from __future__ import annotations

from typing import Literal

StatusKind = Literal["default", "ok", "warn", "error"]


def css_class(kind: StatusKind) -> str:
    if kind == "ok":
        return "uni-status-ok"
    if kind == "warn":
        return "uni-status-warn"
    if kind == "error":
        return "uni-status-error"
    return "uni-status-default"


def add_status_class(label: object, kind: StatusKind) -> None:
    cls = css_class(kind)
    add = getattr(label, "add_css_class", None)
    if callable(add):
        add(cls)
