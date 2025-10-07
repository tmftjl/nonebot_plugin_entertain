from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Dict

from .utils import config_dir


class PermissionsStore:
    def __init__(self) -> None:
        self._path: Path = config_dir() / "permissions.json"
        self._data: Dict[str, Any] = {}
        self._mtime: float = 0.0
        self._loaded: bool = False
        self._last_check: float = 0.0

    def _reload(self) -> None:
        try:
            text = self._path.read_text(encoding="utf-8")
            data = json.loads(text)
            if isinstance(data, dict):
                self._data = data
                self._mtime = self._path.stat().st_mtime
                self._loaded = True
        except Exception:
            # keep previous data on error
            pass

    def ensure_loaded(self) -> None:
        now = time.time()
        # throttle mtime checks to avoid too frequent stat calls
        if not self._loaded or (now - self._last_check) > 0.5:
            self._last_check = now
            try:
                m = self._path.stat().st_mtime
            except Exception:
                m = 0.0
            if (not self._loaded) or (m != self._mtime):
                self._reload()

    def get(self) -> Dict[str, Any]:
        self.ensure_loaded()
        return self._data or {}

    def reload(self) -> None:
        self._reload()


permissions_store = PermissionsStore()

