from __future__ import annotations

from pathlib import Path
from typing import Optional
import os


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
    """Return a writable config directory.

    Preference order:
    1) Env var `NPE_CONFIG_DIR` when set
    2) Package-root `config/` if writable
    3) Current working directory `./config/`
    """

    def _writable_dir(p: Path) -> bool:
        try:
            p.mkdir(parents=True, exist_ok=True)
            test = p / ".npe_write_test"
            test.write_text("ok", encoding="utf-8")
            try:
                test.unlink()
            except Exception:
                pass
            return True
        except Exception:
            return False

    # 1) explicit env override
    env_dir = os.getenv("NPE_CONFIG_DIR")
    if env_dir:
        root = Path(env_dir)
        if not _writable_dir(root):
            # fall back if env path is not writable
            root = None  # type: ignore[assignment]
        else:
            if name:
                sub = root / name
                sub.mkdir(parents=True, exist_ok=True)
                return sub
            return root

    # 2) try package-root config
    pkg_root = _root() / "config"
    if _writable_dir(pkg_root):
        if name:
            sub = pkg_root / name
            sub.mkdir(parents=True, exist_ok=True)
            return sub
        return pkg_root

    # 3) last resort: cwd/config
    cwd_root = Path.cwd() / "config"
    cwd_root.mkdir(parents=True, exist_ok=True)
    if name:
        sub = cwd_root / name
        sub.mkdir(parents=True, exist_ok=True)
        return sub
    return cwd_root


def plugin_resource_dir(name: str) -> Path:
    """Return plugins/<name>/resource/, creating it if missing."""
    base = _root() / "plugins" / name / "resource"
    base.mkdir(parents=True, exist_ok=True)
    return base


def plugin_data_dir(name: str) -> Path:
    """Return plugins/<name>/data/, creating it if missing."""
    base = _root() / "plugins" / name / "data"
    base.mkdir(parents=True, exist_ok=True)
    return base
