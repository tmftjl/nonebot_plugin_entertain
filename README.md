# nonebot-plugin-entertain 使用与开发文档

nonebot-plugin-entertain 是基于 NoneBot2（OneBot v11）的多功能插件合集，提供娱乐、群管、帮助图、AI 对话、会员到期管理与 Web 控制台等能力。项目在权限与配置上做了统一封装，适合规模化维护与二次开发。

## 功能总览

- 娱乐（plugins/entertain）
  - 今日运势、doro 抽卡、点歌（QQ/网易云/酷狗）、每日打卡、欢迎图、注册时间查询、表情盒子等。
- 群管（plugins/group_admin）
  - 禁言/解禁/全体禁言、撤回、精华、设/撤管理员、踢人拉黑、违禁词（开关、增删清、拦截动作）。
- 帮助图（plugins/help）
  - Playwright 渲染帮助图，失败时回退到 PIL 文本图。
- AI 对话（plugins/ai_chat）
  - 多模态聊天（文本/图片）、工具调用（Function Calling + MCP）、会话与人格系统、TTS 语音、摘要记忆、主动回复。
- 会员系统与控制台（commands/membership + console）
  - 到期提醒/自动退群、续费码生成与兑换、定时任务、FastAPI Web 控制台（/member_renewal）。
- DF（plugins/df）
  - 戳一戳图库管理（Git 克隆/更新）、随机图片、转发给主人等。

## 目录结构与核心组件

- 核心（core/）
  - `core/api.py`：对外统一 API（Plugin、权限、配置、缓存、目录等）。
  - `core/framework/`：注册器（registry）、权限（perm）、配置（config）、缓存（cache）、工具（utils）。
  - `core/system_config.py`：系统级配置项（控制台/调度/续费码等）及 JSON Schema。
  - `core/http.py`：共享 httpx AsyncClient、统一超时与重试。
  - `core/__init__.py`：启动挂载 Web 控制台、关闭共享 HTTP 客户端。
- 子插件（plugins/）：按域拆分（entertain / group_admin / help / ai_chat / df）。
- 系统命令（commands/）：例如会员相关系统命令。
- Web 控制台（console/）：路由、静态资源与页面。
- 数据库（db/）：SQLModel + SQLite（默认 `data/entertain.db`）。
- 运行目录
  - 配置：`config/`（支持 `NPE_CONFIG_DIR` 环境变量覆盖目录）
  - 数据：`data/<plugin>/`
  - 资源：`plugins/<plugin>/resource/`

## 安装与环境

1) 安装依赖

```bash
pip install -r requirements.txt
# 可选：帮助图用 Playwright
python -m playwright install chromium
```

2) 环境依赖（可选/按需）

- OneBot v11 连接端：如 go-cqhttp
- FFmpeg：点歌音频转码，需在系统 PATH 中
- Git：DF 图库 `git clone/pull`

3) 集成到 NoneBot 项目

在你的 NoneBot 项目中加载本插件：

```python
nonebot.load_plugin("nonebot_plugin_entertain")
```

首次启动将自动：
- 创建/补齐 `config/permissions.json`
- 写入各插件默认配置（缺失时）
- 初始化 SQLite 数据库（`data/entertain.db`）
- 挂载 Web 控制台（若启用）

## 权限与配置

### 权限（config/permissions.json）

- 结构：
  - `top`（全局）→ `sub_plugins.<插件>.top` → `sub_plugins.<插件>.commands.<命令>`
- 字段：
  - `enabled`、`level`（all/member/admin/owner/bot_admin/superuser）、`scene`（all/group/private）、`whitelist/blacklist`（users/groups）
- 检查顺序：开关 → 白/黑名单 → 场景（群/私）→ 角色等级
- 修改后热生效：调用 `reload_permissions()`（控制台保存后会自动触发）

### 插件配置

- 通过 `core/framework/config.py` 注册与管理，默认值写入磁盘，缺失键自动补齐并回写。
- 支持命名空间配置（同一文件多段配置）。
- 控制台可批量查看与保存，并统一热重载。

### 系统配置

- `config/system/config.json`：控制台开关、调度时间、续费码规则等。
- 提供 JSON Schema，便于前端渲染表单与校验。

## Web 控制台

- 前缀：`/member_renewal`
- 入口：`/member_renewal/console`（需 token）
- 启用：系统配置 `member_renewal_console_enable: true`
- 获取访问地址：私聊发送 `今汐登录`（SUPERUSER）获取带 token 的 URL（默认指向 `member_renewal_console_host`）。
- 能力：会员编辑、续费码生成、权限与插件配置的查看与保存（保存后自动热重载）。

## 常用命令速查（示例）

- 控制台/会员
  - `今汐登录`（私聊，超管）→ 控制台地址
  - `ww生成续费<数字><天|月|年>`（超管，私聊）
  - `ww续费<数字><天|月|年>-<随机码>`（群聊）
  - `ww到期` 查看本群状态
- AI 对话
  - `#清空会话`、`#会话信息`、`#开启AI`、`#关闭AI`
  - `#人格列表`、`#切换人格 <key>`
  - `#服务商列表`、`#切换服务商 <name>`
  - `#工具列表`、`#开启工具 <name>`、`#关闭工具 <name>`
  - `#开启TTS`、`#关闭TTS`、`#重载AI配置`
- 娱乐与群管
  - `#点歌 关键词`、`#1`（选择第 1 首）
  - `#十连doro抽卡`、`#百连doro抽卡`
  - `#今日运势`、`#签`、`#注册时间 [@或QQ号]`
  - `#开启违禁词`、`#添加违禁词 <词>`、`#违禁词列表`、`#关闭违禁词`
- DF 图库
  - `#DF安装图库`、`#DF更新图库`、`#DF强制更新图库`

## 开发指引

### 注册命令（统一权限与命名）

```python
from nonebot_plugin_entertain.core.api import Plugin
from nonebot_plugin_entertain.core.framework.perm import PermLevel, PermScene

P = Plugin(name="your_plugin", display_name="中文名", enabled=True, level=PermLevel.LOW, scene=PermScene.ALL)
cmd = P.on_regex(r"^#你的命令$", name="internal_name", display_name="中文显示名", priority=5, block=True)

@cmd.handle()
async def _(event):
    ...
```

### 配置管理

```python
from nonebot_plugin_entertain.core.api import (
    register_plugin_config, register_namespaced_config, register_reload_callback,
)

proxy = register_plugin_config("plugin", defaults={"k": 1})
cfg = proxy.load()
proxy.save({"k": 2})

ns = register_namespaced_config("plugin", "section", defaults={"a": 1})
sec_cfg = ns.load()

def on_reload():
    pass
register_reload_callback("plugin", on_reload)
```

### 目录与工具

```python
from nonebot_plugin_entertain.core.api import (
  plugin_resource_dir, plugin_data_dir, config_dir,
)
res = plugin_resource_dir("plugin")
data = plugin_data_dir("plugin")
cfg_dir = config_dir("plugin")
```

### HTTP 与缓存

```python
from nonebot_plugin_entertain.core.http import get_shared_async_client
from nonebot_plugin_entertain.core.constants import DEFAULT_HTTP_TIMEOUT

client = await get_shared_async_client()
r = await client.get("https://example.com", timeout=DEFAULT_HTTP_TIMEOUT)
```