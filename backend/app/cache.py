"""A tiny thread-safe key/value cache on SQLite (standard library only).

Used for LLM responses, requirement extraction and fetched job boards, so reruns
are instant and free. Delete the backend/.cache folder to wipe it.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any

from .config import settings


def make_key(*parts: Any) -> str:
    raw = json.dumps(parts, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class Cache:
    def __init__(self, path: Path, enabled: bool = True) -> None:
        self.enabled = enabled
        self._lock = threading.Lock()
        self._db: sqlite3.Connection | None = None
        if enabled:
            path.parent.mkdir(parents=True, exist_ok=True)
            self._db = sqlite3.connect(str(path), check_same_thread=False)
            self._db.execute(
                "CREATE TABLE IF NOT EXISTS kv (ns TEXT, k TEXT, v TEXT, expires REAL, PRIMARY KEY (ns, k))"
            )
            self._db.commit()

    def get(self, ns: str, key: str) -> Any | None:
        if not self._db:
            return None
        with self._lock:
            row = self._db.execute("SELECT v, expires FROM kv WHERE ns=? AND k=?", (ns, key)).fetchone()
        if not row:
            return None
        value, expires = row
        if expires and expires < time.time():
            return None
        return json.loads(value)

    def set(self, ns: str, key: str, value: Any, ttl: float | None = None) -> None:
        if not self._db:
            return
        expires = time.time() + ttl if ttl else None
        payload = json.dumps(value, ensure_ascii=False)
        with self._lock:
            self._db.execute(
                "INSERT OR REPLACE INTO kv (ns, k, v, expires) VALUES (?, ?, ?, ?)", (ns, key, payload, expires)
            )
            self._db.commit()


cache = Cache(settings.cache_dir / "cache.sqlite3", enabled=settings.cache_enabled)
