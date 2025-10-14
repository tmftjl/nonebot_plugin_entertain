from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

from ...core.api import config_dir, plugin_resource_dir, plugin_data_dir, register_plugin_config


CFG_DIR = config_dir("df")
CFG_PATH = CFG_DIR / "config.json"
RES_DF_DIR = plugin_resource_dir("df")
POKE_DIR = RES_DF_DIR / "poke"
DATA_DF_DIR = plugin_data_dir("df")


DEFAULT_CFG: Dict[str, Any] = {
    "random_picture_open": True,
    # DF 表情图库（戳一戳图片）仓库地址
    "poke_repo": "https://cnb.cool/denfenglai/poke.git",
    "poke": {
        "chuo": True,
        "mode": "random",  # image | text | mix | random
        "imageType": "all",  # 名称或 all
        "imageBlack": [],
        "textMode": "hitokoto",  # hitokoto | list
        "hitokoto_api": "https://v1.hitokoto.cn/?encode=text",
        "textList": [],
    },
    "send_master": {
        "open": True,
        "cd": 0,  # 秒；0 表示关闭
        "success": "已将信息转发给主人",
        "failed": "发送失败，请稍后重试",
        "reply_prefix": "主人回复：",
    },
}


def _validate_cfg(cfg: Dict[str, Any]) -> None:
    def _type(name: str, exp, cond=True):
        if not cond:
            return
        if name in cfg and not isinstance(cfg[name], exp):
            raise ValueError(f"{name} must be {exp}")

    _type("random_picture_open", bool)
    _type("poke_repo", str)

    poke = cfg.get("poke", {})
    if poke and not isinstance(poke, dict):
        raise ValueError("poke must be object")
    if isinstance(poke, dict):
        if "chuo" in poke and not isinstance(poke["chuo"], bool):
            raise ValueError("poke.chuo must be bool")
        if "mode" in poke:
            if poke["mode"] not in {"random", "image", "text", "mix"}:
                raise ValueError("poke.mode invalid")
        if "imageType" in poke and not isinstance(poke["imageType"], str):
            raise ValueError("poke.imageType must be str")
        if "imageBlack" in poke and not isinstance(poke["imageBlack"], list):
            raise ValueError("poke.imageBlack must be list")
        if "textMode" in poke and poke["textMode"] not in {"hitokoto", "list"}:
            raise ValueError("poke.textMode invalid")
        if "hitokoto_api" in poke and not isinstance(poke["hitokoto_api"], str):
            raise ValueError("poke.hitokoto_api must be str")
        if "textList" in poke and not isinstance(poke["textList"], list):
            raise ValueError("poke.textList must be list")

    sm = cfg.get("send_master", {})
    if sm and not isinstance(sm, dict):
        raise ValueError("send_master must be object")
    if isinstance(sm, dict):
        if "open" in sm and not isinstance(sm["open"], bool):
            raise ValueError("send_master.open must be bool")
        if "cd" in sm:
            try:
                cd = int(sm["cd"])  # 允许近似整数
                if cd < 0:
                    raise ValueError
            except Exception:
                raise ValueError("send_master.cd must be non-negative int")
        for k in ("success", "failed", "reply_prefix"):
            if k in sm and not isinstance(sm[k], str):
                raise ValueError(f"send_master.{k} must be str")

# 注册插件配置
REG = register_plugin_config("df", DEFAULT_CFG, validator=_validate_cfg)


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
    """返回 resource/df/poke 下可用的表情包名称列表。"""
    ensure_dirs()
    names: List[str] = []
    try:
        for p in POKE_DIR.iterdir():
            if p.is_dir() and p.name != ".git":
                names.append(p.name)
    except Exception:
        pass
    return sorted(set(names or ["default"]))


def random_local_image(face: str) -> Optional[Path]:
    """从本地表情包目录随机选择一个文件路径，若不存在则返回 None。"""
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

