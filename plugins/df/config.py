from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

from ...utils import config_dir, plugin_resource_dir, plugin_data_dir
from ...config import register_plugin_config


CFG_DIR = config_dir("df")
CFG_PATH = CFG_DIR / "config.json"
RES_DF_DIR = plugin_resource_dir("df")
POKE_DIR = RES_DF_DIR / "poke"
DATA_DF_DIR = plugin_data_dir("df")


DEFAULT_CFG: Dict[str, Any] = {
    "random_picture_open": True,
    # Git repo for DF face-pack gallery (poke images)
    "poke_repo": "https://cnb.cool/denfenglai/poke.git",
    "poke": {
        "chuo": True,
        "mode": "random",  # image | text | mix | random
        "imageType": "all",  # name or all
        "imageBlack": [],
        "textMode": "hitokoto",  # hitokoto | list
        "hitokoto_api": "https://v1.hitokoto.cn/?encode=text",
        "textList": [],
    },
    "send_master": {
        "open": True,
        "cd": 0,  # seconds; 0 to disable
        "success": "已将消息转发给主人",
        "failed": "发送失败，请稍后重试",
        "reply_prefix": "主人回复：",
    },
}

# Register unified config and ensure default file exists
REG = register_plugin_config("df", DEFAULT_CFG)


def ensure_dirs() -> None:
    RES_DF_DIR.mkdir(parents=True, exist_ok=True)
    POKE_DIR.mkdir(parents=True, exist_ok=True)
    DATA_DF_DIR.mkdir(parents=True, exist_ok=True)


def load_cfg() -> Dict[str, Any]:
    ensure_dirs()
    return REG.load()


def save_cfg(cfg: Dict[str, Any]) -> None:
    ensure_dirs()
    REG.save(cfg)


def face_list() -> List[str]:
    """Return available face-pack names from resource/df/poke subdirectories."""
    ensure_dirs()
    names: List[str] = []
    try:
        for p in POKE_DIR.iterdir():
            if p.is_dir() and p.name != ".git":
                names.append(p.name)
    except Exception:
        pass
    # ensure at least 'default' for API fallback behaviour
    return sorted(set(names or ["default"]))


def random_local_image(face: str) -> Optional[Path]:
    """Pick a random file path from a face-pack dir if exists; otherwise None."""
    d = POKE_DIR / face
    if not d.exists() or not d.is_dir():
        return None
    try:
        files = [p for p in d.iterdir() if p.is_file()]
        if not files:
            return None
        import random

        return random.choice(files)
    except Exception:
        return None

