"""MCP（Model Context Protocol）工具桥接（可选）

- 通过启动/连接 MCP Server，动态暴露其 tools 为 OpenAI function-calling 工具
- 若运行环境未安装 mcp SDK 或配置未启用，则安全降级为 no-op

使用方式：
- 在 AI Chat 配置中（tools 字段）启用 `mcp_enabled` 并配置 `mcp_servers`
- 在 `builtin_tools` 中添加需要暴露的 MCP 工具名，格式：`mcp:<server>:<tool>`
  - 例如：`mcp:calc:calculator`、`mcp:fs:list_dir`

注意：
- 由于不同 MCP SDK 版本 API 可能存在差异，此实现尽量容错；若失败会记录日志并降级
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from nonebot.log import logger

try:
    # 参考 modelcontextprotocol/python-sdk
    from mcp.client.session import ClientSession  # type: ignore
    from mcp.client.stdio import StdioServerParameters  # type: ignore
    MCP_AVAILABLE = True
except Exception:  # pragma: no cover - 环境缺少 mcp 时静默降级
    MCP_AVAILABLE = False
    ClientSession = None  # type: ignore
    StdioServerParameters = None  # type: ignore

from .config import get_config


@dataclass
class MCPServerSpec:
    name: str
    command: str
    args: List[str] = field(default_factory=list)
    env: Dict[str, str] = field(default_factory=dict)


class MCPManager:
    def __init__(self) -> None:
        self._started = False
        self._lock = asyncio.Lock()
        # server name -> session
        self._sessions: Dict[str, Any] = {}
        # server name -> tool_name -> tool_meta
        self._server_tools: Dict[str, Dict[str, Dict[str, Any]]] = {}
        # full tool name -> openai tool schema
        self._schemas: Dict[str, Dict[str, Any]] = {}

    def _load_specs(self) -> Tuple[bool, List[MCPServerSpec]]:
        cfg = get_config()
        tools = getattr(cfg, "tools", None)
        enabled = bool(getattr(tools, "mcp_enabled", False)) if tools else False
        specs: List[MCPServerSpec] = []
        if not enabled:
            return False, specs
        try:
            raw = getattr(tools, "mcp_servers", []) or []
            for it in raw:
                try:
                    name = getattr(it, "name", None) or it.get("name")
                    cmd = getattr(it, "command", None) or it.get("command")
                    if not name or not cmd:
                        continue
                    args = list(getattr(it, "args", None) or it.get("args", []) or [])
                    env = dict(getattr(it, "env", None) or it.get("env", {}) or {})
                    specs.append(MCPServerSpec(name=name, command=cmd, args=args, env=env))
                except Exception:
                    continue
        except Exception:
            pass
        return True, specs

    async def ensure_started(self) -> None:
        if self._started:
            return
        async with self._lock:
            if self._started:
                return
            if not MCP_AVAILABLE:
                logger.warning("[AI Chat][MCP] SDK 未安装，已跳过 MCP 初始化")
                self._started = True
                return
            enabled, specs = self._load_specs()
            if not enabled or not specs:
                self._started = True
                return
            for spec in specs:
                try:
                    if spec.name in self._sessions:
                        continue
                    params = StdioServerParameters(command=spec.command, args=spec.args, env=spec.env or None)  # type: ignore
                    # 新版 SDK 支持 async 上下文管理；此处保持会话常驻
                    session = await ClientSession.connect(params)  # type: ignore[attr-defined]
                except AttributeError:
                    # 兼容旧版：可能是 `ClientSession(params)` 然后 `await session.initialize()`
                    try:
                        session = ClientSession(params)  # type: ignore[call-arg]
                        if hasattr(session, "initialize"):
                            await session.initialize()
                    except Exception as e:
                        logger.error(f"[AI Chat][MCP] 启动 {spec.name} 失败: {e}")
                        continue
                except Exception as e:
                    logger.error(f"[AI Chat][MCP] 启动 {spec.name} 失败: {e}")
                    continue

                self._sessions[spec.name] = session
                # 列出工具
                try:
                    tools = await self._list_tools(session)
                    self._server_tools[spec.name] = tools
                    # 建立 OpenAI 工具 schema 映射
                    for tname, meta in tools.items():
                        full = f"mcp:{spec.name}:{tname}"
                        schema = self._to_openai_tool_schema(full, meta)
                        if schema:
                            self._schemas[full] = schema
                    logger.info(f"[AI Chat][MCP] {spec.name} 工具数: {len(tools)}")
                except Exception as e:
                    logger.error(f"[AI Chat][MCP] 获取工具失败 {spec.name}: {e}")
                    self._server_tools[spec.name] = {}
            self._started = True

    async def _list_tools(self, session: Any) -> Dict[str, Dict[str, Any]]:
        """从会话列出工具，尽量兼容不同 SDK 版本。"""
        # 尝试常见 API：session.list_tools() 或 session.tools.list()
        try:
            # 可能返回对象列表或 dict
            out = await session.list_tools()
        except Exception:
            try:
                tools_obj = await session.tools.list()  # type: ignore[attr-defined]
                out = getattr(tools_obj, "tools", tools_obj)
            except Exception:
                out = []
        tools: Dict[str, Dict[str, Any]] = {}
        try:
            for item in out or []:
                # 兼容不同结构
                name = getattr(item, "name", None) or item.get("name")
                desc = getattr(item, "description", None) or item.get("description") or ""
                params = (
                    getattr(item, "inputSchema", None)
                    or getattr(item, "schema", None)
                    or item.get("inputSchema")
                    or item.get("schema")
                    or {"type": "object", "properties": {}}
                )
                if name:
                    tools[name] = {"name": name, "description": desc, "parameters": params}
        except Exception:
            pass
        return tools

    def _to_openai_tool_schema(self, full_name: str, meta: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        try:
            return {
                "type": "function",
                "function": {
                    "name": full_name,
                    "description": str(meta.get("description", ""))[:512],
                    "parameters": meta.get("parameters") or {"type": "object", "properties": {}},
                },
            }
        except Exception:
            return None

    def list_tool_names(self) -> List[str]:
        return sorted(self._schemas.keys())

    def get_tool_schemas_for_names(self, desired_names: List[str]) -> List[Dict[str, Any]]:
        """根据所需工具名返回 OpenAI Schema。

        - 若包含模式 `mcp:*` 则返回所有 MCP 工具
        - 否则仅返回显式列出的 `mcp:<server>:<tool>`
        """
        if not self._schemas:
            return []
        want_all = any(n.strip().lower() in {"mcp:*", "mcp:all", "mcp"} for n in desired_names)
        out: List[Dict[str, Any]] = []
        if want_all:
            return list(self._schemas.values())
        s: List[str] = [n for n in desired_names if n.startswith("mcp:")]
        for n in s:
            sch = self._schemas.get(n)
            if sch:
                out.append(sch)
        return out

    async def execute_tool(self, full_name: str, args: Dict[str, Any]) -> str:
        """执行 MCP 工具：`mcp:<server>:<tool>`"""
        try:
            if not full_name.startswith("mcp:"):
                return "错误：非 MCP 工具名"
            parts = full_name.split(":", 2)
            if len(parts) != 3:
                return "错误：MCP 工具名格式应为 mcp:<server>:<tool>"
            server, tool = parts[1], parts[2]
            session = self._sessions.get(server)
            if not session:
                return f"错误：MCP 服务器未连接：{server}"

            # 调用工具（尽量兼容不同 SDK 版本）
            try:
                # 新版：session.call_tool(name, arguments)
                result = await session.call_tool(tool, args)  # type: ignore[attr-defined]
                content = getattr(result, "content", None)
                if isinstance(content, list):
                    # 合并文本内容
                    texts = []
                    for c in content:
                        t = getattr(c, "text", None) or c.get("text") if isinstance(c, dict) else None
                        if t:
                            texts.append(str(t))
                    if texts:
                        return "\n".join(texts)
                # 兜底：直接转字符串
                return str(getattr(result, "result", result))
            except Exception:
                # 旧版：session.tools.call(name, args)
                try:
                    result = await session.tools.call(tool, args)  # type: ignore[attr-defined]
                    return str(result)
                except Exception as e:
                    logger.error(f"[AI Chat][MCP] 工具调用失败 {full_name}: {e}")
                    return f"MCP 工具调用失败: {str(e)}"
        except Exception as e:
            logger.error(f"[AI Chat][MCP] 工具调用异常 {full_name}: {e}")
            return f"MCP 工具调用异常: {str(e)}"


# 全局实例
mcp_manager = MCPManager()

