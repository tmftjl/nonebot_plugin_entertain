# member_renewal Web 控制台重构实施说明（详细）

本文档定义将 `member_renewal` 重构为“网页控制台 + API”的详细工作项与实现规范，覆盖后端接口、前端页面、数据与配置迁移、安全与权限、测试与验收、里程碑与风险等。

## 1. 背景与目标

- 现状：
  - 续费/到期逻辑以命令为主，数据为本地 JSON，已有基础 Web 控制台雏形与 API（`/member_renewal/...`）。
  - 权限为全局 `config/permissions.json`，支持插件与命令粒度；暂无控制台管理入口。
- 目标：
  - 将 `member_renewal` 打造成“网页控制台型后台”，以 Web 管理为主、命令为辅。
  - 集中管理：群到期、批量操作、续费码、配置（调度/提醒/时区/模板等）、权限（插件/命令粒度）、操作审计、安全控制。
  - 平滑迁移数据与配置，保持命令兼容。

## 2. 术语（本插件内）

- 群记录（membership）：以群号为键，记录到期时间、状态、管理 bot 等。
- 续费码（code）：一次或多次使用的续费凭证，形如 `ww续费<时长><单位>-<随机>`。
- 控制台 Token：访问 Web 控制台 API 的访问令牌；可分角色（viewer/operator/admin）。

## 3. 数据与存储

### 3.1 路径迁移（M2 交付）

- 业务数据（群记录与续费码）：
  - 现状：`plugins/member_renewal/group_memberships.json`
  - 目标：`config/member_renewal/memberships.json`
  - 根目录通过 `utils.config_dir("member_renewal")` 决定（优先级：`NPE_CONFIG_DIR` > 包内 `config/` > `./config/`）。
  - 启动迁移：首次在新路径不存在且旧路径存在时，执行搬迁并备份旧文件为 `group_memberships.json.bak`。

- 插件配置：
  - 现状：`plugins/member_renewal/member_renewal.json`（由 `plugins/member_renewal/config.py` 读取）
  - 目标：`config/member_renewal/config.json`（采用统一 ConfigProxy 机制）
  - 启动迁移：将旧配置内容写入新文件（若新文件不存在），后续以新文件为准。

- 审计日志（新增）：
  - 路径：`config/member_renewal/audit.log`（追加写）
  - 内容：时间、IP、Token(脱敏)、角色、操作、参数摘要、结果（成功/失败）、错误摘要。

- 权限文件（保持）：
  - `config/permissions.json`

### 3.2 数据结构

#### memberships.json（建议结构）

```json
{
  "generatedCodes": {
    "ww续费7天-abcd12": {
      "length": 7,
      "unit": "天",
      "generated_time": "2025-10-05T12:00:00+00:00",
      "expire_at": "2025-10-31T00:00:00+00:00",  // 可选（新增：续费码有效期）
      "max_use": 1,                                // 可选（新增：最大可用次数）
      "used_count": 0                              // 可选（新增：已使用次数）
    }
  },
  "<group_id>": {
    "group_id": "123456",
    "expiry": "2025-10-31T12:00:00+00:00",
    "status": "active",                 // active | expired
    "managed_by_bot": "<bot_id>",
    "last_reminder_on": "2025-10-05",   // YYYY-MM-DD；同日仅提醒一次
    "expired_at": "2025-10-06T00:00:00+00:00", // 过期时间（状态切换时记录）
    "last_renewed_by": "<user_id>",
    "renewal_code_used": "ww续费..."
  }
}
```

### 3.3 配置结构（config/member_renewal/config.json）

现有字段（迁移）：

- `member_renewal_timezone`: string，默认 `Asia/Shanghai`
- `member_renewal_enable_scheduler`: bool，默认 true
- `member_renewal_schedule_hour/minute/second`: number
- `member_renewal_reminder_days_before`: number，默认 7
- `member_renewal_auto_leave_on_expire`: bool，默认 true
- `member_renewal_console_enable`: bool，默认 false
- `member_renewal_console_token`: string（将被新 tokens 替代，仍保留兼容）

新增字段（建议）：

- `member_renewal_contact_suffix`: string，提醒消息的联系方式后缀
- `member_renewal_remind_template`: string，提醒模板（支持占位符：`{group_id}`、`{days}`、`{expiry}`）
- `member_renewal_soon_threshold_days`: number，界定“即将到期”的阈值，默认 7
- `member_renewal_default_bot_id`: string，默认操作 bot
- `member_renewal_leave_mode`: string，`leave | dismiss`，退群策略
- `member_renewal_console_tokens`: array of { token, role, note?, disabled? }
- `member_renewal_console_ip_allowlist`: string[]，可选 IP 白名单
- `member_renewal_code_prefix`: string，续费码前缀，默认 `ww续费`
- `member_renewal_code_random_len`: number，随机段长度，默认 6（十六进制）
- `member_renewal_code_expire_days`: number，续费码默认有效期（天）
- `member_renewal_code_max_use`: number，默认 1（>1 支持多次使用）
- `member_renewal_daily_remind_once`: bool，默认 true
- `member_renewal_export_fields`: string[]，导出字段控制
- `member_renewal_rate_limit`: { window_sec: number, max: number }，API 频控参数

