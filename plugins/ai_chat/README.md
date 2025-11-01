**AI 对话（ai_chat）**
- 基于 NoneBot2 的高性能 AI 对话插件，支持多会话管理、人格切换、OpenAI Function Calling 工具调用，以及可插拔的前后置钩子。

**功能亮点**
- 多会话管理：按会话 ID 管理历史与状态（群聊/私聊），支持开关会话与清空历史。
- 人格系统：内置多个人格，可通过命令切换，会话级生效。
- 工具调用：支持 OpenAI Function Calling，内置时间/天气示例工具，可热切换启用列表。
- 前后置钩子：提供 pre/post AI 调用钩子，可在业务侧自定义消息改写、响应后处理等。
- 聊天室记忆：群聊中维护轻量“聊天室历史”（内存环形缓冲），更贴近群聊语境。
- 多服务商配置：支持在配置中维护多组 base_url/api_key/model，并通过命令切换。

**安装与依赖**
- 依赖 openai>=1.0、pydantic>=2、sqlalchemy>=2、sqlmodel、aiosqlite 等（见 `requirements.txt`）。
- 运行于 NoneBot2 + OneBot v11 适配器。
- 数据库存储使用 SQLite（自动建表，路径参见框架 `data/` 目录）。

**配置文件**
- 位置：`config/ai_chat/config.json` 与 `config/ai_chat/personas/`（由 `NPE_CONFIG_DIR` 可整体重定向，参考 `core/framework/utils.py`）。
- 注册默认配置与 schema：`plugins/ai_chat/config.py`。

配置项（`config.json`）
- `api`：字典，键为服务商名称，值包含 `base_url`、`api_key`、`model`、`timeout`。
- `session`：会话行为。
  - `api_active`：当前使用的服务商名（匹配 `api` 的键）。
  - `default_temperature`：默认温度。
  - `max_rounds`：对话上下文“轮数”（user+assistant 记一轮）。
  - `chatroom_history_max_lines`：群聊“聊天室历史”内存上限行数。
  - `active_reply_enable`：是否启用群聊“主动回复”。
  - `active_reply_probability`：主动回复触发概率（0~1）。
  - `active_reply_prompt_suffix`：主动回复追加到 messages 的提示（支持 `{message}`/`{prompt}` 占位）。
- `tools`：工具调用。
  - `enabled`：全局开关。
  - `max_iterations`：工具调用最多迭代轮次。
  - `builtin_tools`：启用的工具名列表（如 `get_time`、`get_weather`）。

人格文件（`personas/` 目录）
- 支持 `.txt`、`.md`、`.docx` 三种文本格式；文件名（不含扩展名）作为人格代号。
- `.txt/.md` 可在顶部使用极简 Front Matter（可选）：
  ```
  ---
  name: 显示名
  description: 描述
  ---

  这里是系统提示(system prompt)正文...
  ```
- 若未提供 Front Matter，则 `name` 默认为文件名，`description` 取正文首行摘要。

**使用方式**
- 对话触发：
  - 群聊：需 @ 机器人或命中“主动回复”（概率触发）；
  - 私聊：直接发送文本即可。
- 会话管理：
  - `#清空会话` 清空当前会话历史。
  - `#会话信息` 查看当前会话状态与人格等。
  - `#开启AI` / `#关闭AI` 管理当前会话可用性（管理员）。
- 人格相关：
  - `#人格` 查看当前人格。
  - `#人格列表` 查看可用人格列表。
  - `#切换人格 <代号>` 切换当前会话人格（管理员）。
- 服务商管理：
  - `#服务商列表` 查看当前配置的服务商、默认模型与地址。
  - `#切换服务商 <name>` 切换 `session.api_active` 并重建客户端（管理员）。
- 工具管理：
  - `#工具列表` 查看所有注册工具及启用状态。
  - `#启用工具 <name>` 将工具加入启用列表并打开全局开关（管理员）。
  - `#关闭工具 <name>` 从启用列表移除工具（管理员）。
- 配置重载：
- `#重载AI配置` 重新加载 `config.json` 和 `personas/` 并重建客户端（超管）。

命令注册位置
- 见 `plugins/ai_chat/commands.py:111` 起始的“通用触发”与后续各管理命令。

