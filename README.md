## 项目概述

这是 **nonebot-plugin-entertain**，一个通过 OneBot v11 适配器为 QQ 群提供娱乐和实用功能的 NoneBot2 插件集合。项目使用自定义框架，具有统一的权限和配置管理。

## 核心架构

### 插件加载系统

项目通过 NoneBot2 的 `load_plugins()` 加载两类插件：

1. **子插件** (`plugins/`)：外部娱乐功能（如运势、doro 抽卡、点歌等）
2. **系统命令** (`commands/`)：内置功能（如会员管理）

两者都在 `__init__.py` 启动时自动加载。

### 权限系统（三层架构）

权限通过单一文件管理：`config/permissions.json`

**子插件结构：**
- 全局层：`top` - 影响所有子插件
- 插件层：`sub_plugins.<插件名>.top` - 影响特定插件
- 命令层：`sub_plugins.<插件名>.commands.<命令名>` - 单命令控制

**系统命令结构：**
- 扁平结构：`system.commands.<命令名>` - 不受全局 `top` 影响

每个条目包含：
- `enabled`：布尔开关
- `level`：`"all"` | `"member"` | `"admin"` | `"owner"` | `"bot_admin"` | `"superuser"`
- `scene`：`"all"` | `"group"` | `"private"`
- `whitelist`：`{users: [], groups: []}`
- `blacklist`：`{users: [], groups: []}`

**权限评估顺序：**
1. 白名单/黑名单（立即允许/拒绝）
2. 场景检查（群聊 vs 私聊）
3. 等级检查（用户角色）

权限检查级联：全局 → 插件 → 命令（每层可拒绝但不能覆盖拒绝）。

### 注册模式（`core/framework/registry.py`）

**创建插件（代码中使用枚举）：**
```python
from nonebot_plugin_entertain.core.framework.registry import Plugin
from nonebot_plugin_entertain.core.framework.perm import PermLevel

P = Plugin(enabled=True, level=PermLevel.LOW, scene="all")
```

- 从模块路径自动检测插件名（位于 `plugins/<名称>/` 下）
- `category="sub"` 用于子插件，`"system"` 用于内置命令
- 首次运行时自动将默认值写入 `permissions.json`

**注册命令：**
```python
cmd = P.on_regex(
    r"^#?<模式>$",
    name="command_name",  # 必需，用于 permissions.json 跟踪
    priority=13,
    block=True
)
```

- `name` 参数是必需的 - 用作 permissions.json 中的键
- 如果未明确提供，自动绑定 `permission=P.permission_cmd(name)`
- 附加日志处理器以跟踪命令触发

### 配置系统（`core/framework/config.py`）

**配置文件位置（优先级顺序）：**
1. 环境变量：`NPE_CONFIG_DIR`
2. 包根目录：`<package>/config/`（可写，首选）
3. 工作目录：`./config/`

**单插件配置：**
```python
from nonebot_plugin_entertain.core.framework.config import register_plugin_config

cfg_proxy = register_plugin_config("plugin_name", defaults={...})
cfg = cfg_proxy.load()  # 自动从默认值填充缺失键
cfg_proxy.save(new_cfg)
```

**命名空间配置（共享文件）：**
```python
from nonebot_plugin_entertain.core.framework.config import register_namespaced_config

proxy = register_namespaced_config("entertain", "fortune", defaults={...})
cfg = proxy.load()  # 加载 entertain/config.json -> fortune 部分
```

**系统配置：** `config/system/config.json` 通过 `core/system_config.py` 管理

**配置管理函数：**
- `bootstrap_configs()`：启动时调用以确保文件存在
- `upsert_plugin_defaults()`：更新插件级权限默认值
- `upsert_command_defaults()`：更新命令级默认值（子插件）
- `upsert_system_command_defaults()`：更新命令级默认值（系统）

### 权限辅助函数（`core/framework/perm.py`）

- `permission_for_plugin(name, category="sub")`：插件级权限
- `permission_for_cmd(plugin, command, category="sub")`：命令级权限
- `reload_permissions()`：强制从磁盘重新加载 + 使缓存失效

