"""AI 对话配置与人格文件管理

- 统一落盘目录：config/ai_chat/
- 人格改为“目录化”管理：config/ai_chat/personas 下的 .md/.txt/.docx 文件
- 始终从磁盘读取人格，避免缓存导致的“重复/删不掉/404”等问题
"""
from __future__ import annotations

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


# ==================== Pydantic 配置模型 ====================


class APIItem(BaseModel):
    base_url: str = Field(default="https://api.openai.com/v1", description="API 地址")
    api_key: str = Field(default="", description="API Key")
    model: str = Field(default="gpt-4o-mini", description="默认模型")
    timeout: int = Field(default=60, description="超时（秒）")


class SessionConfig(BaseModel):
    api_active: str = Field(default="default", description="当前服务商（名称）")
    default_temperature: float = Field(default=0.7, description="默认温度")
    max_rounds: int = Field(default=8, description="最大轮数（user+assistant 计一轮）")
    chatroom_history_max_lines: int = Field(default=200, description="聊天室历史行数上限（内存）")
    active_reply_enable: bool = Field(default=False, description="是否开启主动回复（群聊）")
    active_reply_probability: float = Field(default=0.1, description="主动回复概率 0~1")
    active_reply_prompt_suffix: str = Field(
        default=(
            "请根据以下消息进行自然回复：`{message}`，并保持简洁清晰。"
            "只需回复结果，不要解释过程。"
        ),
        description="主动回复附加提示，支持 {message}/{prompt} 占位符",
    )


class ToolsConfig(BaseModel):
    enabled: bool = Field(default=False, description="是否启用工具调用")
    max_iterations: int = Field(default=3, description="最多工具往返次数")
    builtin_tools: list[str] = Field(default_factory=lambda: ["get_time", "get_weather"], description="内置工具")


class AIChatConfig(BaseModel):
    # api 使用字典：{ name: { base_url, api_key, model, timeout } }
    api: Dict[str, APIItem] = Field(default_factory=dict)
    session: SessionConfig = Field(default_factory=SessionConfig)
    tools: ToolsConfig = Field(default_factory=ToolsConfig)


class PersonaConfig(BaseModel):
    name: str = Field(description="显示名")
    details: str = Field(description="系统提示词（System Prompt）")


# ==================== 默认值与 Schema ====================


DEFAULTS: Dict[str, Any] = {
    "api": {
        "default": {
            "base_url": "https://api.openai.com/v1",
            "api_key": "",
            "model": "gpt-4o-mini",
            "timeout": 60,
        }
    },
    "session": {
        "api_active": "default",
        "default_temperature": 0.7,
        "max_rounds": 8,
        "chatroom_history_max_lines": 200,
        "active_reply_enable": False,
        "active_reply_prompt_suffix": (
            "请根据以下消息进行自然回复：`{message}`，并保持简洁清晰。"
            "只需回复结果，不要解释过程。"
        ),
        "active_reply_probability": 0.1,
    },
    "tools": {
        "enabled": False,
        "max_iterations": 3,
        "builtin_tools": ["get_time", "get_weather"],
    },
}


CFG = register_plugin_config("ai_chat", DEFAULTS)


AI_CHAT_SCHEMA: Dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "title": "AI 对话",
    "properties": {
        "api": {
            "type": "object",
            "title": "服务商（字典，键为名称）",
            "description": "键为服务商名称，值为该服务商配置。",
            "x-order": 1,
            "additionalProperties": {
                "type": "object",
                "properties": {
                    "base_url": {"type": "string", "title": "API 地址", "x-order": 1},
                    "api_key": {"type": "string", "title": "API Key", "x-order": 2},
                    "model": {"type": "string", "title": "模型", "x-order": 3},
                    "timeout": {"type": "integer", "title": "超时（秒）", "x-order": 4},
                },
            },
        },
        "session": {
            "type": "object",
            "title": "会话",
            "x-order": 4,
            "x-collapse": True,
            "properties": {
                "api_active": {"type": "string", "title": "当前服务商", "x-order": 1},
                "default_temperature": {"type": "number", "title": "默认温度", "minimum": 0, "maximum": 2, "x-order": 2},
                "max_rounds": {"type": "integer", "title": "最大轮数", "minimum": 1, "maximum": 50, "x-order": 3},
                "chatroom_history_max_lines": {"type": "integer", "title": "聊天室历史行数", "minimum": 1, "maximum": 5000, "x-order": 4},
                "active_reply_enable": {"type": "boolean", "title": "开启主动回复（群聊）", "x-order": 5},
                "active_reply_probability": {"type": "number", "title": "主动回复概率（0~1）", "minimum": 0, "maximum": 1, "x-order": 6},
                "active_reply_prompt_suffix": {"type": "string", "title": "主动回复提示后缀", "x-order": 7},
            },
        },
        "tools": {
            "type": "object",
            "title": "工具",
            "x-order": 6,
            "x-collapse": True,
            "properties": {
                "enabled": {"type": "boolean", "title": "启用工具", "x-order": 1},
                "max_iterations": {"type": "integer", "title": "最多工具往返次数", "minimum": 1, "maximum": 10, "x-order": 2},
                "builtin_tools": {"type": "array", "title": "内置工具", "items": {"type": "string"}, "x-order": 3},
            },
        },
    },
}

