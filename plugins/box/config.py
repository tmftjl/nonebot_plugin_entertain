from __future__ import annotations

from pathlib import Path
from typing import List, Tuple

from pydantic import BaseModel, Field

from ...config import register_plugin_config


class Config(BaseModel):
    """Box plugin configuration.

    Stored under config/box/config.json (auto-created with defaults).
    """

    auto_box: bool = False
    only_admin: bool = False
    auto_box_groups: List[str] = Field(default_factory=list)
    box_blacklist: List[str] = Field(default_factory=list)


CFG = register_plugin_config("box", defaults=Config().dict())


def load_config() -> Tuple[Config, Path]:
    try:
        data = CFG.load()
        return Config.parse_obj(data), CFG.path
    except Exception:
        # fallback to defaults
        return Config(), CFG.path


plugin_config, plugin_config_path = load_config()

