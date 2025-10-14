from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

from .framework.config import register_plugin_config
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
    "member_renewal_contact_suffix": " 咨询/加入交流QQ群：757463664 联系群管",
    "member_renewal_remind_template": "本群会员将在 {days} 天后到期（{expiry}），请尽快联系管理员续费",
    "member_renewal_soon_threshold_days": 7,
    # 到期处理
    "member_renewal_auto_leave_on_expire": True,
    "member_renewal_leave_mode": "leave",
    "member_renewal_default_bot_id": "",
    # 控制台可用 Bot 列表：[{"bot_id": str, "bot_name": str?}]
    "member_renewal_bots": [],
    # 控制台/网页
    "member_renewal_console_enable": True,
    # 可选：统计服务 API 地址（供网页端转发）
    "member_renewal_stats_api_url": "http://127.0.0.1:8000",
    # 续费码生成
    "member_renewal_code_prefix": "ww续费",
    "member_renewal_code_random_len": 6,  # 随机码长度（十六进制字符）
    "member_renewal_code_expire_days": 0,  # 过期天数（0 表示永久）
    "member_renewal_code_max_use": 1,
    # 导出字段
    "member_renewal_export_fields": ["group_id", "expiry", "status", "last_renewed_by"],
}


# 存储为系统级配置：config/system/config.json
_REG = register_plugin_config("system", SYSTEM_DEFAULTS, filename="config.json")


def load_cfg() -> Dict[str, Any]:
    return _REG.load()


def save_cfg(cfg: Dict[str, Any]) -> None:
    _REG.save(cfg or {})


def config_path() -> Path:
    return _REG.path
