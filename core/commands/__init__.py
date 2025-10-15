from __future__ import annotations

# Import all submodules under core.commands so that system commands
# are registered via import side effects, similar to how sub-plugins
# import their feature modules.

import importlib
import pkgutil
from nonebot.log import logger

# Always best-effort import: do not break on single module failure
_pkg_name = __name__
for _finder, _modname, _ispkg in pkgutil.walk_packages(__path__, _pkg_name + "."):
    try:
        importlib.import_module(_modname)
        try:
            logger.debug(f"core.commands: loaded {_modname}")
        except Exception:
            pass
    except Exception as e:
        try:
            logger.warning(f"core.commands: failed to import {_modname}: {e}")
        except Exception:
            pass
