AI 对话（ai_chat）

简介
- 基于 NoneBot2 的高性能 AI 对话插件，支持多模态输入/输出、工具调用（Function Calling + MCP）、多会话管理、人设系统与可插拔钩子。

核心特性
- 多模态输入：支持图片+文本输入（自动拼接为 Chat Completions 的 content parts）。
- 多模态输出：
  - 解析模型输出中的 Markdown 图片与图片链接，自动以图片消息发送；
  - 可配置开启 TTS 语音回复（OpenAI TTS）。
- 工具调用（完全体）：
  - 内置装饰器式工具注册，OpenAI Function Calling JSON Schema 对齐；
  - 可选启用 MCP 动态工具桥接，以 `mcp:<server>:<tool>` 形式暴露给模型；
  - 循环处理工具往返至停止或达迭代上限。
- 会话管理：按会话 ID 维护历史与状态，支持启停、清空历史、切换人格；
- 钩子扩展：pre/post 两类钩子可动态改写 messages、model、temperature、tools 或最终响应文本；
- 多服务商配置：在配置中维护多个 base_url/api_key/model，并可通过命令切换。

安装与依赖
- 依赖见仓库 `requirements.txt`（openai>=1.0、pydantic>=2、sqlalchemy>=2、sqlmodel、aiosqlite 等）。
- 运行环境：NoneBot2 + OneBot v11 适配器。
- 语音 TTS：需使用支持的 OpenAI TTS 模型（默认 `gpt-4o-mini-tts`）。
- MCP（可选）：如需使用，需安装 MCP Python SDK 并配置 MCP 服务器命令。

配置文件
- 位置：`config/ai_chat/config.json` 与 `config/ai_chat/personas/`（可用 `NPE_CONFIG_DIR` 重定向，见 `core/framework/utils.py`）。
- Schema 注册位置：`plugins/ai_chat/config.py`。

配置示例（节选）
```
{
  "api": {
    "openai": {"base_url": "https://api.openai.com/v1", "api_key": "sk-...", "model": "gpt-4o-mini", "timeout": 60}
  },
  "session": {
    "api_active": "openai",
    "default_temperature": 0.7,
    "max_rounds": 8,
    "chatroom_history_max_lines": 200,
    "active_reply_enable": false,
    "active_reply_probability": 0.1,
    "active_reply_prompt_suffix": "请参考以下消息进行自然回复：`{message}`。"
  },
  "tools": {
    "enabled": true,
    "max_iterations": 3,
    "builtin_tools": ["get_time", "get_weather", "mcp:*"],
    "mcp_enabled": true,
    "mcp_servers": [
      {"name": "calc", "command": "your-mcp-server", "args": [], "env": {}}
    ]
  },
  "output": {
    "tts_enable": false,
    "tts_model": "gpt-4o-mini-tts",
    "tts_voice": "alloy",
    "tts_format": "mp3"
  }
}
```

人格文件（personas/）
- 支持 `.txt`、`.md`、`.docx`，优先选择同名 `.md`；
- `.txt/.md` 可使用极简 Front Matter：
```
---
name: 默认助手
description: 一个友好的 AI 助手
---

这里是系统提示词正文...
```

使用方法
- 对话触发：
  - 群聊需 @ 机器人或命中“主动回复”；
  - 私聊直接发送文本/图片；
  - 支持仅图片消息（无文本）。
- 会话管理：
  - `#清空会话` 清空历史；`#会话信息` 查看状态；`#开启AI`/`#关闭AI` 启停会话（管理员）。
- 人格管理：
  - `#人格列表` 查看可用人格；`#切换人格 <代号>` 切换人格（管理员）。
- 工具管理：
  - `#工具列表` 查看工具与启用状态；
  - `#开启工具 <name>` 将工具加入启用列表并打开总开关；
  - `#关闭工具 <name>` 从启用列表移除（管理员）。
  - `#开启TTS` / `#关闭TTS` 开关语音回复（超管）。
