nonebot-plugin-entertain
=======================

娱乐功能合集，将多种功能统一到一个 NoneBot2 插件包内，集中式配置与权限控制。

包含功能（位于 `plugins/*` 子模块）
- 注册时间查询：`#注册时间 [@QQ 或 QQ号]`（`plugins/reg_time`）
- 每日 doro 结局：`#doro结局` / `#随机doro结局` / `#今日doro结局`（`plugins/doro`）
- 发病语录：`#发病语录`（`plugins/sick`）
- 点歌：点歌 + 选曲（`plugins/musicshare`）
- 今日运势：（`plugins/fortune`）
- 开盒：`开盒 [@QQ 或 QQ号]`（`plugins/box`）
- 群欢迎：设置/查看/开关欢迎（`plugins/welcome`，默认仅群管理可用，图片持久化为 base64）
- 塔菲流量查询：`#查询流量 [用户名]`（`plugins/taffy`，默认仅超管可用）
- 面板提示：`ww上传…面板…`、`ww…面板图…`、`ww(刷新|更新)?面板(刷新)?`（`plugins/panel`）

安装
1) 需要 `nonebot2` 与 OneBot v11 适配器；依赖 `httpx`、`Pillow`、`aiofiles`、`aiohttp` 等（三方依赖按需安装）。
2) 将目录 `nonebot_plugin_entertain` 放入机器人项目（或打包为模块安装）。
3) 在机器人入口加载：`nonebot.load_plugin("nonebot_plugin_entertain")`。

配置（环境变量 /.env）
- 功能开关（默认 true）
  - `ENTERTAIN_ENABLE_REG_TIME=true|false`
  - `ENTERTAIN_ENABLE_DORO=true|false`
  - `ENTERTAIN_ENABLE_SICK=true|false`
  - `ENTERTAIN_ENABLE_MUSICSHARE=true|false`
  - `ENTERTAIN_ENABLE_FORTUNE=true|false`
  - `ENTERTAIN_ENABLE_BOX=true|false`
  - `ENTERTAIN_ENABLE_WELCOME=true|false`
  - `ENTERTAIN_ENABLE_TAFFY=true|false`
  - `ENTERTAIN_ENABLE_PANEL=true|false`

- 权限控制（集中式），默认 all
  - `ENTERTAIN_PERM_DEFAULT=all|admin|superuser`
  - `ENTERTAIN_PERM_REG_TIME=all|admin|superuser`
  - `ENTERTAIN_PERM_DORO=all|admin|superuser`
  - `ENTERTAIN_PERM_SICK=all|admin|superuser`
  - `ENTERTAIN_PERM_MUSICSHARE=all|admin|superuser`
  - `ENTERTAIN_PERM_FORTUNE=all|admin|superuser`
  - `ENTERTAIN_PERM_BOX=all|admin|superuser`
  - `ENTERTAIN_PERM_WELCOME=all|admin|superuser`
  - `ENTERTAIN_PERM_WELCOME_SET=admin`（默认）
  - `ENTERTAIN_PERM_WELCOME_CLEAR=admin`（默认）
  - 也可通过 `config/permissions.json` 细化各功能的 `scene`（all/group/private）、白名单/黑名单。

- 其他
  - `ENTERTAIN_QQ_REG_TIME_API_KEY=xxxx`（可选，注册时间查询使用）

说明
- 所有功能均为异步并调用外部 API，注意超时与异常兜底。
- 权限级别：
  - `all` 所有人可用
  - `admin` 群管理员/群主（群聊事件）或超管
  - `superuser` NoneBot 超级用户
- 欢迎语：
  - 设置：`设置欢迎 <任意格式消息>`，支持文字/图片/@ 等；占位符 `{at}`（新成员@）、`{qq}`（新成员QQ）。
  - 查看/开关：`查看欢迎`、`开启欢迎`、`关闭欢迎`
  - 欢迎消息持久化保存到 `nonebot_plugin_entertain/data/welcome/welcome.json`，图片自动转为 base64 存储，避免 URL 过期。

目录与持久化
- 数据：`nonebot_plugin_entertain/data/<子目录>/`（例如 `data/fortune`、`data/welcome`）
- 资源：`nonebot_plugin_entertain/resource/`
- 配置：`nonebot_plugin_entertain/config/`

插件编写指南
- 目录结构
  - 新建 `plugins/<your_plugin>/__init__.py`，在其中注册命令（matcher）。
  - 如需按开关加载，在 `config.py` 添加 `entertain_enable_xxx: bool`，并在包 `__init__.py` 里用 `_conditional_import(".plugins.xxx")` 挂载。
- 注册命令
  - 推荐使用 `on_regex`/`on_message` 等；设置 `block`/`priority` 与现有插件风格一致。
  - 权限请使用集中式方法：
    - 插件级：`permission=permission_for_plugin("your_plugin")`
    - 命令级（同时受插件级约束）：`permission=permission_for_cmd("your_plugin", "your_command")`
- 权限配置
  - 权限 JSON 支持三级：全局 → 插件（plugins）→ 命令（commands）。兼容旧版 `features`（逐条目）。
  - 示例片段：
    ```json
    {
      "enabled": true,
      "whitelist": { "users": [], "groups": [] },
      "blacklist": { "users": [], "groups": [] },
      "plugins": {
        "welcome": { "enabled": true, "level": "admin", "scene": "group" },
        "taffy": { "enabled": true, "level": "superuser", "scene": "all" }
      },
      "commands": {
        "welcome": {
          "show": { "enabled": true, "level": "admin", "scene": "group" },
          "set": { "enabled": true, "level": "admin", "scene": "group" },
          "enable": { "enabled": true, "level": "admin", "scene": "group" },
          "disable": { "enabled": true, "level": "admin", "scene": "group" }
        },
        "taffy": {
          "query": { "enabled": true, "level": "superuser", "scene": "all" }
        }
      }
    }
    ```
  - 字段含义：
    - `enabled`：开关；`level`：`all|admin|owner|superuser`；`scene`：`all|group|private`
    - 支持 `whitelist/blacklist`（`users`/`groups`），白名单优先于黑名单。
  - 兼容旧版：若仍在 `features` 中配置，仍会生效；当与插件/命令级同时存在时，插件/命令级优先生效且更严格的限制会生效。
- 数据与配置读写
  - 使用工具函数：
    - `from ...utils import data_dir, config_dir, resource_dir`
    - `data_dir("my")` 返回并创建 `data/my/` 目录。
  - 读写 JSON 建议使用 UTF-8 并捕获异常，避免影响消息处理。
- 网络请求
  - 推荐 `httpx.AsyncClient(timeout=...)`；对 `HTTPError`、解析失败等进行友好提示。
- 图片等资源
  - 若需要持久化图片，建议参考 `plugins/welcome`：将图片转为 `base64://...` 存储，避免外链失效。
- 示例骨架

```python
from nonebot import on_regex
from nonebot.matcher import Matcher
from nonebot.adapters.onebot.v11 import MessageEvent
from ...perm import permission_for_cmd
from ...utils import data_dir

my_cmd = on_regex(r"^#?我的功能(.*)$", block=True, priority=100, permission=permission_for_cmd("my_plugin", "my_command"))

@my_cmd.handle()
async def _(matcher: Matcher, event: MessageEvent):
    # TODO: your logic
    await matcher.finish("OK")
```

发布与调试
- 子插件无需单独 PluginMetadata，只需注册 matcher 即可。
- 若新增了配置项或权限项，请同步更新 `config.py`、`__init__.py` 与 `config/permissions.json`。
