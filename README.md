nonebot-plugin-entertain
=======================

简介
- 提供多个娱乐与实用功能，统一在框架内加载 `plugins/*`
- 统一的权限控制：全局(top) -> 子插件(top) -> 命令(commands)

环境
- Python 3.9+
- NoneBot2 + OneBot v11
- 依赖：`httpx`、`Pillow`、`aiofiles`、`aiohttp`

安装
- 安装 `nonebot_plugin_entertain` 到你的项目
- 在 NoneBot 中加载：`nonebot.load_plugin("nonebot_plugin_entertain")`

目录结构
- 配置：`config/<plugin>/config.json`
- 权限：`config/permissions.json`
- 子插件：`plugins/<plugin>/`
  - `__init__.py` 业务逻辑
  - `data/` 持久化数据（可选）
  - `resource/` 资源文件（可选）
- 系统功能：核心内置的会员续费等功能位于 `core/commands/membership/`

权限模型与文件
- 文件：`config/permissions.json`
- 结构：
  - `sub_plugins.top` 子插件全局默认项（影响所有外部子插件）
  - `sub_plugins.<sub>.top` 指定子插件默认项
  - `sub_plugins.<sub>.commands.<name>` 命令级默认项
  - `system.top` 系统内置模块默认项
  - `system.<main>.commands.<name>` 系统内置模块下的命令默认项
- 示例：
```
{
  "sub_plugins": {
    "top": { "enabled": true, "level": "all", "scene": "all" },
    "box": {
      "top": { "enabled": true, "level": "all", "scene": "all" },
      "commands": {
        "open": { "enabled": true, "level": "admin", "scene": "group" }
      }
    }
  },
  "system": {
    "top": { "enabled": true, "level": "all", "scene": "all" },
    "membership": {
      "commands": {
        "gen_code": { "enabled": true, "level": "superuser", "scene": "private" }
      }
    }
  }
}
```

首次运行
- 若不存在 `config/permissions.json`，系统会扫描 `plugins/` 及内置模块自动写入所需结构；后续不会自动覆盖该文件。

权限使用（统一方式）
- 装饰器注册命令时带上 name，便于写入 `permissions.json`：
```
from nonebot_plugin_entertain.registry import Plugin

P = Plugin(enabled=True, level="all", scene="all")

cmd = P.on_regex(r"^#?<示例>$", name="command_name", priority=13, block=True)
```
- 使用 `permission=P.permission()` 或 `permission=P.permission_cmd("name")` 控制权限。
- 系统内置模块可使用 `Plugin(name="membership", category="system")` 放入 system 分类并受 `system.top` 影响。

配置（统一 API 与文件）
- 系统整体配置：`config/system/config.json`；同时会生成 `config/system/config.js`（供前端直接引用 `window.NPE_CONFIG`）。
- 每个子插件仍可使用 `config/<plugin>/config.json` 保存独立配置。
- 配置目录优先级：环境变量 `NPE_CONFIG_DIR` > 包根目录 `config/`（可写）> 运行目录 `./config/`。

会员功能（内置）
- 命令：
  - 控制台登录：`控制台登录`（私聊，超级用户）
  - 生成续费码：`ww生成续费<数字><天|月|年>`（私聊，超级用户）
  - 使用续费码：`ww续费<数字><天|月|年>-<随机码>`（群聊）
  - 查询到期：`ww到期`（群聊）
  - 手动检查：`ww检查会员`（管理员）
- Web 控制台：`/membership/console`（需在系统配置中开启 `member_renewal_console_enable`）

编码与注释
- 全部源文件使用 UTF-8 编码
- 代码内注释已统一为中文