- 服务商管理：
  - `#服务商列表`、`#切换服务商 <name>`。
- 配置重载：
  - `#重载AI配置` 重新加载配置与人格并重建客户端（超管）。

多模态说明
- 输入图片：自动将 `text + image(s)` 组织为 OpenAI chat 的 content 数组；
- 输出图片：自动解析模型输出中的 Markdown 图片/图片链接并逐条发送；
- 语音 TTS：当 `output.tts_enable = true` 时，生成语音文件并通过 `record` 语音消息发送（OneBot v11）。

本地 TTS 接入
- 统一接口：通过 `output.tts_provider` 选择提供方（`openai`/`http`/`command`）。
- HTTP 模式：
  - 配置 `output.tts_provider = "http"`
  - 配置 `output.tts_http_url`（默认 POST，载荷 JSON：`{"text": 文本, "voice": 发音, "format": 格式}`）
  - `output.tts_http_response_type` 选择 `bytes`（响应体即音频字节）或 `base64`（JSON 返回 base64，字段名由 `output.tts_http_base64_field` 指定，默认 `audio`）。
- 命令行模式：
  - 配置 `output.tts_provider = "command"`
  - 配置 `output.tts_command`，命令模板支持占位符：`{text}`、`{voice}`、`{format}`、`{out}`（输出文件路径）
  - 你的命令需把合成后的音频写入 `{out}` 指定的路径并退出（返回码 0）

示例（本地 TTS）
```
{
  "output": {
    "tts_enable": true,
    "tts_provider": "http",
    "tts_http_url": "http://127.0.0.1:5000/tts",
    "tts_http_response_type": "bytes",
    "tts_format": "mp3",
    "tts_voice": "xiaoyan"
  }
}
```

```
{
  "output": {
    "tts_enable": true,
    "tts_provider": "command",
    "tts_command": "my_tts.exe --text \"{text}\" --voice {voice} --format {format} --out \"{out}\"",
    "tts_format": "wav",
    "tts_voice": "zh-CN"
  }
}
```

MCP 工具桥接
- 在 `tools` 中开启 `mcp_enabled` 并配置 `mcp_servers`；
- 在 `builtin_tools` 中加入 `mcp:*`（全部启用）或指定 `mcp:<server>:<tool>`；
- 工具执行结果以 `tool` 角色消息写回给模型，继续对话。

二次开发
- 钩子：`plugins/ai_chat/hooks.py` 中注册 `register_pre_ai_hook` / `register_post_ai_hook`；
- 自定义工具：使用 `plugins/ai_chat/tools.py` 中的 `@register_tool(...)` 装饰器；
- 重要位置：命令 `plugins/ai_chat/commands.py`，核心 `plugins/ai_chat/manager.py`，配置与人格 `plugins/ai_chat/config.py`，工具与 MCP `plugins/ai_chat/tools.py`、`plugins/ai_chat/mcp.py`。

注意事项
- 请确保为当前激活服务商配置有效 API Key；
- TTS 调用需要模型支持，如不可用将自动降级为仅文本；
- MCP 需正确安装 SDK 并配置服务器命令，初始化失败时会自动跳过。

进阶能力与优化建议
- 图片压缩：对本地图片按最长边与 JPEG 质量压缩，降低上传体积，提升响应速度。
- 长期记忆：可开启摘要，定期归纳历史并注入 System Prompt，有效降低上下文体积。
- 并发工具：对同批次 Function Calling 的多个工具并发执行，减少工具往返耗时。
- 流式输出（建议）：可选改造为流式分段发送，提升“首字符时间”，遇接口限制可退化为分段发送。
- RAG（建议）：接入向量检索，把外部知识/文档透传进模型，提升专业问答质量与可追溯性。
- 多提供商容错（建议）：对 429/超时自动切换到备选模型或重试，提高可用性。
- 质量评估（建议）：对生成结果做自评与重写（短路规则），兼顾速度与质量。
