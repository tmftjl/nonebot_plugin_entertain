from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional, Union
from fnmatch import fnmatch


RES_DIR = Path(__file__).parent / "resources"
CFG_DIR = RES_DIR / "help_config"
CFG_MAP_FILE = CFG_DIR / "command_map.json"


def _available_configs() -> Dict[str, str]:
    """Return mapping of config name (stem, lower-cased) -> filename.

    Only `.json` files under `resources/config` are considered.
    """
    mapping: Dict[str, str] = {}
    if not CFG_DIR.exists():
        return mapping
    for p in CFG_DIR.iterdir():
        if p.is_file() and p.suffix.lower() == ".json":
            stem = p.stem.lower()
            mapping[stem] = p.name
    return mapping


def _default_cmd_map() -> Dict[str, str]:
    """Built-in fallback command -> filename mapping (lower-cased keys)."""
    return {
        # help.json
        "help": "help.json",
        "默认": "help.json",
        "群管": "help.json",
        "帮助": "help.json",
        "菜单": "help.json",
        "功能": "help.json",
        "admin": "help.json",
        # fun.json
        "fun": "fun.json",
        "娱乐": "fun.json",
        "娱乐帮助": "fun.json",
        "yx": "fun.json",
        "game": "fun.json",
        "games": "fun.json",
    }
def _load_cmd_map() -> Dict[str, str]:
    """Load command->config filename mapping from `command_map.json`.

    If the file does not exist or is invalid, return a default mapping.
    Keys are normalized to lower-case.
    """
    mapping: Dict[str, str] = {}
    try:
        if CFG_MAP_FILE.exists():
            import json

            # Use utf-8-sig to gracefully handle files saved with BOM
            raw = json.loads(CFG_MAP_FILE.read_text(encoding="utf-8-sig"))
            if isinstance(raw, dict):
                for k, v in raw.items():
                    if isinstance(k, str) and isinstance(v, str):
                        mapping[k.strip().lower()] = v.strip()
    except Exception:
        mapping = {}
    if not mapping:
        mapping = _default_cmd_map()
    return mapping


def resolve_help_config(user_input: Optional[str]) -> Optional[str]:
    """Resolve which config to use from user input via explicit mapping.

    Behavior:
    - Empty/None input -> return None (use default later)
    - Exact match against mapping keys (case-insensitive) -> return mapped filename
    - `*` wildcard supported against mapping keys; only resolves when exactly one match
    - If user provides a filename ending with `.json` that exists -> return it
    - Otherwise returns None (not found or ambiguous)
    """

    if not user_input or str(user_input).strip() == "":
        return None

    key = str(user_input).strip().lower()
    cmd_map = _load_cmd_map()

    # Direct hit in mapping
    if key in cmd_map:
        return cmd_map[key]

    # If input looks like a filename and exists, accept it
    if key.endswith(".json"):
        # Normalize filename as is, but only if present under config dir
        file = CFG_DIR / key
        if file.exists():
            return key

    # Wildcard matching over mapping keys
    if "*" in key:
        matched = [cmd_map[k] for k in cmd_map.keys() if fnmatch(k, key)]
        # Deduplicate mapped filenames in case multiple keys map to same file
        uniq = list({m for m in matched})
        if len(uniq) == 1:
            return uniq[0]
        return None

    # No match
    return None

def load_help_config(config: Union[str, None]) -> Dict[str, Any]:
    """Load config JSON from plugin resources by filename.

    - `config` is the mapped filename (e.g. `help.json`) or None
    - Defaults to `help.json` when input is None
    - Returns empty dict when the file cannot be loaded
    """
    filename = help_config_filename(config)
    file = CFG_DIR / filename
    if file.exists():
        try:
            import json

            # Read with utf-8-sig to support BOM while remaining compatible with UTF-8
            data = json.loads(file.read_text(encoding="utf-8-sig"))
            if isinstance(data, dict):
                return data
        except Exception:
            pass
    # Fallback to empty dict on error or missing file
    return {}


def help_config_filename(config: Union[str, None]) -> str:
    """Get the JSON filename for the given config name or alias.

    - Accepts a mapped filename (e.g. `help.json`) or an alias
    - Returns a filename like `help.json` with a default of `help.json`
    """
    if not config or str(config).strip() == "":
        return "help.json"
    name = str(config).strip().lower()
    if name.endswith(".json"):
        return name
    # Try resolve via mapping if an alias is provided
    mapped = _load_cmd_map().get(name)
    if mapped:
        return mapped
    # As a loose fallback, allow stems that exist
    avail = _available_configs()
    if name in avail:
        return avail[name]
    return "help.json"
