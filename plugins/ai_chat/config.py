"""AI 对话配置与人格文件管理（UTF-8）

- 统一落盘目录：config/ai_chat/
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional, List
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
    default_provider: str = Field(default="", description="默认服务商（名称）")
    default_temperature: float = Field(default=0.7, description="默认温度")
    max_rounds: int = Field(default=8, description="最大轮数（user+assistant 计一轮）")
    chatroom_history_max_lines: int = Field(default=200, description="聊天室历史行数上限（内存）")
    active_reply_enable: bool = Field(default=False, description="是否开启主动回复（群聊）")
    active_reply_probability: float = Field(default=0.1, description="主动回复概率 0~1")
    ignore_prefixes: List[str] = Field(default_factory=list, description="消息以这些前缀之一开头时不触发AI回复（忽略前导空白）")
    active_reply_prompt_suffix: str = Field(
        default=(
            "请根据以下消息进行自然回复：`{message}`，并保持简洁清晰。\n"
            "只需回复结果，不要解释过程。\n"
        ),
        description="主动回复附加提示，支持 {message}/{prompt} 占位",
    )


class MCPServerItem(BaseModel):
    name: str = Field(description="MCP 服务器名")
    command: str = Field(description="启动命令")
    args: list[str] = Field(default_factory=list, description="命令参数")
    env: Dict[str, str] = Field(default_factory=dict, description="环境变量")


class ToolsConfig(BaseModel):
    enabled: bool = Field(default=False, description="是否启用工具调用")
    max_iterations: int = Field(default=3, description="最多工具往返次数")
    builtin_tools: list[str] = Field(default_factory=lambda: ["get_time", "get_weather"], description="内置工具")
    # MCP（可选）
    mcp_enabled: bool = Field(default=False, description="启用 MCP 动态工具")
    mcp_servers: list[MCPServerItem] = Field(default_factory=list, description="MCP 服务器配置列表")


class OutputConfig(BaseModel):
    tts_enable: bool = Field(default=False, description="是否开启 TTS 语音回复")
    # 统一 TTS 提供方：openai | http | command
    tts_provider: str = Field(default="openai", description="TTS 提供方：openai/http/command")
    # OpenAI TTS 相关
    tts_model: str = Field(default="gpt-4o-mini-tts", description="TTS 模型（OpenAI）")
    tts_voice: str = Field(default="alloy", description="TTS 发音（OpenAI）")
    tts_format: str = Field(default="mp3", description="TTS 音频格式：mp3/wav 等")
    # HTTP 本地/自建 TTS（返回音频字节或 JSON(base64)）
    tts_http_url: str = Field(default="", description="HTTP TTS 接口 URL")
    tts_http_method: str = Field(default="POST", description="HTTP 方法：POST/GET")
    tts_http_response_type: str = Field(default="bytes", description="响应类型：bytes/base64")
    tts_http_base64_field: str = Field(default="audio", description="当响应 JSON+base64 时的字段名")
    # 命令行 TTS：在本地执行命令把音频写入指定输出路径；占位符：{text}/{voice}/{format}/{out}
    tts_command: str = Field(default="", description="命令行 TTS 模板（需包含 {out} 输出路径占位符）")


class InputConfig(BaseModel):
    image_max_side: int = Field(default=1280, description="输入图片最长边像素上限（>0 开启压缩）")
    image_jpeg_quality: int = Field(default=85, description="输入图片 JPEG 质量（1-95）")


class MemoryConfig(BaseModel):
    enable_summarize: bool = Field(default=False, description="开启长期记忆摘要")
    summarize_min_rounds: int = Field(default=12, description="达到多少轮后开始摘要")
    summarize_interval_rounds: int = Field(default=8, description="每隔多少轮更新一次摘要")


class AIChatConfig(BaseModel):
    # api 使用字典：{ name: { base_url, api_key, model, timeout } }
    api: Dict[str, APIItem] = Field(default_factory=dict)
    session: SessionConfig = Field(default_factory=SessionConfig)
    tools: ToolsConfig = Field(default_factory=ToolsConfig)
    output: OutputConfig = Field(default_factory=OutputConfig)
    input: InputConfig = Field(default_factory=InputConfig)
    memory: MemoryConfig = Field(default_factory=MemoryConfig)


class PersonaConfig(BaseModel):
    name: str = Field(description="显示名")
    details: str = Field(description="系统提示词（System Prompt）")


# ==================== 默认值与 Schema ====================


DEFAULTS: Dict[str, Any] = {
    "api": {},
    "session": {
        "default_provider": "",
        "default_temperature": 0.7,
        "max_rounds": 8,
        "chatroom_history_max_lines": 200,
        "active_reply_enable": False,
        "active_reply_prompt_suffix": (
            "请根据以下消息进行自然回复：`{message}`，并保持简洁清晰。\n"
            "只需回复结果，不要解释过程。\n"
        ),
        "active_reply_probability": 0.1,
        "ignore_prefixes": [],
    },
    "tools": {
        "enabled": False,
        "max_iterations": 3,
        "builtin_tools": ["get_time", "get_weather"],
        "mcp_enabled": False,
        "mcp_servers": [],
    },
    "output": {
        "tts_enable": False,
        "tts_provider": "openai",
        "tts_model": "gpt-4o-mini-tts",
        "tts_voice": "alloy",
        "tts_format": "mp3",
        "tts_http_url": "",
        "tts_http_method": "POST",
        "tts_http_response_type": "bytes",
        "tts_http_base64_field": "audio",
        "tts_command": "",
    },
    "input": {
        "image_max_side": 1280,
        "image_jpeg_quality": 85,
    },
    "memory": {
        "enable_summarize": False,
        "summarize_min_rounds": 12,
        "summarize_interval_rounds": 8,
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
            "description": "键为服务商名称，值为该服务商配置",
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
                "default_provider": {"type": "string", "title": "默认服务商", "x-order": 1},
                "default_temperature": {"type": "number", "title": "默认温度", "minimum": 0, "maximum": 2, "x-order": 2},
                "max_rounds": {"type": "integer", "title": "最大轮数", "minimum": 1, "maximum": 50, "x-order": 3},
                "chatroom_history_max_lines": {"type": "integer", "title": "聊天室历史行数", "minimum": 1, "maximum": 5000, "x-order": 4},
                "active_reply_enable": {"type": "boolean", "title": "开启主动回复（群聊）", "x-order": 5},
                "active_reply_probability": {"type": "number", "title": "主动回复概率（0~1）", "minimum": 0, "maximum": 1, "x-order": 6},
                "active_reply_prompt_suffix": {"type": "string", "title": "主动回复提示后缀", "x-order": 7},
                "ignore_prefixes": {"type": "array", "title": "不回复前缀（全局）", "description": "消息以这些前缀之一开头时不触发AI；忽略前导空白。", "items": {"type": "string"}, "x-order": 8},
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
                "mcp_enabled": {"type": "boolean", "title": "启用 MCP 动态工具", "x-order": 4},
                "mcp_servers": {
                    "type": "array",
                    "title": "MCP 服务器",
                    "x-order": 5,
                    "items": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string", "title": "名称", "x-order": 1},
                            "command": {"type": "string", "title": "命令", "x-order": 2},
                            "args": {"type": "array", "items": {"type": "string"}, "title": "参数", "x-order": 3},
                            "env": {"type": "object", "additionalProperties": {"type": "string"}, "title": "环境变量", "x-order": 4},
                        },
                    },
                },
            },
        },
        "output": {
            "type": "object",
            "title": "输出",
            "x-order": 7,
            "x-collapse": True,
            "properties": {
                "tts_enable": {"type": "boolean", "title": "启用 TTS 语音回复", "x-order": 1},
                "tts_provider": {"type": "string", "title": "TTS 提供方（openai/http/command）", "x-order": 2},
                "tts_model": {"type": "string", "title": "TTS 模型（OpenAI）", "x-order": 3},
                "tts_voice": {"type": "string", "title": "TTS 发音（OpenAI）", "x-order": 4},
                "tts_format": {"type": "string", "title": "TTS 音频格式", "x-order": 5},
                "tts_http_url": {"type": "string", "title": "HTTP TTS 地址", "x-order": 6},
                "tts_http_method": {"type": "string", "title": "HTTP 方法", "x-order": 7},
                "tts_http_response_type": {"type": "string", "title": "HTTP 响应类型（bytes/base64）", "x-order": 9},
                "tts_http_base64_field": {"type": "string", "title": "base64 字段名（JSON 响应）", "x-order": 10},
                "tts_command": {"type": "string", "title": "命令行模板（含 {out}）", "x-order": 11},
            },
        },
        "input": {
            "type": "object",
            "title": "输入",
            "x-order": 8,
            "x-collapse": True,
            "properties": {
                "image_max_side": {"type": "integer", "title": "图片最长边像素上限", "minimum": 0, "maximum": 4096, "x-order": 1},
                "image_jpeg_quality": {"type": "integer", "title": "图片 JPEG 质量", "minimum": 1, "maximum": 95, "x-order": 2},
            },
        },
        "memory": {
            "type": "object",
            "title": "长期记忆",
            "x-order": 9,
            "x-collapse": True,
            "properties": {
                "enable_summarize": {"type": "boolean", "title": "开启摘要", "x-order": 1},
                "summarize_min_rounds": {"type": "integer", "title": "开始摘要的轮数阈值", "minimum": 2, "maximum": 100, "x-order": 2},
                "summarize_interval_rounds": {"type": "integer", "title": "摘要间隔轮数", "minimum": 2, "maximum": 100, "x-order": 3},
            },
        },
    },
}

try:
    _api_props = AI_CHAT_SCHEMA["properties"]["api"]["additionalProperties"]["properties"]
    _api_props.setdefault(
        "support_tools",
        {"type": "boolean", "title": "支持工具调用", "default": True, "x-order": 5},
    )
    _api_props.setdefault(
        "support_vision",
        {"type": "boolean", "title": "支持识别图片", "default": True, "x-order": 6},
    )
except Exception:
    # Schema 扩展失败不影响功能
    pass

register_plugin_schema("ai_chat", AI_CHAT_SCHEMA)


# ==================== 缓存与路径 ====================


_config: Optional[AIChatConfig] = None
_personas: Dict[str, "PersonaConfig"] = {}


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


"""
# ==================== 人格（基于文件名） ====================
"""

SUPPORTED_PERSONA_EXTS = {".md", ".txt"}


def _ensure_default(dir_path: Path) -> None:
    """确保存在一个叫 default 的文件（优先 default.md）。"""
    try:
        p = dir_path / "default.md"
        if not p.exists():
            content = (
                "你是一个友好、耐心且乐于助人的 AI 助手。"
                "请保持回答简洁清晰，并具备同理心。"
            )
            p.write_text(content, encoding="utf-8")
    except Exception:
        pass


def _ensure_default_persona_only(dir_path: Path) -> None:
    """当目录为空时，仅创建 default.md 示例文件。"""
    _ensure_default(dir_path)


def _collect_persona_files(dir_path: Path) -> Dict[str, Path]:
    """收集人格文件，返回 {stem: Path}，按扩展优先级（.md > .txt）。"""
    rank = {".md": 0, ".txt": 1}
    result: Dict[str, Path] = {}
    try:
        files = [
            f for f in dir_path.glob("*") if f.is_file() and f.suffix.lower() in SUPPORTED_PERSONA_EXTS
        ]
        files.sort(key=lambda p: (p.stem.lower(), rank.get(p.suffix.lower(), 9)))
        for fp in files:
            stem = fp.stem
            if stem not in result:
                result[stem] = fp
            else:
                logger.warning(f"[AI Chat] 人格文件名重复（仅保留优先者）: {fp.name}")
    except Exception as e:
        logger.error(f"[AI Chat] 扫描人格目录失败: {e}")
    return result


def list_personas() -> List[str]:
    """列出所有人格名（文件名，不含扩展名）。"""
    dir_path = get_personas_dir()
    _ensure_default(dir_path)
    files = _collect_persona_files(dir_path)
    names = sorted(files.keys())
    if "default" not in names:
        names = ["default", *names]
    return names


def get_persona_text(name: str) -> str:
    """读取指定人格（文件名）的内容，找不到时返回空字符串（回退 default）。"""
    dir_path = get_personas_dir()
    _ensure_default(dir_path)
    files = _collect_persona_files(dir_path)
    path = files.get(name)
    try:
        if path and path.exists():
            return path.read_text(encoding="utf-8", errors="ignore").strip()
    except Exception as e:
        logger.error(f"[AI Chat] 读取人格失败 {name}: {e}")
    if name != "default":
        try:
            p = dir_path / "default.md"
            if p.exists():
                return p.read_text(encoding="utf-8", errors="ignore").strip()
        except Exception:
            pass
    return ""


def save_persona_text(name: str, text: str) -> Path:
    """保存/覆盖指定人格（文件名）的内容，写入 .md 文件，返回路径。"""
    dir_path = get_personas_dir()
    _ensure_default(dir_path)
    if not name or any(ch in name for ch in "/\\:*?\"<>|") or name.strip() != name:
        raise ValueError("非法的人格名（文件名）")
    path = dir_path / f"{name}.md"
    path.write_text(text or "", encoding="utf-8")
    return path


# 禁用重命名：仅允许修改内容


# ==================== 配置读写 ====================


def load_config() -> AIChatConfig:
    global _config
    try:
        data = CFG.load() or {}
        # migrate: ignore_prefix (str) -> ignore_prefixes (list[str])
        try:
            sess = data.setdefault("session", {})
            if "ignore_prefixes" not in sess:
                old = sess.get("ignore_prefix")
                if isinstance(old, list):
                    sess["ignore_prefixes"] = [str(x) for x in old if isinstance(x, (str, int)) and str(x)]
                elif isinstance(old, str) and old:
                    sess["ignore_prefixes"] = [old]
                else:
                    sess["ignore_prefixes"] = []
        except Exception:
            pass
        _config = AIChatConfig(**data)
        # 规范化：若存在服务商但未设置/设置了无效的 default_provider，则设置为第一个键
        try:
            apis = _config.api or {}
            if apis:
                names = list(apis.keys())
                active = (_config.session.default_provider or "").strip()
                if not active or active not in apis:
                    _config.session.default_provider = names[0]
                    CFG.save(_config.model_dump())
        except Exception:
            pass
        logger.info("[AI Chat] 配置加载成功")
    except Exception as e:
        logger.error(f"[AI Chat] 配置加载失败: {e}，使用默认配置")
        _config = AIChatConfig(**DEFAULTS)
    return _config


def save_config(config: AIChatConfig) -> None:
    try:
        # Preserve unknown provider fields (e.g., capability flags) on save
        try:
            existing = CFG.load() or {}
        except Exception:
            existing = {}
        new_data = config.model_dump()
        try:
            raw_apis = dict((existing or {}).get("api") or {})
            new_apis = dict((new_data or {}).get("api") or {})
            for name, raw in raw_apis.items():
                if name in new_apis and isinstance(raw, dict) and isinstance(new_apis[name], dict):
                    # Known capability flags to preserve even if schema doesn't include them
                    for k in ("support_tools", "support_vision"):
                        if k in raw and k not in new_apis[name]:
                            new_apis[name][k] = raw[k]
            new_data["api"] = new_apis
        except Exception:
            pass
        CFG.save(new_data)
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
        return APIItem()
    active_name = getattr(cfg.session, "default_provider", None) or ""
    if active_name in apis:
        return apis[active_name]
    first_key = next(iter(apis.keys()))
    return apis[first_key]


def get_api_by_name(name: Optional[str]) -> APIItem:
    """按名称获取服务商配置；名称为空或不存在时返回第一个可用服务商。"""
    cfg = get_config()
    apis: Dict[str, APIItem] = dict(getattr(cfg, "api", {}) or {})
    if not apis:
        return APIItem()
    key = (name or "").strip()
    if key and key in apis:
        return apis[key]
    first_key = next(iter(apis.keys()))
    return apis[first_key]


# ==================== 人格：目录化实现 ====================

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

def load_personas() -> Dict[str, PersonaConfig]:
    """扫描 config/ai_chat/personas 目录，返回 {key: PersonaConfig}

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
        _ensure_default_persona_only(dir_path)

    rank = {".md": 0, ".txt": 1, ".docx": 2}
    files = [f for f in dir_path.glob("*") if f.is_file() and f.suffix.lower() in SUPPORTED_PERSONA_EXTS]
    files.sort(key=lambda p: (p.stem, rank.get(p.suffix.lower(), 9), p.name))

    personas: Dict[str, PersonaConfig] = {}
    for fp in files:
        key = fp.stem
        if key in personas:
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
        name = key
        details = body.strip()
        if not details:
            logger.warning(f"[AI Chat] 人格文件内容为空，已跳过: {fp.name}")
            continue
        personas[key] = PersonaConfig(name=name, details=details)

    # Ensure 'default' persona exists; create and load if missing
    if "default" not in personas:
        try:
            default_fp = dir_path / "default.md"
            if not default_fp.exists():
                _ensure_default_persona_only(dir_path)
            if default_fp.exists():
                raw = _read_text_file(default_fp)
                meta, body = _parse_front_matter(raw)
                name = "default"
                details = (body or "").strip()
                if details:
                    personas["default"] = PersonaConfig(name=name, details=details)
        except Exception:
            pass

    if not personas:
        personas = {
            "default": PersonaConfig(
                name="default",
                details=("你是一个友好、耐心且乐于助人的 AI 助手。请保持回答简洁清晰，并具备同理心。"),
            )
        }

    _personas = personas
    logger.info(f"[AI Chat] 人格加载完成，共 {len(_personas)} 个")
    return _personas


def save_personas(personas: Dict[str, PersonaConfig]) -> None:
    """将 personas 写入 personas 目录为 .md，带 front matter"""
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
    """基于文件名的人格映射：{文件名: PersonaConfig(name=文件名, details=文件内容)}"""
    dir_path = get_personas_dir()
    _ensure_default(dir_path)
    files = _collect_persona_files(dir_path)
    personas: Dict[str, PersonaConfig] = {}
    for name, path in files.items():
        try:
            content = path.read_text(encoding="utf-8", errors="ignore").strip()
        except Exception:
            content = ""
        if content:
            personas[name] = PersonaConfig(name=name, details=content)
    if "default" not in personas:
        personas["default"] = PersonaConfig(name="default", details=get_persona_text("default") or "")
    return personas



def get_personas() -> Dict[str, PersonaConfig]:
    """返回缓存的人格映射；为空时触发一次加载（key=文件名，details=文件内容）。"""
    global _personas
    if not _personas:
        _personas = load_personas()
    return _personas
def reload_all() -> None:
    global _config
    _config = load_config()
    try:
        load_personas()
    except Exception:
        pass
    logger.info("[AI Chat] 配置已重载")


register_reload_callback("ai_chat", reload_all)
