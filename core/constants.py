from __future__ import annotations

"""Project-wide static constants.

Values here represent rarely changed, global defaults that should not live
in per-plugin configuration files. Update here if needed across the project.
"""

# Unified default HTTP timeout (seconds) for outbound requests across the repo.
DEFAULT_HTTP_TIMEOUT: float = 15.0
