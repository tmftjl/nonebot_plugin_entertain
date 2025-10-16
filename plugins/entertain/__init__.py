from __future__ import annotations

# Ensure consolidated config/schema is registered once
from . import config as _config  # noqa: F401

# Aggregate commands from submodules so they register on import
from . import fortune  # noqa: F401
from . import doro  # noqa: F401
from . import musicshare  # noqa: F401
from . import sick  # noqa: F401
from . import reg_time  # noqa: F401
from . import box  # noqa: F401
from . import welcome  # noqa: F401