register_plugin_schema("ai_chat", AI_CHAT_SCHEMA)


# ==================== 缓存与路径 ====================


_config: Optional[AIChatConfig] = None
_personas: Dict[str, PersonaConfig] = {}


def get_config_dir() -> Path:
    d = config_dir("ai_chat")
    d.mkdir(parents=True, exist_ok=True)
    return d


def get_config_path() -> Path:
    return get_config_dir() / "config.json"


def get_personas_dir() -> Path:
    p = get_config_dir() / "personas"
    p.mkdir(parents=True, exist_ok=True)
    return p


# ==================== 人格文件读取 ====================


SUPPORTED_PERSONA_EXTS = {".txt", ".md", ".docx"}


def _read_text_file(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore")


def _read_docx_text(path: Path) -> str:
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
    """解析简易 Front Matter（仅 name/description）"""
    meta: Dict[str, str] = {}
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return meta, text
    end_idx = None
    for i in range(1, min(len(lines), 100)):
        if lines[i].strip() == "---":
            end_idx = i
            break
    if end_idx is None:
        return meta, text
    for ln in lines[1:end_idx]:
        s = ln.strip()
        if not s or s.startswith("#"):
            continue
        if ":" in s:
            k, v = s.split(":", 1)
            k = k.strip().lower()
            v = v.strip().strip('"').strip("'")
            if k in {"name", "description"}:
                meta[k] = v
    body = "\n".join(lines[end_idx + 1 :]).lstrip("\n")
    return meta, body


def _ensure_default_personas(dir_path: Path) -> None:
    try:
        samples: Dict[str, str] = {
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
                "description: 专业的知识问答\n"
                "---\n\n"
                "你是一个专业的知识问答助手，擅长编程、系统架构等，回答准确专业且提供可操作建议。"
            ),
        }
        for fname, content in samples.items():
            p = dir_path / fname
            if not p.exists():
                p.write_text(content, encoding="utf-8")
    except Exception:
        pass


# ==================== 配置读写 ====================


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


def get_active_api() -> APIItem:
    cfg = get_config()
    apis: Dict[str, APIItem] = dict(getattr(cfg, "api", {}) or {})
    if not apis:
        d = (DEFAULTS.get("api") or {}).get("default") or {}
        return APIItem(**d)
    active_name = getattr(cfg.session, "api_active", None) or "default"
    if active_name in apis:
        return apis[active_name]
    # fallback: 取第一个
    first_key = next(iter(apis.keys()))
    return apis[first_key]


# ==================== 人格：目录化实现 ====================


def load_personas() -> Dict[str, PersonaConfig]:
    """扫描 config/ai_chat/personas 目录，返回 {key: PersonaConfig}。

    - 支持 .md/.txt/.docx，优先选择 .md（若同名多扩展）
    - 读取 Front Matter 的 name/description；未提供 name 时用文件名；details 为正文
    - 目录空时自动写入示例人格
    """
    global _personas
    dir_path = get_personas_dir()

    try:
        has_supported = any(f.is_file() and f.suffix.lower() in SUPPORTED_PERSONA_EXTS for f in dir_path.iterdir())
    except Exception:
        has_supported = False
    if not has_supported:
        logger.info("[AI Chat] 人格目录为空，写入示例人格")
        _ensure_default_personas(dir_path)

    # 排序以保证优先级：.md < .txt < .docx
    rank = {".md": 0, ".txt": 1, ".docx": 2}
    files = [f for f in dir_path.glob("*") if f.is_file() and f.suffix.lower() in SUPPORTED_PERSONA_EXTS]
    files.sort(key=lambda p: (p.stem, rank.get(p.suffix.lower(), 9), p.name))

    personas: Dict[str, PersonaConfig] = {}
    for fp in files:
        key = fp.stem
        if key in personas:
            # 已有同名（更高优先级扩展已放入），跳过
            continue
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
        details = body.strip()
        if not details:
            logger.warning(f"[AI Chat] 人格文件内容为空，已跳过: {fp.name}")
            continue
        personas[key] = PersonaConfig(name=name, details=details)

    if not personas:
        personas = {
            "default": PersonaConfig(
                name="默认助手",
                details=(
                    "你是一个友好、耐心且乐于助人的 AI 助手。回答简洁清晰，有同理心。"
                ),
            )
        }

    _personas = personas
    logger.info(f"[AI Chat] 人格加载完成，共 {len(_personas)} 个")
    return _personas


def save_personas(personas: Dict[str, PersonaConfig]) -> None:
    """将 personas 写入 personas 目录（.md，带 front matter）"""
    dir_path = get_personas_dir()
    try:
        for key, p in personas.items():
            fp = dir_path / f"{key}.md"
            content = f"---\nname: {p.name}\n---\n\n{p.details}\n"
            fp.write_text(content, encoding="utf-8")
        logger.info("[AI Chat] 人格已写入 personas 目录")
    except Exception as e:
        logger.error(f"[AI Chat] 写入人格目录失败: {e}")


def get_personas() -> Dict[str, PersonaConfig]:
    """总是重载，确保与文件一致。"""
    return load_personas()


def reload_all() -> None:
    global _config, _personas
    _config = load_config()
    _personas = load_personas()
    logger.info("[AI Chat] 配置与人格已重载")


register_reload_callback("ai_chat", reload_all)
