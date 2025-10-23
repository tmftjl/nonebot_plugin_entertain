# AI 对话插件缓存使用说明

本文档专门介绍 `plugins/ai_chat/` 的缓存设计、配置与最佳实践，帮助你在高并发场景下获得稳定且低时延的对话体验。

## 核心概念

- 组件：`CacheManager`（位于 `plugins/ai_chat/manager.py`）
  - L1 进程内缓存，基于字典 + TTL。
  - 提供方法：`get(key)`、`set(key, value, ttl)`、`delete(key)`、`clear()`、`clear_pattern(substr)`。
- 非持久化：缓存仅存在于进程内存，重启/热重载后会重建。
- 并发安全：内部通过 `asyncio.Lock` 串行化对缓存字典的访问。

## 键空间与含义

- `session:<session_id>`：缓存会话对象（`ChatSession` 行）。
- `history:<session_id>`：缓存当前会话的上下文消息列表（从 `ai_chat_sessions.history_json` 解析的列表）。
- `favo:<user_id>:<session_id>`：缓存用户在该会话的好感度对象（`UserFavorability`）。

示例：
- 群聊 `123456` 的会话键：`session:group_123456`、`history:group_123456`
- 私聊 `987654` 的好感度键：`favo:987654:private_987654`

## 配置位置与 TTL

文件：`config/ai_chat/config.json`

- `cache.session_ttl`：会话缓存 TTL（秒）
- `cache.history_ttl`：历史缓存 TTL（秒）
- `cache.favorability_ttl`：好感度缓存 TTL（秒）

说明：
- `ttl = 0` 表示永久缓存（直到显式清理）。
- 修改配置后，可用命令 `#重载AI配置` 热重载并清空内存缓存。

## 命中路径（读）

处理消息时（`ChatManager.process_message`）：
1. 命中 `session:<sid>`，否则查询表 `ai_chat_sessions`，并缓存。
2. 命中 `history:<sid>`，否则优先读取 `ai_chat_sessions.history_json`（单条记录，一次 I/O），解析为列表并缓存；若空，再回退 `ai_message_history` 最近 `max_history` 条，随后回填到 `history_json` 并缓存。
3. 命中 `favo:<uid>:<sid>`，否则查询/创建 `UserFavorability` 并缓存。

这样“会话一次读一条记录”即可获得上下文，显著降低数据库开销与对话耗时。

## 写入与失效（写）

对话完成后后台异步执行（不阻塞回复）：
- 明细表：向 `ai_message_history` 插入两条（`user`/`assistant`）。
- 会话 JSON：将两条新增消息追加到 `ai_chat_sessions.history_json`，并按 `max_history` 自动裁剪（超出弹出最早的）。
- 缓存：
  - `history:<sid>` 直接覆盖为最新列表；
  - `session:<sid>` 刷新为最新会话行；
  - 删除 `favo:<uid>:<sid>`，迫使下次读取好感度最新值。

管理命令联动：
- `#清空会话`：清空明细表与 `history_json`，并删除 `history:<sid>`、`session:<sid>`。
- `#切换人格`、`#开启AI`/`#关闭AI`：删除 `session:<sid>`，触发下次重载会话配置。
- `#重载AI配置`：全量 `cache.clear()`。

## 并发与一致性

- 对话处理：按 `session_id` 使用会话锁串行化，保证同会话内的处理顺序。
- 历史写入：维护独立的“历史写入锁”，确保并发追加 `history_json` 时不会覆盖彼此。
- 建议：不要绕过 `ChatManager` 直接改写 `history_json`，插件内部已负责更新缓存与裁剪逻辑。

## 最佳实践与建议

- 大群建议：
  - `cache.history_ttl` 设置略大于平均消息间隔（如 30～120 秒），减少频繁解析 JSON 与 I/O。
  - `session.default_max_history` 视上下文需求取 10～30，过大将增大内存与 token 成本。
- 私聊建议：
  - 可适当提高 `history_ttl`，体验更顺滑。
- `ttl=0` 场景：
  - 适配极高吞吐且单进程部署；注意内存增长与配置变更后需要手动清理缓存。

## 调试与排错

- 命令：
  - `#会话信息`：确认 `max_history`、`persona_name`、`is_active` 等。
  - `#清空会话`：快速重置某个会话的上下文。
  - `#重载AI配置`：热重载配置并清空缓存（排除缓存导致的“看起来没生效”问题）。
- 代码辅助：
  - 仅开发调试时，可调用 `chat_manager.cache.clear_pattern('session:group_123')` 精确清理某会话相关缓存。

## 扩展开发：如何正确使用缓存

当你编写扩展逻辑需要修改上下文：

1) 优先通过模型方法维护会话 JSON
```python
from plugins.ai_chat.models import ChatSession

await ChatSession.append_history_items(
    session_id=sid,
    items=[{"role": "system", "content": "注意事项..."}],
    max_history=desired_max,
)
```

2) 同步刷新缓存（若你的逻辑绕过了 ChatManager）
```python
from plugins.ai_chat.manager import chat_manager

# 重新拉取并写回缓存
session = await ChatSession.get_by_session_id(session_id=sid)
await chat_manager.cache.set(f"session:{sid}", session, ttl=cfg.cache.session_ttl)

# 可选：直接刷新 history 列表缓存
import json
history_list = json.loads(session.history_json or "[]") if session else []
await chat_manager.cache.set(f"history:{sid}", history_list, ttl=cfg.cache.history_ttl)
```

3) 不要忘记相关失效
```python
await chat_manager.cache.delete(f"favo:{user_id}:{sid}")
```

> 提示：如果只是正常对话流程，无需手动操作缓存，插件已自动维护。

## 常见问题（FAQ）

- Q：缓存会持久化到磁盘吗？
  - A：不会，仅进程内存。重启/热重载后会重建。
- Q：为何读历史是从 `history_json` 开始？
  - A：将“最近 N 条上下文”放在会话单行中，可“一次查询拿到上下文”，显著降低 I/O 与 ORM 开销，明细表仅用于归档与审计。
- Q：修改了配置为什么没生效？
  - A：请先 `#重载AI配置`，该命令会清空缓存并重建客户端。