**实现要点**
- 会话与历史
  - 会话模型：`plugins/ai_chat/models.py` 中 `ChatSession`（表名 `ai_chat_sessions`）。
  - 会话历史：仅维护 JSON 字段 `history_json`，读写由 `append_history_items` 和 `clear_history_json` 完成。
  - 迁移保障：启动首次调用时通过 `ensure_history_column()` 确保列存在（SQLite PRAGMA）。
- 对话核心
  - 入口：`plugins/ai_chat/manager.py` `ChatManager.process_message()`。
  - 构造 messages：`_build_messages()` 注入人格 System Prompt、历史消息、群聊用户名前缀、主动回复后缀等。
  - OpenAI 调用：`_call_ai()` 走 `client.chat.completions.create()`，并按需处理 `tool_calls`（Function Calling 循环调用）。
  - 钩子：`hooks.py` 提供 `register_pre_ai_hook` 与 `register_post_ai_hook`，在调用前后可动态改写 messages/model/temperature/tools 或响应文本。
- 群聊“聊天室历史”
  - 内存环形缓冲：`ChatroomMemory` 通过 `chatroom_history_max_lines` 控制大小，不落库。
  - 在主动回复模式下会以 System Prompt 追加带入。

**二次开发**
- 自定义钩子（pre/post）：
  - 引入：`from nonebot_plugin_entertain.plugins.ai_chat.hooks import register_pre_ai_hook, register_post_ai_hook`。
  - pre 示例：
    - 返回 dict 可覆盖参数：`{"temperature": 0.2, "model": "gpt-4o-mini", "messages": [...], "tools": [...]}`。
  - post 示例：
    - 返回 str 可直接替换最终响应。
- 自定义工具：
  - 参考 `plugins/ai_chat/tools.py` 的装饰器 `register_tool(name, description, parameters)` 注册；
  - 函数签名与 `parameters` 中的 JSON Schema 对齐；
  - 由 `execute_tool(name, args)` 异步调用，并写入 `tool` 角色消息返回。

**常见问题与注意事项**
- API Key：必须在 `config/ai_chat/config.json` 的 `api` 字典中，`session.api_active` 对应项设置 `api_key`，否则插件会禁用对话能力（见 `plugins/ai_chat/__init__.py`）。
- 主动回复：该功能会在群聊中“随机”触发回复，默认概率 0.1，可能造成群内较高活跃/干扰，建议谨慎开启或降低概率，并结合权限白名单使用。
- 上下文成本：`max_rounds` 越大，调用成本越高；同时 `chatroom_history_max_lines` 过大会增加 System Prompt 体积，注意平衡。
- SQLite 迁移：`ensure_history_column()` 仅对 SQLite 生效；如更换数据库，需要自行迁移该列。
- 并发与锁：同一会话串行处理（会话锁），历史写入有独立锁，避免竞态；不同会话可并行处理。
- 模型兼容：默认 `gpt-4o-mini`，确保所选模型支持 Function Calling（若启用工具）。

**改动与差异点**
- 移除了“好感度”等历史逻辑，改为纯会话+JSON 历史持久化（轻量可靠）。
- 增加 pre/post 钩子能力，便于在业务层扩展。
- 新增“聊天室历史”内存缓冲，提升群聊语境理解。

**改进建议**
- 流式回复：可增加流式输出/撤回合并优化体验。
- 回复引用：在群聊中引用被回复消息，减少误解。
- 细化主动回复：增加按群白名单、时间段、关键词等触发策略。
- 工具权限：为工具级别增加启用权限与参数校验。
- 错误提示：针对常见错误（超时/配额/未配置）返回更友好的中文提示。

**相关代码位置**
- 触发与命令：`plugins/ai_chat/commands.py:111`、`plugins/ai_chat/commands.py:169`、`plugins/ai_chat/commands.py:184` 等。
- 核心管理：`plugins/ai_chat/manager.py`（OpenAI 调用、历史维护、会话并发控制）。
- 配置与人格：`plugins/ai_chat/config.py:276`、`plugins/ai_chat/config.py:325`、`plugins/ai_chat/config.py:386`。
- 工具与钩子：`plugins/ai_chat/tools.py`、`plugins/ai_chat/hooks.py`。
