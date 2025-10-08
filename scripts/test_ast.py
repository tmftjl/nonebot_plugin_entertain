from __future__ import annotations

from pathlib import Path
import ast

base = Path(__file__).resolve().parents[1] / "plugins"
for f in base.rglob("*.py"):
    try:
        text = f.read_text(encoding="utf-8", errors="ignore")
        ast.parse(text)
        print("OK", f)
    except Exception as e:
        print("ERR", f, e)

