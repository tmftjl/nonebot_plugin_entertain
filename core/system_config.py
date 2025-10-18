from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

from .framework.config import register_plugin_config, register_plugin_schema
from .api import set_plugin_display_name
from .framework.utils import config_dir


# 系统级默认配置（包含会员相关项）
SYSTEM_DEFAULTS: Dict[str, Any] = {
    # 定时与时区
    "member_renewal_timezone": "Asia/Shanghai",
    "member_renewal_enable_scheduler": True,
    "member_renewal_schedule_hour": 12,
    "member_renewal_schedule_minute": 0,
    "member_renewal_schedule_second": 0,
    # 提醒行为
    "member_renewal_reminder_days_before": 7,
    "member_renewal_daily_remind_once": True,
    "member_renewal_remind_template": "本群会员将在 {days} 天后到期（{expiry}），请尽快联系管理员续费",
    "member_renewal_soon_threshold_days": 7,
    # 到期处理
    "member_renewal_auto_leave_on_expire": True,
    "member_renewal_leave_mode": "leave",
    # 控制台/网页
    "member_renewal_console_enable": True,
    "member_renewal_console_host": "http://localhost:8080",
    # 可选：统计服务 API 地址（供网页端转发）
    "member_renewal_stats_api_url": "http://127.0.0.1:8000",
    # 续费码生成
    "member_renewal_code_prefix": "ww续费",
    "member_renewal_code_random_len": 6,  # 随机码长度（十六进制字符）
    "member_renewal_code_expire_days": 0,  # 过期天数（0 表示永久）
    "member_renewal_code_max_use": 1,
}


# 存储为系统级配置：config/system/config.json
_REG = register_plugin_config("system", SYSTEM_DEFAULTS, filename="config.json")
try:
    set_plugin_display_name("system", "系统配置")
except Exception:
    pass

# 为前端提供的 Schema（Plan A）：描述字段中文名、说明、类型及 UI 提示
SYSTEM_SCHEMA: Dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "title": "系统配置",
    "properties": {
        # 定时与时区
        "member_renewal_timezone": {
            "type": "string",
            "title": "时区",
            "description": "用于会员到期计算与定时任务触发的时区（IANA 时区名）",
            "default": "Asia/Shanghai",
            "examples": ["Asia/Shanghai", "UTC"],
            "x-group": "定时与时区",
            "x-order": 1
        },
        "member_renewal_enable_scheduler": {
            "type": "boolean",
            "title": "启用定时任务",
            "description": "开启后将按设定时间每日执行到期检查与提醒（需要 nonebot_plugin_apscheduler）",
            "default": True,
            "x-group": "定时与时区",
            "x-order": 2
        },
        "member_renewal_schedule_hour": {
            "type": "integer",
            "title": "执行小时",
            "description": "每日任务触发的小时（0-23）",
            "default": 12,
            "minimum": 0,
            "maximum": 23,
            "x-group": "定时与时区",
            "x-order": 3
        },
        "member_renewal_schedule_minute": {
            "type": "integer",
            "title": "执行分钟",
            "description": "每日任务触发的分钟（0-59）",
            "default": 0,
            "minimum": 0,
            "maximum": 59,
            "x-group": "定时与时区",
            "x-order": 4
        },
        "member_renewal_schedule_second": {
            "type": "integer",
            "title": "执行秒",
            "description": "每日任务触发的秒（0-59）",
            "default": 0,
            "minimum": 0,
            "maximum": 59,
            "x-group": "定时与时区",
            "x-order": 5
        },

        # 提醒行为
        "member_renewal_reminder_days_before": {
            "type": "integer",
            "title": "提前提醒天数",
            "description": "到期前 N 天开始提醒",
            "default": 7,
            "minimum": 0,
            "x-group": "提醒行为",
            "x-order": 10
        },
        "member_renewal_daily_remind_once": {
            "type": "boolean",
            "title": "每日仅提醒一次",
            "description": "开启后在同一天内对同一群聊仅提醒一次",
            "default": True,
            "x-group": "提醒行为",
            "x-order": 11
        },
        "member_renewal_remind_template": {
            "type": "string",
            "title": "提醒模板",
            "description": "提醒消息模板，支持 {days}/{expiry} 占位符",
            "default": "本群会员将在 {days} 天后到期（{expiry}），请尽快联系管理员续费",
            "x-group": "提醒行为",
            "x-widget": "textarea",
            "x-order": 13
        },
        "member_renewal_soon_threshold_days": {
            "type": "integer",
            "title": "临近到期阈值(天)",
            "description": "小于等于该天数时视为“即将到期”",
            "default": 7,
            "minimum": 0,
            "x-group": "提醒行为",
            "x-order": 14
        },

        # 到期处理
        "member_renewal_auto_leave_on_expire": {
            "type": "boolean",
            "title": "到期自动退群",
            "description": "到期后自动执行退群动作（需 Bot 权限）",
            "default": True,
            "x-group": "到期处理",
            "x-order": 20
        },
        "member_renewal_leave_mode": {
            "type": "string",
            "title": "退群模式",
            "description": "leave=主动退出，dismiss=解散（若有权限）",
            "enum": ["leave", "dismiss"],
            "default": "leave",
            "x-group": "到期处理",
            "x-order": 21
        },
        "member_renewal_console_enable": {
            "type": "boolean",
            "title": "启用Web控制台",
            "description": "挂载 /member_renewal 控制台页面与接口",
            "default": True,
            "x-group": "控制台",
            "x-order": 32
        },
        "member_renewal_console_host": {
            "type": "string",
            "title": "控制台访问地址",
            "description": "控制台的完整URL地址,用于生成二维码等",
            "default": "http://localhost:8080",
            "x-group": "控制台",
            "x-order": 33
        },
        "member_renewal_stats_api_url": {
            "type": "string",
            "title": "统计API地址",
            "description": "前端转发的统计服务 API 根地址",
            "default": "http://127.0.0.1:8000",
            "x-group": "控制台",
            "x-order": 34
        },

        # 续费码生成
        "member_renewal_code_prefix": {
            "type": "string",
            "title": "续费码前缀",
            "description": "生成续费码时使用的文本前缀",
            "default": "ww续费",
            "x-group": "续费码",
            "x-order": 40
        },
        "member_renewal_code_random_len": {
            "type": "integer",
            "title": "随机码长度",
            "description": "续费码随机部分长度（十六进制字符数）",
            "default": 6,
            "minimum": 1,
            "x-group": "续费码",
            "x-order": 41
        },
        "member_renewal_code_expire_days": {
            "type": "integer",
            "title": "过期天数",
            "description": "生成后的续费码有效天数，0 表示永久有效",
            "default": 0,
            "minimum": 0,
            "x-group": "续费码",
            "x-order": 42
        },
        "member_renewal_code_max_use": {
            "type": "integer",
            "title": "最大使用次数",
            "description": "单个续费码可被使用的最大次数",
            "default": 1,
            "minimum": 1,
            "x-group": "续费码",
            "x-order": 43
        },
    }
}

# 注册 system 的 Schema 供前端读取
try:
    register_plugin_schema("system", SYSTEM_SCHEMA)
except Exception:
    # 容错：不影响配置读写
    pass


def load_cfg() -> Dict[str, Any]:
    return _REG.load()


def save_cfg(cfg: Dict[str, Any]) -> None:
    _REG.save(cfg or {})


def config_path() -> Path:
    return _REG.path
