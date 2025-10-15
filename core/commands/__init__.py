"""System command packages.

Imported via module-name loader to ensure plugin context. Import subpackages
here so their commands register during plugin load.
"""

from . import membership as _  # noqa: F401
