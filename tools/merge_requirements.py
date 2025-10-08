from __future__ import annotations

import sys
from pathlib import Path
from typing import Dict, List, Set, Tuple


def _read_lines(p: Path) -> List[str]:
    try:
        return [ln.strip() for ln in p.read_text(encoding="utf-8").splitlines()]
    except Exception:
        return []


def _is_req_line(ln: str) -> bool:
    if not ln:
        return False
    if ln.lstrip().startswith("#"):
        return False
    if ln.startswith("-r ") or ln.startswith("--requirement "):
        # avoid recursive includes; keep simple
        return False
    return True


def _pkg_key(ln: str) -> str:
    s = ln.split(";", 1)[0].strip()  # strip env markers
    # crude parse: stop at first version/operator char or extras
    stop_chars = set("><=!~ 	[")
    out = []
    for ch in s:
        if ch in stop_chars:
            break
        out.append(ch)
    return "".join(out).lower().replace("_", "-")


def collect_requirements(root: Path) -> Tuple[List[str], List[Path]]:
    base = root / "requirements.txt"
    base_lines = [ln for ln in _read_lines(base) if _is_req_line(ln)] if base.exists() else []
    plugin_req_files = sorted((root / "plugins").rglob("requirements.txt"))
    return base_lines, plugin_req_files


def merge_requirements(base: List[str], plugin_files: List[Path]) -> Tuple[List[str], List[str]]:
    ordered: List[str] = []
    seen_lines: Set[str] = set()
    seen_pkgs: Dict[str, str] = {}
    warnings: List[str] = []

    def add_line(ln: str, origin: str) -> None:
        key = _pkg_key(ln)
        if not key:
            return
        if ln in seen_lines:
            return
        if key in seen_pkgs and seen_pkgs[key] != ln:
            warnings.append(f"Conflict for {key!r}: keeping '{seen_pkgs[key]}', skipping '{ln}' from {origin}")
            return
        seen_lines.add(ln)
        seen_pkgs[key] = ln
        ordered.append(ln)

    for ln in base:
        add_line(ln, "requirements.txt")

    for req in plugin_files:
        for ln in _read_lines(req):
            if _is_req_line(ln):
                add_line(ln, str(req))

    return ordered, warnings


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    out_path = root / "requirements.all.txt"
    base, plugin_files = collect_requirements(root)
    merged, warnings = merge_requirements(base, plugin_files)
    try:
        out_path.write_text("\n".join(merged) + "\n", encoding="utf-8")
    except Exception as e:
        print(f"[merge] Failed to write {out_path}: {e}")
        return 2
    print(f"[merge] Collected {len(plugin_files)} plugin requirement files")
    if warnings:
        print(f"[merge] {len(warnings)} conflicts:")
        for w in warnings:
            print(f"  - {w}")
    print(f"[merge] Wrote {len(merged)} lines to {out_path}")
    print(f"[merge] Install with: pip install -r {out_path.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

