nonebot-plugin-entertain
=======================

简介
- 娱乐功能合集，按子插件拆分于 `plugins/*`
- 统一权限控制：框架(top) -> 子插件(top) -> 命令(commands) 三层嵌套

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

权限模型（文件）
- 文件：`config/permissions.json`
- 结构（嵌套：框架 -> 子插件 -> 命令）：
  - `<framework>.top` 框架级默认项
  - `<framework>.sub_plugins.<sub>.top` 子插件级默认项
  - `<framework>.sub_plugins.<sub>.commands.<name>` 命令级默认项
- 标识符：`nonebot_plugin_entertain:<子插件>:<命令>`（三段式）
- 示例
```
{
  "nonebot_plugin_entertain": {
    "top": { "enabled": true, "level": "all", "scene": "all" },
    "sub_plugins": {
      "box": {
        "top": { "enabled": true, "level": "all", "scene": "all" },
        "commands": {
          "open": { "enabled": true, "level": "admin", "scene": "group" }
        }
      }
    }
  }
}
```

首次生成
- 首次运行若无 `config/permissions.json`，系统会扫描 `plugins/` 自动写入 框架/子插件/命令 条目，生成规范结构；后续不会在启动时自动迁移或重写该文件。

权限用法（统一）
- 使用包装器创建命令（会自动写入命令默认项至 `permissions.json`）：
```
from nonebot_plugin_entertain.registry import Plugin

P = Plugin()  # 或 P = Plugin(enabled=True, level="all", scene="all")

cmd = P.on_regex(r"^#?<命令>$", name="command_name", priority=13, block=True)
```
- 非正则事件：`permission=P.permission()`（子插件级）或 `permission=P.permission_cmd("name")`（命令级）
- 内部使用三段式标识 `nonebot_plugin_entertain:<子插件>:<命令>` 完成三级校验；命令层可对白名单进行精确豁免。

配置管理（统一 API，独立文件）
- 每个插件各自使用 `config/<plugin>/config.json` 存储配置；文件不存在时写入默认值，存在则直接使用文件内容（不做默认值合并）。
- 统一方法（在插件内使用）：
```
from nonebot_plugin_entertain.config import register_plugin_config, get_plugin_config, save_plugin_config, reload_plugin_config

# 注册（建议在模块导入时执行）
REG = register_plugin_config("<plugin>", DEFAULTS, validator=optional_validator)

# 读取/保存（使用缓存，避免频繁读盘）
cfg = REG.load()               # 或 get_plugin_config("<plugin>")
REG.save(cfg)                  # 或 save_plugin_config("<plugin>", cfg)

# 重载（读取磁盘并校验，返回 (ok, cfg, err)）
ok, cfg, err = reload_plugin_config("<plugin>")
```
- 配置目录选择顺序：环境变量 `NPE_CONFIG_DIR` > 包内 `config/`（可写）> 工作目录 `./config/`

内置子插件（示例）
- 注册时间：`#注册时间 [@QQ 或 QQ号]`
- doro 结局：`#doro结局` / `#随机doro结局` / `#今日doro结局`
- 发病语录：`#发病语录`
- 点歌（musicshare）：`点歌 [qq|kugou|netease] 关键词`（发送序号选择）
- 今日运势：`#今日运势` / `#运势` / `#抽签`
- 开盒（box）：`开盒 [@某人]` 或 `开盒 <QQ>`
- 欢迎（welcome）：`#设置欢迎 ...` / `#查看欢迎` / `#开启欢迎` / `#关闭欢迎`
- 面板（panel）：`ww上传…面板` / `ww…面板图…` / `ww(刷新|更新)面板`
- DF 随机图：如 `#随机jk`、`#随机cos`、`#随机腿`；图库安装/更新：`#DF安装图库` / `#DF更新图库`

注意
- 权限与配置均在内存中缓存，变更后可调用对应的重载函数（权限：`from nonebot_plugin_entertain.perm import reload_permissions`）。
- 若运行环境无权写入包目录，请设置 `NPE_CONFIG_DIR` 指向可写路径。
