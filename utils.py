from __future__ import annotations

from pathlib import Path
from typing import Optional


def _root() -> Path:
    # Anchor to this package location to be robust across CWDs
    return Path(__file__).parent


def data_dir(name: Optional[str] = None) -> Path:
    base = _root() / "data"
    base.mkdir(parents=True, exist_ok=True)
    if name:
        p = base / name
        p.mkdir(parents=True, exist_ok=True)
        return p
    return base


def resource_dir() -> Path:
    p = _root() / "resource"
    p.mkdir(parents=True, exist_ok=True)
    return p


def config_dir(name: Optional[str] = None) -> Path:
    base = _root() / "config"
    base.mkdir(parents=True, exist_ok=True)
    if name:
        p = base / name
        p.mkdir(parents=True, exist_ok=True)
        return p
    return base
