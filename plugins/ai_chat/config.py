"""AI 对话配置（api 使用数组形式）

- 注册并管理 `config/ai_chat/config.json`
- 提供 Pydantic 配置对象供代码内部访问
- 管理 `config/ai_chat/personas.json`
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional, List, Tuple
import zipfile
import xml.etree.ElementTree as ET

from nonebot.log import logger
from pydantic import BaseModel, Field

from ...core.api import (
    register_plugin_config,
    register_plugin_schema,
    register_reload_callback,
)
from ...core.framework.utils import config_dir


# ==================== Pydantic 配置对象 ====================


class APIConfig(BaseModel):
    """AI 服务商配置（通过唯一 name 标识）"""

    name: str = Field(description="唯一名称，用于切换服务商")
    base_url: str = Field(default="https://api.openai.com/v1", description="API 基础地址")
    api_key: str = Field(default="", description="API 密钥")
    model: str = Field(default="gpt-4o-mini", description="默认模型")
    timeout: int = Field(default=60, description="超时时间（秒）")


class SessionConfig(BaseModel):
    """会话配置"""

    api_active: str = Field(default="default", description="当前启用的服务商名称（匹配 api[].name）")
    default_temperature: float = Field(default=0.7, description="默认温度")
    max_rounds: int = Field(default=8, description="最大上下文轮数（user+assistant 记为一轮）")
    chatroom_history_max_lines: int = Field(default=200, description="群聊聊天室记忆最大行数（内存）")
    active_reply_enable: bool = Field(default=False, description="是否启用群聊主动回复（实验）")
    active_reply_probability: float = Field(default=0.1, description="主动回复触发概率（0~1）")
    active_reply_prompt_suffix: str = Field(
        default=(
            "现在有一条新消息到达：`{message}`。请做出自然、简洁的回复。"
            "只输出回复正文，不要包含额外说明。"
        ),
        description="主动回复场景下附加的提示（支持占位符 {message}/{prompt}）",
    )


class ToolsConfig(BaseModel):
    """工具配置"""

    enabled: bool = Field(default=False, description="是否启用工具")
    max_iterations: int = Field(default=3, description="最多工具调用迭代次数")
    builtin_tools: list[str] = Field(
        default_factory=lambda: ["get_time", "get_weather"], description="内置工具"
    )


class AIChatConfig(BaseModel):
    """AI 对话总配置"""

    # api 使用数组形式：[APIConfig, ...]
    api: List[APIConfig] = Field(default_factory=list, description="AI 服务商配置（数组）")
    session: SessionConfig = Field(default_factory=SessionConfig)
    tools: ToolsConfig = Field(default_factory=ToolsConfig)


class PersonaConfig(BaseModel):
    """人格配置"""

    name: str = Field(description="人格名称")
    description: str = Field(description="人格描述")
    system_prompt: str = Field(description="系统提示词")


# ==================== 默认值与前端 Schema ====================


DEFAULTS: Dict[str, Any] = {
    "api": [
        {
            "name": "default",
            "base_url": "https://api.openai.com/v1",
            "api_key": "",
            "model": "gpt-4o-mini",
            "timeout": 60,
        }
    ],
    "session": {
        "api_active": "default",
        "default_temperature": 0.7,
        "max_rounds": 8,
        "chatroom_history_max_lines": 200,
        "active_reply_enable": False,
        "active_reply_prompt_suffix": (
            "现在有一条新消息到达：`{message}`。请做出自然、简洁的回复。"
            "只输出回复正文，不要包含额外说明。"
        ),
        "active_reply_probability": 0.1,
    },
    "tools": {
        "enabled": False,
        "max_iterations": 3,
        "builtin_tools": ["get_time", "get_weather"],
    },
}


# 注册统一配置文件（config/ai_chat/config.json）
CFG = register_plugin_config("ai_chat", DEFAULTS)


AI_CHAT_SCHEMA: Dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "title": "AI 对话",
    "properties": {
        "api": {
            "type": "array",
            "title": "AI 服务商（数组）",
            "x-order": 1,
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "title": "名称", "x-order": 1},
                    "base_url": {
                        "type": "string",
                        "title": "API 地址",
                        "default": DEFAULTS["api"][0]["base_url"],
                        "x-order": 2,
                    },
                    "api_key": {
                        "type": "string",
                        "title": "API 密钥",
                        "default": DEFAULTS["api"][0]["api_key"],
                        "x-order": 3,
                    },
                    "model": {
                        "type": "string",
                        "title": "默认模型",
                        "default": DEFAULTS["api"][0]["model"],
                        "x-order": 4,
                    },
                    "timeout": {
                        "type": "integer",
                    "title": "超时（秒）",
                        "minimum": 1,
                        "maximum": 300,
                        "default": DEFAULTS["api"][0]["timeout"],
                        "x-order": 5,
                    },
                },
                "required": ["name"],
            },
        },
        "session": {
            "type": "object",
            "title": "会话",
            "x-order": 4,
            "x-collapse": True,
            "properties": {
                "api_active": {
                    "type": "string",
                    "title": "当前启用服务商名",
                    "default": DEFAULTS["session"]["api_active"],
                    "x-order": 2,
                },
                "default_temperature": {
                    "type": "number",
                    "title": "默认温度",
                    "minimum": 0,
                    "maximum": 2,
                    "default": DEFAULTS["session"]["default_temperature"],
                    "x-order": 1,
                },
                "max_rounds": {
                    "type": "integer",
                    "title": "最大上下文轮数",
                    "minimum": 1,
                    "maximum": 50,
                    "default": DEFAULTS["session"]["max_rounds"],
                    "x-order": 3,
                },
                "chatroom_history_max_lines": {
                    "type": "integer",
                    "title": "聊天室记忆最大行数",
                    "minimum": 1,
                    "maximum": 5000,
                    "default": DEFAULTS["session"]["chatroom_history_max_lines"],
                    "x-order": 4,
                },
                "active_reply_enable": {
                    "type": "boolean",
                    "title": "群聊启用主动回复（实验）",
                    "default": DEFAULTS["session"]["active_reply_enable"],
                    "x-order": 5,
                },
                "active_reply_probability": {
                    "type": "number",
                    "title": "主动回复触发概率 0~1",
                    "minimum": 0,
                    "maximum": 1,
                    "default": DEFAULTS["session"]["active_reply_probability"],
                    "x-order": 6,
                },
                "active_reply_prompt_suffix": {
                    "type": "string",
                    "title": "主动回复提示后缀",
                    "default": DEFAULTS["session"]["active_reply_prompt_suffix"],
                    "x-order": 7,
                },
            },
        },
        "tools": {
            "type": "object",
            "title": "工具",
            "x-order": 6,
            "x-collapse": True,
            "properties": {
                "enabled": {
                    "type": "boolean",
                    "title": "启用工具",
                    "default": DEFAULTS["tools"]["enabled"],
                    "x-order": 1,
                },
                "max_iterations": {
                    "type": "integer",
                    "title": "最多工具迭代次数",
                    "minimum": 1,
                    "maximum": 10,
                    "default": DEFAULTS["tools"]["max_iterations"],
                    "x-order": 2,
                },
                "builtin_tools": {
                    "type": "array",
                    "title": "内置工具",
                    "items": {"type": "string"},
                    "default": DEFAULTS["tools"]["builtin_tools"],
                    "x-order": 3,
                },
            },
        },
    },
}

register_plugin_schema("ai_chat", AI_CHAT_SCHEMA)


# ==================== 读写与缓存 ====================


_config: Optional[AIChatConfig] = None
_personas: Dict[str, PersonaConfig] = {}


def get_config_dir() -> Path:
    cfg_dir = config_dir("ai_chat")
    cfg_dir.mkdir(parents=True, exist_ok=True)
    return cfg_dir


def get_config_path() -> Path:
    return get_config_dir() / "config.json"


def get_personas_dir() -> Path:
    p = get_config_dir() / "personas"
    p.mkdir(parents=True, exist_ok=True)
    return p


# ==================== 人格文件读取工具 ====================


SUPPORTED_PERSONA_EXTS = {".txt", ".md", ".docx"}


def _read_text_file(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore")


def _read_docx_text(path: Path) -> str:
    """轻量解析 .docx 文本（不依赖第三方库）。

    - 仅提取段落中的文本，保持基本换行
    - 不保留样式与图片
    """
    try:
        with zipfile.ZipFile(path) as z:
            xml_bytes = z.read("word/document.xml")
        ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
        root = ET.fromstring(xml_bytes)
        lines: List[str] = []
        for p in root.findall(".//w:p", ns):
            texts: List[str] = []
            for t in p.findall(".//w:t", ns):
                if t.text:
                    texts.append(t.text)
            if texts:
                lines.append("".join(texts))
        return "\n".join(lines).strip()
    except Exception:
        try:
            return path.read_bytes().decode("utf-8", errors="ignore")
        except Exception:
            return ""


def _parse_front_matter(text: str) -> Tuple[Dict[str, str], str]:
    """解析 Markdown/TXT 顶部的极简 Front Matter。

    语法：
    ---\n
    name: 名称\n
    description: 描述\n
    ---\n
    正文...

    仅解析 name/description 两个键，其他忽略。
    返回 (meta, body)
    """
    meta: Dict[str, str] = {}
    lines = text.splitlines()
    if not lines:
        return meta, text
    if lines[0].strip() != "---":
        return meta, text
    end_idx = None
    for i in range(1, min(len(lines), 100)):
        if lines[i].strip() == "---":
            end_idx = i
            break
    if end_idx is None:
        return meta, text
    for ln in lines[1:end_idx]:
        ln = ln.strip()
        if not ln or ln.startswith("#"):
            continue
        if ":" in ln:
            k, v = ln.split(":", 1)
            k = k.strip().lower()
            v = v.strip().strip('"').strip("'")
            if k in {"name", "description"}:
                meta[k] = v
    body = "\n".join(lines[end_idx + 1 :]).lstrip("\n")
    return meta, body


def _summarize_description(body: str, width: int = 40) -> str:
    for ln in body.splitlines():
        s = ln.strip().lstrip("#:-* ")
        if s:
            return s[:width]
    return ""


def _ensure_default_personas(dir_path: Path) -> None:
    """当 personas 目录为空时，写入示例人格文件。"""
    try:
        samples = {
            "default.md": (
                "---\n"
                "name: 默认助手\n"
                "description: 一个友好的 AI 助手\n"
                "---\n\n"
                "你是一个友好、耐心且乐于助人的 AI 助手。回答简洁清晰，有同理心。"
            ),
            "tsundere.md": (
                "---\n"
                "name: 傲娇少女\n"
                "description: 傲娇属性的人格\n"
                "---\n\n"
                "你是一个有些傲娇的人格，说话常带有‘才不是’‘哼’之类的口癖，外冷内热。"
            ),
            "professional.md": (
                "---\n"
                "name: 专业问答\n"
                "description: 专业的技术问答\n"
                "---\n\n"
                "你是一个专业的技术问答助手，擅长编程、系统架构等。回答准确、专业，提供实用建议。"
            ),
        }
        for fname, content in samples.items():
            p = dir_path / fname
            if not p.exists():
                p.write_text(content, encoding="utf-8")
    except Exception:
        pass


def load_config() -> AIChatConfig:
    global _config
    try:
        data = CFG.load() or {}
        _config = AIChatConfig(**data)
        logger.info("[AI Chat] 配置加载成功")
    except Exception as e:
        logger.error(f"[AI Chat] 配置加载失败: {e}，使用默认配置")
        _config = AIChatConfig(**DEFAULTS)
    return _config


def save_config(config: AIChatConfig) -> None:
    try:
        CFG.save(config.model_dump())
        logger.info("[AI Chat] 配置保存成功")
    except Exception as e:
        logger.error(f"[AI Chat] 配置保存失败: {e}")


def get_config() -> AIChatConfig:
    global _config
    if _config is None:
        _config = load_config()
    return _config


def get_active_api() -> APIConfig:
    cfg = get_config()
    apis: List[APIConfig] = list(getattr(cfg, "api", []) or [])
    if not apis:
        defaults = DEFAULTS["api"][0]
        return APIConfig(
            name=defaults["name"],
            base_url=defaults["base_url"],
            api_key=defaults["api_key"],
            model=defaults["model"],
            timeout=defaults["timeout"],
        )

    active_name = getattr(cfg.session, "api_active", None) or "default"
    for item in apis:
        if item.name == active_name:
            return item

    # fallback to first
    return apis[0]


def load_personas() -> Dict[str, PersonaConfig]:
    global _personas
    path = get_personas_path()

    if not path.exists():
        logger.info("[AI Chat] 人格配置文件不存在，创建默认人格")
        _personas = {
            "default": PersonaConfig(
                name="默认助手",
                description="一个友好的 AI 助手",
                system_prompt="你是一个友好、耐心且乐于助人的 AI 助手。回答简洁清晰，有同理心。",
            ),
            "tsundere": PersonaConfig(
                name="傲娇少女",
                description="傲娇属性的人格",
                system_prompt="你是一个有些傲娇的人格，说话常带有‘才不是’‘哼’之类的口癖，外冷内热。",
            ),
            "professional": PersonaConfig(
                name="专业问答",
                description="专业的技术问答",
                system_prompt="你是一个专业的技术问答助手，擅长编程、系统架构等。回答准确、专业，提供实用建议。",
            ),
        }
        save_personas(_personas)
        return _personas

    try:
        with open(path, "r", encoding="utf-8") as f:
            raw = json.load(f)
        _personas = {k: PersonaConfig(**v) for k, v in (raw or {}).items()}
        logger.info(f"[AI Chat] 人格配置加载成功，共 {_personas and len(_personas) or 0} 个")
    except Exception as e:
        logger.error(f"[AI Chat] 人格配置加载失败: {e}，使用默认人格")
        _personas = {
            "default": PersonaConfig(
                name="默认助手",
                description="一个友好的 AI 助手",
                system_prompt="你是一个友好、耐心且乐于助人的 AI 助手。回答简洁清晰，有同理心。",
            )
        }
    return _personas


def save_personas(personas: Dict[str, PersonaConfig]) -> None:
    path = get_personas_path()
    try:
        data = {k: v.model_dump() for k, v in personas.items()}
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        logger.info("[AI Chat] 人格配置保存成功")
    except Exception as e:
        logger.error(f"[AI Chat] 人格配置保存失败: {e}")


# --- Override personas I/O: switch to directory-based storage ---

def load_personas() -> Dict[str, PersonaConfig]:
    """从本地目录加载人格：config/ai_chat/personas。

    - 支持 .txt / .md / .docx
    - .txt/.md 支持顶部极简 Front Matter（name/description）
    - 未提供元信息时，name 使用文件名（不含扩展名），description 取正文首行摘要
    - 完全替代旧 personas.json（不做兼容）
    """
    global _personas
    dir_path = get_personas_dir()

    # 若目录为空，写入示例
    try:
        has_supported = any(
            f.suffix.lower() in SUPPORTED_PERSONA_EXTS for f in dir_path.iterdir() if f.is_file()
        )
    except Exception:
        has_supported = False
    if not has_supported:
        logger.info("[AI Chat] 人格目录为空，写入示例人格")
        _ensure_default_personas(dir_path)

    personas: Dict[str, PersonaConfig] = {}
    for fp in sorted(dir_path.glob("*")):
        if not fp.is_file() or fp.suffix.lower() not in SUPPORTED_PERSONA_EXTS:
            continue
        key = fp.stem
        try:
            if fp.suffix.lower() == ".docx":
                raw = _read_docx_text(fp)
            else:
                raw = _read_text_file(fp)
        except Exception as e:
            logger.error(f"[AI Chat] 读取人格文件失败 {fp.name}: {e}")
            continue

        meta, body = _parse_front_matter(raw)
        name = meta.get("name") or key
        desc = meta.get("description") or _summarize_description(body)
        system_prompt = body.strip()
        if not system_prompt:
            logger.warning(f"[AI Chat] 人格文件空内容，已跳过: {fp.name}")
            continue

        personas[key] = PersonaConfig(name=name, description=desc, system_prompt=system_prompt)

    if not personas:
        personas = {
            "default": PersonaConfig(
                name="默认助手",
                description="一个友好的 AI 助手",
                system_prompt=(
                    "你是一个友好、耐心且乐于助人的 AI 助手。回答简洁清晰，有同理心。"
                ),
            )
        }
    # 确保存在 default 键，便于下游安全回退
    if "default" not in personas:
        try:
            any_one = next(iter(personas.values()))
            personas["default"] = any_one
        except Exception:
            pass

    _personas = personas
    logger.info(f"[AI Chat] 人格加载完成，共 {len(_personas)} 个")
    return _personas


def save_personas(personas: Dict[str, PersonaConfig]) -> None:
    """将传入的人格写入 personas 目录（.md）。

    - 文件名使用键名 + .md
    - 写入带 front matter 的 Markdown
    """
    dir_path = get_personas_dir()
    try:
        for key, p in personas.items():
            fname = f"{key}.md"
            fp = dir_path / fname
            content = (
                f"---\nname: {p.name}\ndescription: {p.description}\n---\n\n{p.system_prompt}\n"
            )
            fp.write_text(content, encoding="utf-8")
        logger.info("[AI Chat] 人格已写入 personas 目录")
    except Exception as e:
        logger.error(f"[AI Chat] 写入人格目录失败: {e}")


def get_personas() -> Dict[str, PersonaConfig]:
    global _personas
    if not _personas:
        _personas = load_personas()
    return _personas


def reload_all() -> None:
    global _config, _personas
    _config = load_config()
    _personas = load_personas()
    logger.info("[AI Chat] 所有配置已重新加载")


# Register framework-level reload callback
register_reload_callback("ai_chat", reload_all)
