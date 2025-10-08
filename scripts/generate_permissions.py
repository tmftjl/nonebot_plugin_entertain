from __future__ import annotations

import json
import re
from pathlib import Path
import ast


ROOT = Path(__file__).resolve().parents[1]
CONF = ROOT / "config" / "permissions.json"
PLUGINS = ROOT / "plugins"


def _perm_entry_default():
    return {
        "enabled": True,
        "level": "all",
        "scene": "all",
        "whitelist": {"users": [], "groups": []},
        "blacklist": {"users": [], "groups": []},
    }


def main() -> None:
    data: dict = {}
    if PLUGINS.exists():
        for pdir in PLUGINS.iterdir():
            if not pdir.is_dir() or not (pdir / "__init__.py").exists():
                continue
            pname = pdir.name
            node = data.setdefault(pname, {"top": _perm_entry_default(), "commands": {}})
            node.setdefault("top", _perm_entry_default())
            cmds = node.setdefault("commands", {})
            for f in pdir.rglob("*.py"):
                try:
                    text = f.read_text(encoding="utf-8", errors="ignore")
                except Exception:
                    continue
                try:
                    tree = ast.parse(text.lstrip("\ufeff"))
                except Exception:
                    continue

                # gather alias names for upsert_command_defaults
                up_names = {"upsert_command_defaults"}
                for node in ast.walk(tree):
                    if isinstance(node, ast.ImportFrom):
                        try:
                            for alias in node.names:
                                if alias.name == "upsert_command_defaults" and alias.asname:
                                    up_names.add(alias.asname)
                        except Exception:
                            pass

                for node in ast.walk(tree):
                    try:
                        if isinstance(node, ast.Call):
                            fn = node.func
                            # P.on_regex(..., name="...")
                            if isinstance(fn, ast.Attribute) and isinstance(fn.value, ast.Name) and fn.value.id == "P" and fn.attr == "on_regex":
                                for kw in node.keywords or []:
                                    if kw.arg == "name" and isinstance(kw.value, ast.Constant) and isinstance(kw.value.value, str):
                                        cmds.setdefault(str(kw.value.value), _perm_entry_default())
                            # P.permission_cmd("...")
                            if isinstance(fn, ast.Attribute) and isinstance(fn.value, ast.Name) and fn.value.id == "P" and fn.attr == "permission_cmd":
                                if node.args and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str):
                                    cmds.setdefault(str(node.args[0].value), _perm_entry_default())
                            # upsert_command_defaults(pname, "...") or alias
                            if isinstance(fn, ast.Name) and fn.id in up_names:
                                if len(node.args) >= 2 and all(isinstance(a, ast.Constant) and isinstance(a.value, str) for a in node.args[:2]):
                                    pn = str(node.args[0].value)
                                    cn = str(node.args[1].value)
                                    if pn == pname:
                                        cmds.setdefault(cn, _perm_entry_default())
                    except Exception:
                        continue

    CONF.parent.mkdir(parents=True, exist_ok=True)
    CONF.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
