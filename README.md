nonebot-plugin-entertain
=======================

简介
- 娱乐功能合集，按子插件拆分于 `plugins/*`
- 统一权限控制：全局(top) -> 子插件(top) -> 命令(commands) 三层结构

环境
- Python 3.9+
- NoneBot2 + OneBot v11
- 依赖：`httpx`、`Pillow`、`aiofiles`、`aiohttp`

安装
- 将 `nonebot_plugin_entertain` 加入项目
- 加载：`nonebot.load_plugin("nonebot_plugin_entertain")`

目录结构
- 配置：`config/<plugin>/config.json`
- 权限：`config/permissions.json`
- 子插件：`plugins/<plugin>/`
  - `__init__.py` 业务逻辑
  - `data/` 持久数据（插件自管）
  - `resource/` 资源文件（插件自管）
- 内置功能：`membership/`（会员续费，迁移为框架内置模块）

权限模型（文件）
- 文件：`config/permissions.json`
- 结构（嵌套）：
  - `sub_plugins.top` 子插件全局默认项（影响所有外部子插件）
  - `sub_plugins.<sub>.top` 子插件级默认项
  - `sub_plugins.<sub>.commands.<name>` 命令级默认项
  - `system.top` 系统命令区域（不受 root top 影响）
  - `system.<main>.commands.<name>` 内置插件命令级默认项
- 标识符：内部使用 `plugin:command`（命令级）或 `plugin`（插件级）
- 示例
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

首次生成
- 首次运行若无 `config/permissions.json`，系统会扫描 `plugins/` 以及框架内置模块（例如 `membership/`）自动写入 全局/子插件/命令 条目；后续不会在启动时自动迁移或重写该文件。

权限用法（统一）
- 使用包装器创建命令（会自动写入命令默认项至 `permissions.json`）：
```
from nonebot_plugin_entertain.registry import Plugin

P = Plugin()  # 或 P = Plugin(enabled=True, level="all", scene="all")

cmd = P.on_regex(r"^#?<命令>$", name="command_name", priority=13, block=True)
```
- 非正则事件：`permission=P.permission()`（子插件级）或 `permission=P.permission_cmd("name")`（命令级）
- 内置插件请使用：`Plugin(name="membership", category="system")`，其命令默认项写入 `system` 分类并受 `system.top` 影响。

配置管理（统一 API，独立文件）
- 每个插件各自使用 `config/<plugin>/config.json` 存储配置；文件不存在时写入默认值，存在则直接使用文件内容（不做默认值合并）。
- 统一方法（在插件内使用）：
```
from nonebot_plugin_entertain.config import register_plugin_config, get_plugin_config, save_plugin_config, reload_plugin_config

REG = register_plugin_config("<plugin>", DEFAULTS, validator=optional_validator)

cfg = REG.load()               # 或 get_plugin_config("<plugin>")
REG.save(cfg)                  # 或 save_plugin_config("<plugin>", cfg)

ok, cfg, err = reload_plugin_config("<plugin>")
```
- 配置目录选择顺序：环境变量 `NPE_CONFIG_DIR` > 包内 `config/`（可写）> 工作目录 `./config/`

内置示例功能
- 注册时间：`#注册时间 [@QQ 或 QQ号]`
- doro 结局：`#doro结局` / `#随机doro结局` / `#今日doro结局`
- 发病语录：`#发病语录`
- 点歌（musicshare）：`点歌 [qq|kugou|netease] 关键词`（发送序号选择）
- 今日运势：`#今日运势` / `#运势` / `#抽签`
- 开盒（box）：`开盒[@某人]` 或 `开盒<QQ>`
- 欢迎（welcome）：`#设置欢迎 ...` / `#查看欢迎` / `#开启欢迎` / `#关闭欢迎`
- 面板（panel）：`ww上传…面板` / `ww…面板图…` / `ww(刷新|更新)面板`
- DF 随机图：如 `#随机jk`、`#随机cos`、`#随机腿`；图库安装/更新：`#DF安装图库` / `#DF更新图库`

注意
- 权限与配置均在内存中缓存，变更后可调用对应的重载函数（权限：`from nonebot_plugin_entertain.perm import reload_permissions`）。
- 若运行环境无权写入包目录，请设置 `NPE_CONFIG_DIR` 指向可写路径。

Membership 迁移说明
- 功能从子插件迁移为框架内置模块，代码位于 `membership/`。
- 配置文件：`config/entertain/config.json 中的 membership 节点`（首次运行会写入默认配置）。
- 权限配置：出现在 `permissions.json` 的 `system.membership` 中，命令名如 `gen_code`、`redeem` 等，受 `system.top` 统一控制。
- Web 控制台路由：`/membership/*`（可在配置中开启）。


