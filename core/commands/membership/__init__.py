from __future__ import annotations

# 通过导入同目录下的 membership.py 触发命令注册
# NoneBot 加载到本包时会执行此导入，从而完成系统命令的注册。
# 仅执行导入以注册命令，不导出符号
from . import membership as _  # noqa: F401
