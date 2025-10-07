from __future__ import annotations

import json
from pathlib import Path
from typing import List, Tuple

from pydantic import BaseModel, Field

from ...utils import config_dir


class Config(BaseModel):
    """Box plugin configuration (centralized).

    Stored under nonebot_plugin_entertain/config/config.json
    """

    auto_box: bool = False
    only_admin: bool = False
    auto_box_groups: List[str] = Field(default_factory=list)
    box_blacklist: List[str] = Field(default_factory=list)


CONFIG_DIR = config_dir()
CONFIG_PATH = CONFIG_DIR / "config.json"


def _read_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def load_config() -> Tuple[Config, Path]:
    if CONFIG_PATH.exists():
        try:
            data = _read_json(CONFIG_PATH)
            cfg = Config.parse_obj(data)
            return cfg, CONFIG_PATH
        except Exception:
            pass
    default_cfg = Config()
    try:
        _write_json(CONFIG_PATH, default_cfg.dict())
    except Exception:
        pass
    return default_cfg, CONFIG_PATH


plugin_config, plugin_config_path = load_config()
