from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

from ...core.api import (
    config_dir,
    plugin_resource_dir,
    plugin_data_dir,
    register_plugin_config,
    register_plugin_schema,
    register_reload_callback,
)


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

# 模块级缓存
_CACHED: Dict[str, Any] = REG.load()


def reload_cache() -> None:
    """重新加载配置到模块级缓存，供框架重载配置时调用。"""
    global _CACHED
    _CACHED = REG.load()


# 注册重载回调
register_reload_callback("df", reload_cache)

# Schema for frontend (Chinese labels and help)
DF_SCHEMA: Dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "title": "DF 插件配置",
    "properties": {
        "random_picture_open": {
            "type": "boolean",
            "title": "启用随机图片",
            "description": "启用后响应‘来张/看看/随机 + 关键词’等随机图片命令，以及本地表情库",
            "default": True,
            "x-group": "随机图片",
            "x-order": 1,
        },
        "poke_repo": {
            "type": "string",
            "title": "表情图库仓库",
            "description": "DF 表情图库（戳一戳图片）Git 仓库地址，用于更新本地资源",
            "default": "https://cnb.cool/denfenglai/poke.git",
            "x-group": "随机图片",
            "x-order": 2,
        },
        "poke": {
            "type": "object",
            "title": "戳一戳回复",
            "description": "配置收到戳一戳时的图片/文本回复策略",
            "x-group": "戳一戳",
            "x-order": 10,
            "properties": {
                "chuo": {
                    "type": "boolean",
                    "title": "启用戳一戳",
                    "description": "是否响应戳一戳事件",
                    "default": True,
                    "x-order": 1,
                },
                "mode": {
                    "type": "string",
                    "title": "回复模式",
                    "description": "random=随机 image/text/mix 三种之一；image=仅图片；text=仅文本；mix=图文",
                    "enum": ["random", "image", "text", "mix"],
                    "default": "random",
                    "x-order": 2,
                },
                "imageType": {
                    "type": "string",
                    "title": "图片类型/表情名",
                    "description": "all 表示任意本地表情；或指定某个表情目录名",
                    "default": "all",
                    "x-order": 3,
                },
                "imageBlack": {
                    "type": "array",
                    "title": "屏蔽表情",
                    "description": "不参与随机的表情名称列表",
                    "items": {"type": "string"},
                    "default": [],
                    "x-order": 4,
                },
                "textMode": {
                    "type": "string",
                    "title": "文本来源",
                    "description": "hitokoto=随机一言; list=从自定义列表随机",
                    "enum": ["hitokoto", "list"],
                    "default": "hitokoto",
                    "x-order": 5,
                },
                "hitokoto_api": {
                    "type": "string",
                    "title": "一言 API",
                    "description": "当文本来源为 hitokoto 时调用的 API",
                    "default": "https://v1.hitokoto.cn/?encode=text",
                    "x-order": 6,
                },
                "textList": {
                    "type": "array",
                    "title": "自定义文本列表",
                    "description": "当文本来源为 list 时，从该列表中随机选择",
                    "items": {"type": "string"},
                    "default": [],
                    "x-order": 7,
                },
            },
        },
        "send_master": {
            "type": "object",
            "title": "转发给主人",
            "description": "部分命令的反馈将转发给主人账号，可配置频率与提示文字",
            "x-group": "主人转发",
            "x-order": 20,
            "properties": {
                "open": {
                    "type": "boolean",
                    "title": "启用",
                    "description": "是否开启转发给主人",
                    "default": True,
                    "x-order": 1,
                },
                "cd": {
                    "type": "integer",
                    "title": "冷却(秒)",
                    "description": "0 表示关闭冷却",
                    "default": 0,
                    "minimum": 0,
                    "x-order": 2,
                },
                "success": {
                    "type": "string",
                    "title": "成功提示",
                    "description": "转发成功时给用户的提示语",
                    "default": "已将信息转发给主人",
                    "x-order": 3,
                },
                "failed": {
                    "type": "string",
                    "title": "失败提示",
                    "description": "转发失败时给用户的提示语",
                    "default": "发送失败，请稍后重试",
                    "x-order": 4,
                },
                "reply_prefix": {
                    "type": "string",
                    "title": "回复前缀",
                    "description": "主人回复用户时的前缀文字",
                    "default": "主人回复：",
                    "x-order": 5,
                },
            },
        },
    },
}

try:
    register_plugin_schema("df", DF_SCHEMA)
except Exception:
    pass


def ensure_dirs() -> None:
    RES_DF_DIR.mkdir(parents=True, exist_ok=True)
    POKE_DIR.mkdir(parents=True, exist_ok=True)
    DATA_DF_DIR.mkdir(parents=True, exist_ok=True)


def load_cfg() -> Dict[str, Any]:
    """从模块级缓存读取配置。"""
    ensure_dirs()
    return _CACHED


def save_cfg(cfg: Dict[str, Any]) -> None:
    """保存配置并更新模块级缓存。"""
    ensure_dirs()
    REG.save(cfg)
    # 保存后立即更新缓存
    reload_cache()


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

