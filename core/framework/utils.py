from __future__ import annotations

from pathlib import Path
from typing import Optional
import os


def _root() -> Path:
    # Package root (nonebot_plugin_entertain)
    # file is .../core/framework/utils.py -> parents[2] is package root
    return Path(__file__).resolve().parents[2]


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

    Note: Directory writability is checked by attempting to create the directory,
    not by writing test files, for better performance.
    """

    def _ensure_dir(p: Path) -> bool:
        """Ensure directory exists and is accessible."""
        try:
            p.mkdir(parents=True, exist_ok=True)
            # 检查目录是否可访问（不写入测试文件）
            return p.exists() and p.is_dir()
        except Exception:
            return False

    # 1) explicit env override
    env_dir = os.getenv("NPE_CONFIG_DIR")
    if env_dir:
        root = Path(env_dir)
        if _ensure_dir(root):
            if name:
                sub = root / name
                sub.mkdir(parents=True, exist_ok=True)
                return sub
            return root

    # 2) try package-root config (package root is two levels up)
    pkg_root = _root() / "config"
    if _ensure_dir(pkg_root):
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
