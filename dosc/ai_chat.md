# AI 对话插件（ai_chat）详解

本插件为 NoneBot2 的高性能 AI 对话能力，支持多会话、人格系统、好感度统计与工具调用，集成统一权限与配置系统。

- 目录位置：`plugins/ai_chat/`
- 主要文件：`__init__.py`、`config.py`、`manager.py`、`models.py`、`tools.py`、`commands.py`

## 功能概览

- 群聊 @ 机器人 或 私聊直接聊天，自动维持上下文
- 人格系统：从 JSON 加载多个人格，可动态切换
- 好感度：按互动次数与情感变化累积（可配置）
- 工具调用：支持 OpenAI Function Calling（内置时间、天气示例）
- 缓存优化：会话/历史/好感度多层缓存，减少数据库与 API 压力
- 管理命令：清空会话、查看信息、开关 AI、切换人格/服务商、热重载配置

## 配置与文件布局

- 配置目录：`config/ai_chat/`
  - `config.json`：AI 对话主配置（由框架注册与维护）
  - `personas.json`：人格配置（首次不存在会自动写入默认示例）
- 数据库：`data/entertain.db`（SQLite，框架统一管理）

配置通过 `plugins/ai_chat/config.py` 管理，核心结构如下（简要）：

- `api`：数组，支持多个服务商（如 OpenAI 兼容接口）
  - `name` 唯一名（用于切换）
  - `base_url`、`api_key`、`model`、`timeout`
- `api_active`：当前启用的服务商名（按 `name` 匹配）
- `cache`：缓存 TTL（秒）
  - `session_ttl`、`history_ttl`、`favorability_ttl`
- `session`：会话默认参数
  - `default_max_history`、`default_temperature`、`auto_create`
- `favorability`：好感度参数（开关与增量）
- `tools`：工具调用（开关、最大迭代、内置工具名列表）
- `response`：回复行为（最大长度、群聊是否 @ 用户）

可在运行期使用命令 `#重载AI配置` 热重载 `config.json` 与 `personas.json`，并重建客户端、清空内存缓存。

## 数据如何存储（SQLite 数据库）

数据库由 `db/base_models.py` 统一初始化，文件路径为 `data/entertain.db`。本插件定义三张表（`plugins/ai_chat/models.py`）：

- 表 `ai_chat_sessions`（ChatSession）
  - `session_id`：会话唯一标识（格式：`group_<群号>` 或 `private_<QQ>`）
  - `session_type`：`group` | `private`
  - `group_id`、`user_id`
  - `persona_name`：当前选用人格键名（对应 `personas.json`）
  - `max_history`：历史保留条数
  - `config_json`：冗余配置 JSON（保留扩展）
  - `is_active`：会话是否启用 AI
  - `created_at`、`updated_at`

- 表 `ai_message_history`（MessageHistory）
  - `session_id`、`user_id`、`user_name`
  - `role`：`user` | `assistant` | `tool` | `system`
  - `content`：消息内容
  - `tool_calls`：工具调用原始 JSON（可空）
  - `tool_call_id`：工具调用 ID（可空）
  - `tokens`：消耗（可选，未必填）
  - `created_at`

- 表 `ai_user_favorability`（UserFavorability）
  - `user_id`、`session_id`
  - `favorability`：0–100（默认 50）
  - `interaction_count`、`positive_count`、`negative_count`
  - `last_interaction`、`updated_at`

所有表操作都提供了便捷的类方法（带自动会话与提交）：
- 会话：`get_by_session_id`、`create_session`、`update_persona`、`update_active_status`
- 历史：`get_recent_history`、`add_message`、`clear_history`
- 好感度：`get_favorability`、`create_favorability`、`update_favorability`、`set_favorability`

数据库在框架启动时自动初始化，无需额外操作。

## 缓存如何存储（内存 TTL）

缓存由 `CacheManager`（`plugins/ai_chat/manager.py`）负责，采用进程内 L1 缓存 + TTL：

- 键空间与示例
  - 会话：`session:<session_id>`
  - 历史：`history:<session_id>`
  - 好感度：`favo:<user_id>:<session_id>`
- TTL 来源：`config.json -> cache` 中的 `session_ttl` / `history_ttl` / `favorability_ttl`
- TTL 语义：`ttl=0` 表示永久缓存（直到手动清理）
- 并发安全：通过 `asyncio.Lock` 保护缓存字典与逐会话串行化
- 失效策略：
  - 写入历史与好感度后，主动 `delete` 对应键
  - `#重载AI配置` 会触发 `cache.clear()` 全量清空
  - 会话配置变更（如切换人格/开关 AI）会清理 `session:<session_id>`

注意：缓存仅存于进程内存，不落盘，重启或热重载后会重建。

## 命令清单与权限

命令均在 `plugins/ai_chat/commands.py` 注册，已集成统一权限系统：

