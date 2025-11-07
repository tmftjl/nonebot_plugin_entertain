AI 对话插件 ai_chat

简介
- 基于 NoneBot2 的通用 AI 对话插件，支持多模态输入（文本/图片）、工具调用（Function Calling）与可选 MCP、会话与人格系统、TTS 语音回复、摘要记忆等能力。

特性概览
- 多模态输入：自动将文本与图片封装为 Chat Completions 的 content parts。
- 图片解析：识别群/私聊图片、URL、Markdown 图片、data:image URI，并按需压缩（最长边/质量）。
- 工具调用：
  - 装饰器注册自定义工具（OpenAI Function Calling JSON Schema）。
  - 可选接入 MCP（Model Context Protocol），以 mcp:<server>:<tool> 形式使用外部工具。
  - 支持多轮工具迭代，直到模型不再请求工具或达到上限。
- 会话系统：按会话（群/私）持久化历史与状态，支持清空/暂停/切换人格/服务商。
- 摘要记忆：可选按轮数阈值与间隔自动生成对话摘要并注入 System Prompt。
- TTS 输出：统一接口支持 openai/http/command 三种模式，自动将文本转换为音频文件。
- 短期群聊记忆：以“用户名/时间: 内容”记录近 N 行群聊上下文，提升主动回复质量。

安装与启用
- 依赖安装（UTF-8 环境）：
  - 使用项目根目录的 `requirements.txt` 安装：
    pip install -r requirements.txt
  - 关键依赖：openai>=1.0, pydantic>=2, sqlalchemy>=2, sqlmodel, Pillow, httpx, aiosqlite。
- 启用插件：确保在 NoneBot 加载 `nonebot_plugin_entertain` 后，自动加载本插件（ai_chat 的 `__init__.py` 中已 `require("nonebot_plugin_entertain")`）。
- 配置文件与目录：
  - 主配置：`config/ai_chat/config.json`
  - 人格目录：`config/ai_chat/personas/`（支持 .md/.txt/.docx，优先 .md）
  - TTS 音频输出：`data/ai_chat/tts/`
  - 可用环境变量覆盖配置目录：`NPE_CONFIG_DIR=/your/config/dir`

快速开始
1) 创建最小可用配置 `config/ai_chat/config.json`：
```
{
  "api": {
    "openai": {
      "base_url": "https://api.openai.com/v1",
      "api_key": "sk-xxxxxxxxxxxxxxxx",
      "model": "gpt-4o-mini",
      "timeout": 60
    }
  },
  "session": {
    "api_active": "openai",
    "default_temperature": 0.7,
    "max_rounds": 8,
    "chatroom_history_max_lines": 200,
    "active_reply_enable": false,
    "active_reply_probability": 0.1,
    "active_reply_prompt_suffix": "请基于最近消息自然地回复：{message}\n只输出必要内容。"
  }
}
```
2) 常见 `base_url` 示例（按服务商自行替换）：
- OpenAI: `https://api.openai.com/v1`
- 第三方代理/聚合（示例）：`https://one-api.your-domain/v1`、`https://api.deepseek.com/v1`、`https://open.bigmodel.cn/api/paas/v4` 等。请以供应商文档为准。
3) 运行后在群聊 @机器人 发消息，或私聊直接发消息测试。

命令速查
- 对话
  - 群聊需 @机器人 或命中主动回复；私聊直接发送文本/图片即可。
- 会话管理
  - `#清空会话` 清空当前会话历史
  - `#会话信息` 查看当前会话状态
  - `#开启AI` / `#关闭AI`（管理员）切换会话启用状态
- 人格
  - `#人格列表`（管理员）查看可用人格
  - `#切换人格 <key>`（管理员）切换当前会话人格
- 服务商
  - `#服务商列表`（超管）查看配置中的服务商
  - `#切换服务商 <name>`（超管）切换 `session.api_active`
- 工具与 TTS
  - `#工具列表`（超管）查看工具（含 MCP 动态工具）
  - `#开启工具 <name>` / `#关闭工具 <name>`（超管）
  - `#开启TTS` / `#关闭TTS`（超管）
- 系统
  - `#重载AI配置`（超管）重新加载配置与人格

图片输入说明
- 支持来源：
  - QQ 图片消息（自动下载/压缩后转 data:image;base64）
  - 直接粘贴 URL（http/https）或 data:image;base64
  - 文本中的 Markdown 图片：`![alt](https://...)`
- 压缩与质量：
  - `input.image_max_side` 最长边像素（>0 时按比例缩放并转 JPEG）
  - `input.image_jpeg_quality` JPEG 质量（1-95），默认 85

人格文件（personas）
- 位置：`config/ai_chat/personas/`，支持 `.md/.txt/.docx`，优先 `.md`。
- `.md` 支持可选 Front Matter：
```
---
name: 落落大方
description: 友善、耐心、表达清晰
---

你是一位友善且表达清晰的 AI 助手，回答简洁、条理分明。
```
- 初次运行目录为空时仅写入示例人格：`default.md`。
- 切换人格：`#切换人格 default`（管理员）。

工具调用（Function Calling + MCP）
- 内置工具（可在配置 `tools.builtin_tools` 中启用）：
  - `get_time` 当前时间
  - `get_weather` 简单示例（可接入真实 API）
