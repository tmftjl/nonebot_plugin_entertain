from __future__ import annotations

# Register submodules for useful features
from . import panel  # noqa: F401
from . import taffy  # noqa: F401

# Register display name for the 'useful' plugin
try:
    from ..core.api import set_plugin_display_name
    set_plugin_display_name("useful", "常用工具")
except Exception:
    pass