校验规则：

- 时区必须可用；失败时回落到 +08:00 并发出警告。
- 时间字段需为 ISO8601（带时区或明确为 UTC）。
- 单位限定：`天 | 月 | 年`。

## 4. 后端 API 设计（/member_renewal）

### 4.1 认证与安全

发送今汐登录，随机生成token，返回登录连接，设置一定时间有效期

### 4.2 接口列表

说明：所有 JSON 出错统一格式：

```json
{ "error": { "code": "bad_request", "message": "..." } }
```

- `GET /data`（viewer）
  - 返回：完整 memberships.json 内容。

- `POST /generate`（operator）
  - 入参：`{ length: number, unit: "天|月|年", count?: number=1, expire_days?: number, max_use?: number }`
  - 出参：`{ codes: string[] }`
  - 说明：生成 `count` 个续费码；支持设置有效期与最大使用次数。

- `POST /code/delete`（operator）
  - 入参：`{ code: string }`
  - 出参：`{ status: "ok" }`
  - 说明：仅可删除未使用的续费码。

- `POST /extend`（operator）
  - 入参：`{ group_id?: string, ids?: string[], length: number, unit: "天|月|年" }`
  - 出参（单个）：`{ group_id: string, expiry: string }`
  - 出参（批量）：`{ results: { [group_id: string]: { ok: boolean, expiry?: string, error?: string } } }`

- `POST /set_expiry`（operator）
  - 入参：`{ group_id: string, expiry: string | null }`（null 表示清空）
  - 出参：`{ group_id: string, expiry: string | null }`

- `POST /leave`（operator）
  - 入参：`{ group_id?: number, ids?: number[], bot_id?: string, dismiss?: boolean }`
  - 出参（单个）：`{ status: "ok" }`
  - 出参（批量）：`{ results: { [group_id: string]: { ok: boolean, error?: string } } }`

- `POST /remind`（operator）
  - 入参：`{ group_id?: number, ids?: number[], content?: string, bot_id?: string }`
  - 出参：`{ status: "ok" }` 或批量 `results` 格式
  - 行为：若未提供 content，则以模板渲染并追加 `contact_suffix`。

- `POST /assign_bot`（operator）
  - 入参：`{ group_id: string, bot_id: string }`
  - 出参：`{ status: "ok" }`

- `POST /job/run`（operator）
  - 行为：立即运行一次 `_check_and_process()`（提醒+退群）。
  - 出参：`{ reminded: number, left: number }`

- `GET /config`、`POST /config`（admin）
  - 返回/保存 `config/member_renewal/config.json`；保存后立即生效（必要时触发任务重排/权限重载）。

- `GET /permissions/plugins`（admin）
  - 返回：已发现的插件与命令清单（来自聚合扫描）。

- `GET /permissions?plugin=<name>`（admin）
  - 返回：插件级 `top` 与 `commands` 的权限条目。

- `POST /permissions`（admin）
  - 入参：`{ plugin: string, top?: {...}, commands?: { [name: string]: {...} } }`
  - 行为：写入并 `reload_permissions()`。

- `GET /audit`（admin）
  - 查询参数：`token? role? op? from? to? limit?`，分页/筛选审计日志。

- `GET /export`（operator|admin）
  - 参数：`type=memberships|codes`、`format=json|csv`、筛选选项。

### 4.3 错误码与头部

- 401 未授权、403 禁止、404 未找到、409 冲突（如重复使用的码）、422 参数错误、429 频控、500 服务内部错误。
- 频控头：`X-RateLimit-Limit`、`X-RateLimit-Remaining`、`Retry-After`。

## 5. 控制台前端设计

### 5.1 布局与导航

- 顶部导航 Tabs：概览｜群管理｜续费码｜配置｜权限｜审计
- 全局 Token 输入与保存（localStorage），显示当前角色与 IP。

### 5.2 功能页

- 概览（Dashboard）
  - 关键指标卡片：总群数、有效、今日到期、即将到期、已过期
  - 趋势：近 30 天提醒次数/退群数量（可选）

- 群管理
  - 表格：群号、状态（有效/今日/即将/过期）、到期时间、剩余天数、操作
  - 操作：提醒、+7天、设置到期、退群；批量提醒/延期/退群；选择默认单位
  - 过滤：有效/今日/即将/过期/全部、搜索 group_id、排序、分页

- 续费码
  - 列表：掩码显示、有效期、剩余可用次数、创建时间
  - 生成：长度+单位、数量、有效期天数、最大使用次数；复制与撤销

- 配置
  - 分区：调度（启用/时间）、时区、提醒（提前天数/模板/同日仅一次/联系方式后缀）、默认 bot、退群模式、续费码策略、频控、Token 管理（仅 admin）
  - 操作：保存并生效；重置为默认

- 权限
  - 插件选择器：列出插件与命令
  - 编辑：`enabled/level/scene/whitelist/blacklist`；批量更新；预览 diff；一键重载

