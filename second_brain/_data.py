"""Locate the public data files in both supported layouts.

* wheel install:            site-packages/second_brain/data/  (package data)
* source checkout or image: <repository>/data/                 (Dockerfile COPY . ., PYTHONPATH=.)

The wheel never ships a top-level ``data`` package; this resolver is the only place
that knows both layouts, so every reader sees the same bytes either way.
"""
from __future__ import annotations

from pathlib import Path

_PACKAGE_DIR = Path(__file__).resolve().parent
_SENTINEL = "manifest.json"


def data_dir() -> Path:
    """Return the directory that holds the public corpus, frontier state, and locks."""
    installed = _PACKAGE_DIR / "data"
    if (installed / _SENTINEL).is_file():
        return installed
    return _PACKAGE_DIR.parent / "data"


def data_file(name: str) -> Path:
    """Return the path of one public data file (existence is checked by the reader)."""
    return data_dir() / name
