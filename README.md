nonebot-plugin-entertain
=======================

简介
- 娱乐功能合集，自动发现并加载 `plugins/*` 子插件。
- 统一权限控制：全局 → 插件(top) → 命令(commands)。

依赖
- Python 3.9+
- NoneBot2 + OneBot v11
- 第三方：`httpx`、`Pillow`、`aiofiles`、`aiohttp`

安装
- 将 `nonebot_plugin_entertain` 放入项目
- 在启动代码中加载：`nonebot.load_plugin("nonebot_plugin_entertain")`

目录结构
- 配置：`config/<plugin>/config.json`
- 权限：`config/permissions.json`
- 子插件：`plugins/<plugin>/`
  - `__init__.py`（插件逻辑）
  - `data/`（数据目录）
  - `resource/`（资源目录）

权限模型（单文件）
- 文件：`config/permissions.json`
- 结构：
  - 顶层：`enabled`、`whitelist`、`blacklist`
  - 每个插件一个键：
    - `<plugin>.top` 插件级默认
    - `<plugin>.commands.<name>` 命令级默认
- 示例：
```
{
  "enabled": true,
  "whitelist": { "users": [], "groups": [] },
  "blacklist": { "users": [], "groups": [] },
  "box": {
    "top": { "enabled": true, "level": "all", "scene": "all" },
    "commands": {
      "open": { "enabled": true, "level": "admin", "scene": "group" }
    }
  }
}
```

开发规范（极简）
- 使用包装器创建插件与命令（会自动向 `permissions.json` 写入默认项）：
```
from ...registry import Plugin

P = Plugin()  # 可选：P = Plugin(enabled=True, level="all", scene="all")

cmd = P.on_regex(
    r"^#?命令$",
    name="command_name",
    priority=13,
    block=True,
    # 可选：enabled/level/scene/wl_users/wl_groups/bl_users/bl_groups（写错直接抛错）
)
```
- 非正则事件：`permission=P.permission()`（插件级）或 `permission=P.permission_cmd("name")`（命令级）。
- 插件业务配置：`from ...config import register_plugin_config`，使用 `REG = register_plugin_config("<plugin>", DEFAULTS)`，`REG.load()` / `REG.save()`。

注意
- 不再支持每插件目录的 `permissions.json` 与旧的 `permission_for*`/`register_command` 用法。
- 传入的权限字段严格校验，非法值直接抛异常，避免“静默错配”。

已内置功能（示例）
- 注册时间：`#注册时间 [@QQ 或 QQ号]`
- doro 结局：`#doro结局` / `#随机doro结局` / `#今日doro结局`
- 发病语录：`#发病语录`
- 点歌：`#点歌 [qq|酷狗|网易云] 关键词` → 再发送序号选择
- 今日运势：`#今日运势`
- 开箱：`#箱 [@某人]` 或 `#箱 <QQ>`
- 欢迎：`#设置欢迎 ...` / `#查看欢迎` / `#开启欢迎` / `#关闭欢迎`
- 面板：`ww上传…面板…` / `ww…面板图…` / `ww(刷新|更新)?面板(刷新)?`
- DF 随机图：`#(随机|来点|整点)(jk|黑丝|白丝|cos|腿)`；列表：`#DF素材列表`
