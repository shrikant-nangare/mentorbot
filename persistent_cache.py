import json
import os
import sqlite3
import threading
import time
from dataclasses import dataclass


@dataclass(frozen=True)
class CacheConfig:
    path: str
    ttl_s: int
    max_entries: int


class SqliteCache:
    """
    Small persistent cache for strings/JSON.
    Designed for single-writer/small-concurrency FastAPI usage.
    """

    def __init__(self, config: CacheConfig):
        self._path = str(config.path or "").strip()
        self._ttl_s = int(config.ttl_s)
        self._max_entries = int(config.max_entries)
        self._lock = threading.Lock()

        if not self._path:
            raise ValueError("Cache path is empty.")

        os.makedirs(os.path.dirname(self._path) or ".", exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._path, timeout=5, check_same_thread=False)
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        return conn

    def _init_db(self) -> None:
        with self._lock:
            conn = self._connect()
            try:
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS cache (
                      key TEXT PRIMARY KEY,
                      value TEXT NOT NULL,
                      created_at INTEGER NOT NULL,
                      expires_at INTEGER NOT NULL,
                      hits INTEGER NOT NULL DEFAULT 0
                    )
                    """.strip()
                )
                conn.execute("CREATE INDEX IF NOT EXISTS idx_cache_expires_at ON cache(expires_at)")
                conn.commit()
            finally:
                conn.close()

    def _now(self) -> int:
        return int(time.time())

    def _expiry(self, now: int) -> int:
        if self._ttl_s <= 0:
            return now + 10**9  # effectively "never" for our purposes
        return now + int(self._ttl_s)

    def _purge_expired(self, conn: sqlite3.Connection, now: int) -> None:
        conn.execute("DELETE FROM cache WHERE expires_at < ?", (int(now),))

    def _enforce_max_entries(self, conn: sqlite3.Connection) -> None:
        if self._max_entries <= 0:
            return
        # Trim oldest entries if we exceed max_entries.
        conn.execute(
            """
            DELETE FROM cache
            WHERE key IN (
              SELECT key FROM cache
              ORDER BY created_at ASC
              LIMIT (SELECT max(0, (SELECT COUNT(*) FROM cache) - ?) )
            )
            """.strip(),
            (int(self._max_entries),),
        )

    def get(self, key: str) -> str | None:
        k = str(key or "").strip()
        if not k:
            return None
        now = self._now()
        with self._lock:
            conn = self._connect()
            try:
                self._purge_expired(conn, now)
                row = conn.execute(
                    "SELECT value, expires_at FROM cache WHERE key = ?",
                    (k,),
                ).fetchone()
                if not row:
                    conn.commit()
                    return None
                value, expires_at = row[0], int(row[1])
                if expires_at < now:
                    conn.execute("DELETE FROM cache WHERE key = ?", (k,))
                    conn.commit()
                    return None
                conn.execute("UPDATE cache SET hits = hits + 1 WHERE key = ?", (k,))
                conn.commit()
                return str(value)
            finally:
                conn.close()

    def set(self, key: str, value: str) -> None:
        k = str(key or "").strip()
        if not k:
            return
        v = str(value or "")
        now = self._now()
        expires_at = self._expiry(now)
        with self._lock:
            conn = self._connect()
            try:
                self._purge_expired(conn, now)
                conn.execute(
                    """
                    INSERT INTO cache(key, value, created_at, expires_at, hits)
                    VALUES(?, ?, ?, ?, 0)
                    ON CONFLICT(key) DO UPDATE SET
                      value=excluded.value,
                      created_at=excluded.created_at,
                      expires_at=excluded.expires_at
                    """.strip(),
                    (k, v, int(now), int(expires_at)),
                )
                self._enforce_max_entries(conn)
                conn.commit()
            finally:
                conn.close()

    def delete(self, key: str) -> None:
        k = str(key or "").strip()
        if not k:
            return
        with self._lock:
            conn = self._connect()
            try:
                conn.execute("DELETE FROM cache WHERE key = ?", (k,))
                conn.commit()
            finally:
                conn.close()

    def get_json(self, key: str) -> object | None:
        raw = self.get(key)
        if raw is None:
            return None
        try:
            return json.loads(raw)
        except Exception:
            return None

    def set_json(self, key: str, value: object) -> None:
        try:
            payload = json.dumps(value, ensure_ascii=False, sort_keys=True)
        except Exception:
            return
        self.set(key, payload)

