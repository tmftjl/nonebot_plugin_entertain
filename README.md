nonebot-plugin-entertain
=======================

简介
- 娱乐功能合集，按子插件拆分于 `plugins/*`。
- 统一权限控制：全局、插件(top)、命令(commands) 三层。

环境
- Python 3.9+
- NoneBot2 + OneBot v11
- 依赖：`httpx`、`Pillow`、`aiofiles`、`aiohttp`

安装
- 将 `nonebot_plugin_entertain` 加入你的项目
- 加载：`nonebot.load_plugin("nonebot_plugin_entertain")`

目录结构
- 配置：`config/<plugin>/config.json`
- 权限：`config/permissions.json`
- 子插件：`plugins/<plugin>/`
  - `__init__.py` 业务逻辑
  - `data/` 持久数据（插件自管）
  - `resource/` 资源文件（插件自管）

权限模型（文件）
- 文件：`config/permissions.json`
- 结构：
  - 顶层：`enabled`、`whitelist`、`blacklist`
  - 每插件节点：
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

权限用法（统一）
- 使用包装器创建命令（会自动写入命令默认项到 `permissions.json`）：
```
from ...registry import Plugin

P = Plugin()  # 或 P = Plugin(enabled=True, level="all", scene="all")

cmd = P.on_regex(r"^#?<命令>$", name="command_name", priority=13, block=True)
```
- 非正则事件：`permission=P.permission()`（插件级）或 `permission=P.permission_cmd("name")`（命令级）。
- 不再支持旧的每插件目录 `permissions.json` 与旧的 `permission_for*`/`register_command` 用法。

配置管理（统一 API，独立文件）
- 每个插件各自使用 `config/<plugin>/config.json` 存储配置；文件不存在时写入默认值，存在则直接使用文件内容（不做默认值合并）。
- 统一方法（在插件内使用）：
```
from ...config import register_plugin_config, get_plugin_config, save_plugin_config, reload_plugin_config

# 注册（建议在模块导入时执行）
REG = register_plugin_config("<plugin>", DEFAULTS, validator=optional_validator)

# 读取/保存（使用缓存，避免频繁读盘）
cfg = REG.load()               # 或 get_plugin_config("<plugin>")
REG.save(cfg)                  # 或 save_plugin_config("<plugin>", cfg)

# 重载（读取磁盘并校验，返回 (ok, cfg, err)）
ok, cfg, err = reload_plugin_config("<plugin>")
```
- 配置目录选择顺序：环境变量 `NPE_CONFIG_DIR` > 包内 `config/`（可写）> 工作目录 `./config/`。

内置子插件（示例）
- 注册时间：`#注册时间 [@QQ 或 QQ号]`
- doro 结局：`#doro结局` / `#随机doro结局` / `#今日doro结局`
- 发病语录：`#发病语录`
- 点歌（musicshare）：`点歌 [qq|kugou|netease] 关键词` → 发送序号选择
- 今日运势：`#今日运势` / `#运势` / `#抽签`
- 开盒（box）：`盒 [@某人]` 或 `盒 <QQ>`
- 欢迎（welcome）：`#设置欢迎 ...` / `#查看欢迎` / `#开启欢迎` / `#关闭欢迎`
- 面板（panel）：`ww上传…面板` / `ww…面板图…` / `ww(刷新|更新)面板`
- DF 随机图：如 `#随机jk`、`#随机cos`、`#随机腿`（以代码正则为准）；图库安装/更新：`#DF安装图库` / `#DF更新图库`

注意
- 权限与配置均在内存中缓存，变更后可调用对应的重载函数（权限：`from ...perm import reload_permissions`）。
- 若运行环境无权写入包目录，请设置 `NPE_CONFIG_DIR` 指向可写路径。