**运行时权限检查：**
- 权限缓存在 `KeyValueCache` 中，无 TTL（仅手动失效）
- 更新 `permissions.json` 后调用 `reload_permissions()` 以应用更改

## 主要功能

### 会员系统（`commands/membership/`）

内置群组会员管理，包含：
- 续费码生成，可配置最大使用次数和过期时间
- 每个群组的到期跟踪
- 定时检查（如果安装了 `nonebot-plugin-apscheduler`）
- Web 控制台位于 `/member_renewal/console`（启用时）

**命令：**
- `控制台登录`：获取 web 控制台访问链接（超级用户，私聊）
- `ww生成续费<数字><天|月|年>`：生成续费码
- `ww续费<code>`：对群组应用续费码
- `ww到期`：检查到期状态
- `ww检查会员`：手动会员检查（管理员）

### Web 控制台（`console/server.py`）

基于 FastAPI 的管理界面：
- 群组会员管理（延长、提醒、退出）
- 续费码生成和列表
- 系统配置编辑器
- 权限编辑器，带实时重载
- 调度器控制

通过系统配置中的 `member_renewal_console_enable: true` 启用。

## 开发命令

**测试插件：**
这是一个 NoneBot2 插件，需要在机器人实例中加载。没有独立的测试套件。测试方法：
1. 在 NoneBot2 项目中安装：`pip install -e .` 或通过 `nonebot.load_plugin()` 加载
2. 配置 bot.py 以加载插件
3. 运行机器人并通过 OneBot v11 客户端（如 go-cqhttp）交互

**依赖项：**
通过以下方式安装：`pip install -r requirements.txt`

核心依赖：
- `httpx>=0.24`、`aiohttp>=3.8` - HTTP 客户端
- `aiofiles>=23.0` - 异步文件 I/O
- `Pillow>=9.2` - 图像处理
- `pydantic>=2` - 数据验证（NoneBot2 v11 要求）

**编码：**
所有源文件使用 UTF-8 编码。注释和消息使用中文。

## 常见模式

### 添加新命令（代码中使用枚举）

1. 在插件的 `__init__.py` 中创建命令：
```python
from nonebot_plugin_entertain.core.framework.registry import Plugin
from nonebot_plugin_entertain.core.framework.perm import PermLevel

P = Plugin(enabled=True, level=PermLevel.LOW, scene="all")

cmd = P.on_regex(r"^#?<模式>$", name="my_command", priority=13, block=True)

@cmd.handle()
async def handle_cmd(event: GroupMessageEvent):
    # 实现
    pass
```

2. 框架自动：
   - 在 `permissions.json` 中注册命令
   - 应用权限检查
   - 记录命令触发

### 配置管理

配置在首次加载时自动从默认值填充并持久化。修改默认值需要删除配置文件或手动合并。

### 处理权限更改

修改 `permissions.json` 后：
```python
from nonebot_plugin_entertain.core.framework.perm import reload_permissions
reload_permissions()  # 无需重启即应用更改
```

或使用 web 控制台的权限编辑器，它会自动重载。

## 文件组织

- `__init__.py`：入口点，加载子插件和系统命令
- `core/framework/`：核心抽象（注册表、权限、配置、缓存）
- `core/api.py`：共享 API 工具
- `core/system_config.py`：系统范围配置助手
- `plugins/`：子插件实现（每个在自己的目录中）
- `commands/`：系统命令（内置功能）
- `console/`：Web 管理界面
- `config/`：运行时配置文件（gitignored，自动生成）

## 重要说明

- **首次运行行为：** 首次加载时，通过扫描所有插件的命令自动生成 `permissions.json`。此文件随后被保留 - 框架不会覆盖手动编辑。
- **权限继承：** 任何级别（全局 → 插件 → 命令）的拒绝都不能被更低级别覆盖。
- **系统命令隔离：** `system` 类别中的命令不受全局 `top` 权限影响 - 它们具有扁平结构和独立默认值。
- **缓存失效：** 权限缓存没有 TTL，一直持续到调用 `reload_permissions()` 为止。