- 审计
  - 列表：时间、操作者(Token 尾号/角色/IP)、操作、摘要、结果、错误
  - 过滤与导出 CSV/JSON

### 5.3 其他要求

- 全量修复中文乱码（现 `console.html/js` 存在 `�?` 字符），统一 UTF-8 文案与 i18n（当前仅 zh-CN）。
- 对话式提示/Toast、加载态遮罩、失败重试与错误提示友好化。

## 6. 调度任务

- 复用 `nonebot_plugin_apscheduler`，由配置控制开关与 Cron 时间。
- 任务内容：基于到期天数规则进行提醒；过期时可自动退群（可配置）。
- 控制台提供“立即执行一次”入口（`/job/run`）。

## 7. 权限配置管理

- 从 `config/permissions.json` 读取/保存，调用 `perm.reload_permissions()` 生效。
- 插件与命令枚举：复用聚合扫描（`config.aggregate_permissions()`）的结果。
- 控制台仅 admin 可写，operator 只读，viewer 无权访问该页。

## 8. 安全与审计

- Token：支持多 Token 与角色；Token 可禁用；展示最近使用时间（通过审计推导）。
- 审计日志：所有写接口记录；读接口对敏感数据（如导出）也记录。
- IP 白名单（可选）；跨域关闭（同源访问）。
- 内容安全：对 `content` 做长度与敏感词/超长拦截；续费码写入前校验。

## 9. 迁移与兼容性

- 数据：旧 `plugins/.../group_memberships.json` → 新 `config/member_renewal/memberships.json`，原文件保留为 `.bak`。
- 配置：旧 `plugins/.../member_renewal.json` → 新 `config/member_renewal/config.json`。
- 命令：全部保留，帮助文案加入“可前往控制台操作”。

## 10. 测试计划

- 单元：
  - 存储读写/迁移、续费码生成/校验、天数计算与模板渲染、频控计算
  - 权限编辑保存与热重载
- 接口：
  - 鉴权（角色/白名单/超限）、批量接口（成功/部分失败/全部失败）
  - 错误码/错误体一致性、幂等性
- 集成：
  - 与 OneBot v11 交互的模拟（send_group_msg/leave）
  - 调度任务定时触发与“立即执行”
- 手测清单：
  - 控制台各页功能、乱码修复、导出文件、审计检索

## 11. 验收标准（关键）

- 数据迁移成功且幂等；无数据丢失；新旧路径可回滚。
- 控制台支持查看/筛选/批量操作，错误可视化明确。
- 续费码可生成/复制/撤销；支持有效期与多次使用（如启用）。
- 配置可读写并即时生效（调度时间变更后能重排）。
- 权限可视化编辑并热重载生效；不破坏现有权限模型。
- 审计可用、可检索、可导出；敏感信息不泄露。
- 安全：Token 角色限制生效；频控生效；主要接口具备输入校验。

## 12. 性能与稳定性

- 文件写入采用原子写（先写临时文件再替换），避免并发破坏。
- 数据量预估：群上千级别，单文件 JSON 可承载；若后续增长再考虑换存储。
- API 并发：采用简易锁或单线程串行写；读不锁。

## 13. 运维与部署

- 指定配置目录：`NPE_CONFIG_DIR=/path/to/config`。
- 备份策略：每日/每周快照 `memberships.json` 与 `config.json`，审计日志按大小/时间轮转（后续可做）。
- 故障处理：发现 JSON 破损回退到最近快照并记录告警。

## 14. 里程碑与交付

- M1 架构与接口骨架：路由/鉴权/频控/审计框架、空白页面框架
- M2 数据与配置迁移、群管理/续费码页面完善、批量接口、导出
- M3 权限配置页与 API、热重载、权限扫描展示
- M4 多 Token 管理、IP 白名单、审计查询与导出、日志轮转
- M5 文案与乱码清理、完整测试与验收、使用手册与运维文档

## 15. 风险与缓解

- 数据并发写入损坏：采用原子写与基本锁；保留快照。
- Token 外泄：最小权限原则、快速吊销、审计可追踪。
- 旧命令冲突或权限误配：灰度上线、可快速回滚、明确默认值。
- 依赖缺失（apscheduler/fastapi 静态挂载）：保持容错，禁用控制台时不影响命令使用。

## 16. 待确认（产品/运维）

- 权限编辑范围是否覆盖全仓插件（建议是，以统一管理）。
- 退群默认策略为 `leave` 还是 `dismiss`。
- 是否启用续费码“多次使用/有效期”能力（默认开启/关闭）。
- Token 角色分级的粒度与默认策略（viewer/operator/admin）。

---

附：现有相关文件参考（便于实现对照）

- 续费命令与调度：`plugins/member_renewal/commands.py`
- Web 控制台与 API：`plugins/member_renewal/web_console.py`
- 数据与时间工具：`plugins/member_renewal/common.py`
- 统一权限：`config.py`、`perm.py`、`registry.py`、`config/permissions.json`
- 控制台前端：`plugins/member_renewal/web/console.html|.css|.js`