- 对话触发（私聊/群聊）
  - 私聊：任意文本即触发
  - 群聊：必须 @ 机器人后再跟随文本
- 会话管理
  - `#清空会话`：清空当前会话历史（所有人可用）
  - `#会话信息`：查看当前会话配置（所有人可用）
  - `#开启AI`：开启当前会话 AI（需管理员/群主/超管）
  - `#关闭AI`：关闭当前会话 AI（需管理员/群主/超管）
- 人格系统
  - `#人格`：查看当前人格信息
  - `#人格列表`：列出可用人格（来自 `personas.json` 的键）
  - `#切换人格 <名称>`：切换会话人格（需管理员/群主/超管）
- 服务商切换
  - `#切换服务商 <名称>`：按 `api[].name` 选择服务商（需管理员/群主/超管）
    - 说明：当前实现未持久写回 `api_active`，仅重建客户端。若需持久生效，请在 `config/ai_chat/config.json` 手动设置 `api_active`。
- 好感度
  - `#好感度`：查看自己在当前会话的好感度统计
- 系统管理
  - `#重载AI配置`：热重载配置与人格、重建客户端并清空缓存（需超级用户）

群聊回复是否 @ 用户由 `config.response.enable_at_reply` 控制（默认开启）。

## 工作流程（处理一条消息）

核心逻辑位于 `ChatManager.process_message`：

1) 入口判断与会话锁
- 群聊：检测是否 @ 机器人；私聊直接通过
- 按 `session_id` 获取会话级锁，保证同会话串行、不同会话并行

2) 并发加载上下文（带缓存）
- 会话：`_get_session()`（可自动创建，受 `session.auto_create` 控制）
- 历史：`_get_history()`（上限 `session.default_max_history`）
- 好感度：`_get_favorability()`（不存在则自动创建，默认 50）

3) 构建消息
- `system`：选用当前人格的 `system_prompt`，并按好感度附加修饰语
- 历史消息：按顺序追加；群聊会为用户消息前缀 `昵称: 内容`
- 当前用户消息：群聊为 `昵称: 内容`，私聊为原文

4) 调用 AI（OpenAI 兼容接口）
- 模型选自当前激活服务商 `api_active` 对应项的 `model`
- 温度取 `session.default_temperature`
- 若启用工具：附带工具 Schema（见下）
- 若返回包含 `tool_calls`：进入工具迭代流程

5) 工具调用迭代（Function Calling）
- 逐个执行工具，将结果以 `role=tool`、携带 `tool_call_id` 追加到消息中
- 再次调用 AI，让其综合工具结果继续生成
- 迭代次数上限：`tools.max_iterations`

6) 异步持久化与缓存失效
- 后台任务追加两条历史（用户/助手）
- 若开启好感度：按 `favorability.per_message_delta` 增加并统计
- 删除 `history:<sid>` 与 `favo:<uid>:<sid>` 缓存键

7) 回复用户
- 群聊是否 @ 由配置控制；私聊直接发送

异常处理：API/存储异常会记录日志，并回复兜底信息（不抛出到上层）。

## 工具调用扩展

工具注册在 `plugins/ai_chat/tools.py`，使用装饰器：

```python
@register_tool(
    name="get_time",
    description="获取当前日期和时间",
    parameters={"type": "object", "properties": {}}
)
async def tool_get_time() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")
```

- `register_tool(name, description, parameters)`：注册工具定义与处理函数
- `get_enabled_tools([...])`：按配置名生成 OpenAI `tools` 参数
- `execute_tool(name, args)`：执行工具并返回字符串

内置示例：
- `get_time`：当前时间
- `get_weather`：模拟城市天气（可按需接入真实 API）

## 人格配置

- 文件：`config/ai_chat/personas.json`
- 键为人格键名，值为对象：`{ name, description, system_prompt }`
- 首次不存在会写入默认三人格：`default`、`tsundere`、`professional`

使用命令 `#人格列表` 查看可用键，`#切换人格 <键名>` 动态切换。

## 常见问题与提示

- 未配置 API Key：插件会在加载时给出日志警告，并返回“AI 未配置或暂不可用”。请在 `config.json` 的 `api[].api_key` 设置密钥，并确保 `api_active` 指向该项。
- 切换服务商未持久保存：`#切换服务商 <名称>` 仅重建客户端，未写回 `api_active`。若需重启后仍生效，请手动修改 `config.json`。
- 会话 ID 规则：群聊 `group_<群号>`，私聊 `private_<QQ>`；用于区分缓存、历史与好感度作用域。
- 缓存 TTL：根据负载适当调大 `history_ttl`/`favorability_ttl` 可明显减少数据库压力；变更后通过 `#重载AI配置` 生效。

---

如需进一步扩展（自定义工具、接入新服务商、细化权限），参考各文件内注释与统一配置/权限框架（`core/framework`）。
