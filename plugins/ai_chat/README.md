AI 对话（ai_chat）

概述
- 基于 NoneBot2 的高性能 AI 对话插件，支持多模态（文本/图片）、工具调用（Function Calling + 可选 MCP）、多会话与人格系统。

功能特性
- 多模态输入：支持图片 + 文本（自动组装为 Chat Completions content parts）。
- 图片输出识别：自动提取模型输出中的 Markdown 图片/直链/data:image。
- 可选 TTS：统一接口支持 openai/http/command，将回复合成为语音并发送。
- 工具调用：
  - 装饰器式注册，OpenAI Function Calling JSON Schema。
  - 可选接入 MCP 动态工具（mcp:<server>:<tool>）。
  - 支持循环工具调用，直到模型不再调工具或达上限。
- 会话管理：按会话（群/私聊）维护配置与历史，支持启用/停用、切换人格、清空历史。
- 钩子扩展：pre/post 两类钩子，按需动态修改请求/响应。

基础指令
- 对话：群聊需 @ 机器人，或开启主动回复；私聊直接发送消息。
- 会话：
  - `#清空会话` 清除历史
  - `#会话信息` 查看状态
  - `#开启AI` / `#关闭AI`（管理员）
- 人格：
  - `#人格列表`
  - `#切换人格 <key>`（管理员）
- 服务商（超管）：
  - `#服务商列表`
  - `#切换服务商 <name>`
- 工具（超管）：
  - `#工具列表`
  - `#开启工具 <name>` / `#关闭工具 <name>`
  - `#开启TTS` / `#关闭TTS`
- 系统（超管）：
  - `#重载AI配置`

配置文件
- 位置：`config/ai_chat/config.json` 和 `config/ai_chat/personas/`
- 主要配置项见 `plugins/ai_chat/config.py`，支持可视化 Schema。

依赖
- 见仓库根目录 `requirements.txt`（openai>=1.0、pydantic>=2、sqlalchemy>=2、sqlmodel、Pillow、httpx 等）。

注意
- 请在配置文件中填写有效的 OpenAI API Key 并选择启用的服务商（`session.api_active`）。
- TTS 需相应模型/服务支持，未配置时自动退回文本。
- MCP 为可选功能，启用请安装相应 Python SDK 并在配置中添加 servers。