- 自定义工具注册示例（`plugins/ai_chat/tools.py` 相同风格）：
```
from plugins.ai_chat.tools import register_tool

@register_tool(
    name="echo",
    description="回显传入文本",
    parameters={
        "type": "object",
        "properties": {"text": {"type": "string"}},
        "required": ["text"]
    }
)
async def tool_echo(text: str) -> str:
    return text
```
- MCP 接入：
  - 需要安装 Python MCP SDK（`pip install modelcontextprotocol` 或供应商 SDK）。
  - 在配置中开启：
```
{
  "tools": {
    "enabled": true,
    "max_iterations": 3,
    "builtin_tools": ["get_time", "mcp:*"],
    "mcp_enabled": true,
    "mcp_servers": [
      {
        "name": "calc",
        "command": "python",
        "args": ["-m", "your_calc_mcp_server"],
        "env": {"EXAMPLE": "1"}
      }
    ]
  }
}
```
  - 使用方式：模型在调用工具时可使用 `mcp:<server>:<tool>`（例如 `mcp:calc:calculator`）。

TTS 语音输出
- 三种模式：`openai` / `http` / `command`
  - openai：使用 OpenAI TTS（例如 `gpt-4o-mini-tts`）。需要在 `api` 中正确配置 Key/URL。
  - http：向自建/第三方 HTTP 接口发送 `{"text","voice","format"}`，响应可为音频字节或 JSON(base64)。
  - command：执行本地命令，将音频写入 `{out}` 指定路径。支持占位符 `{text}/{voice}/{format}/{out}`。
- 相关配置（示例）：
```
{
  "output": {
    "tts_enable": true,
    "tts_provider": "openai",
    "tts_model": "gpt-4o-mini-tts",
    "tts_voice": "alloy",
    "tts_format": "mp3"
  }
}
```
- 生成的音频文件存放：`data/ai_chat/tts/`，消息将自动携带语音（具体见适配器能力）。

会话与记忆
- 历史与状态持久化到 SQLite：表 `ai_chat_sessions`（位于 `data/entertain.db`）。
- `session.max_rounds` 控制保留的 user+assistant 轮数（模型消息前会裁剪）。
- 群聊短期上下文（内存 LTM）：按 `chatroom_history_max_lines` 行保存“最近群聊摘要”，用于主动回复提示。
- 摘要记忆：
  - `memory.enable_summarize`: 启用/禁用
  - `memory.summarize_min_rounds`: 开始总结所需最小轮数
  - `memory.summarize_interval_rounds`: 间隔轮数再次总结
  - 摘要写入会话 config_json 的 `memory_summary` 字段并注入 System Prompt。

权限与作用域
- 插件默认对所有场景生效（群/私）。
- 权限等级（参考本项目 PermLevel）：
-  管理员：`#清空会话`、`#开启AI`、`#关闭AI`、`#切换人格` 等
-  超管：`#服务商列表`、`#切换服务商`、`#工具列表`、`#开启/关闭工具`、`#开启/关闭TTS`、`#重载AI配置`

完整配置字段速览
- `api`: {名称: {`base_url`,`api_key`,`model`,`timeout`}}
- `session`: `api_active`,`default_temperature`,`max_rounds`,`chatroom_history_max_lines`,`active_reply_enable`,`active_reply_probability`,`active_reply_prompt_suffix`
- `tools`: `enabled`,`max_iterations`,`builtin_tools`,`mcp_enabled`,`mcp_servers`（含 `name`,`command`,`args`,`env`）
- `output`: `tts_enable`,`tts_provider`,`tts_model`,`tts_voice`,`tts_format`,`tts_http_*`,`tts_command`
- `input`: `image_max_side`,`image_jpeg_quality`
- `memory`: `enable_summarize`,`summarize_min_rounds`,`summarize_interval_rounds`

常见问题（FAQ）
- 没有回复/空白：检查 `config/ai_chat/config.json` 中 `api` 是否配置、`session.api_active` 是否指向存在的服务商、API Key 是否有效。
- 提示未配置 OpenAI：第一次运行会在日志中提示配置文件路径，请按路径补全配置并 `#重载AI配置`。
- 图片无法识别：确认发送的图片被适配器正确解析；或将图片以 URL 形式发送；必要时调高 `image_max_side`。
- 主动回复太频繁：降低 `active_reply_probability` 或关闭 `active_reply_enable`。
- TTS 无声音：
  - openai：确认 `api` 配置与 `tts_model` 有效；网络可达。
  - http：确认接口返回类型与 `tts_http_response_type` 匹配；必要时打印服务端日志排错。
  - command：保证命令包含 `{out}` 并能在本机写文件；检查生成路径与权限。
- MCP 看不到工具：确保安装 MCP SDK、在配置中开启 `mcp_enabled` 并正确填写 `mcp_servers`，重载配置后再试。

兼容性与注意事项
- 本插件使用 OpenAI Chat Completions 风格的接口；第三方服务需兼容该协议（含 `tools` 字段）。
- 返回内容中的图片 URL/Markdown 图片会被提取成独立媒体发送，并从文本中移除对应标记。
- 插件文件统一使用 UTF-8 编码；若控制台出现乱码，请将终端编码设置为 UTF-8。

开源与贡献
- 欢迎提交 Issue 与 PR 来完善功能与文档。
