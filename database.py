"""SQLite ma'lumotlar bazasi: sozlamalar, oq ro'yxat, loglar, kirishlar tarixi."""
from __future__ import annotations

import json
import sqlite3
import threading
import time

import config

_SCHEMA = """
CREATE TABLE IF NOT EXISTS chats (
    chat_id     INTEGER PRIMARY KEY,
    title       TEXT,
    type        TEXT,
    enabled     INTEGER NOT NULL DEFAULT 1,
    mode        TEXT,
    threshold   INTEGER,
    strict      INTEGER,
    added_at    INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS whitelist (
    chat_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    added_at INTEGER NOT NULL,
    PRIMARY KEY (chat_id, user_id)
);
CREATE TABLE IF NOT EXISTS events (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id   INTEGER NOT NULL,
    user_id   INTEGER NOT NULL,
    name      TEXT,
    username  TEXT,
    score     INTEGER NOT NULL,
    reasons   TEXT,
    action    TEXT NOT NULL,
    ts        INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_events_chat ON events(chat_id, ts);
CREATE TABLE IF NOT EXISTS joins (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    link    TEXT,
    ts      INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_joins_chat_ts ON joins(chat_id, ts);
"""


class DB:
    def __init__(self, path: str | None = None) -> None:
        self.path = path or config.DB_PATH
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(self.path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        with self._lock:
            self._conn.executescript(_SCHEMA)
            # eski bazalarni yangilash (ustun allaqachon bo'lsa — jim o'tadi)
            for sql in (
                "ALTER TABLE chats ADD COLUMN strict INTEGER",
                "ALTER TABLE chats ADD COLUMN added_by INTEGER",
                "ALTER TABLE chats ADD COLUMN added_by_name TEXT",
                "ALTER TABLE chats ADD COLUMN present INTEGER DEFAULT 1",
            ):
                try:
                    self._conn.execute(sql)
                except sqlite3.OperationalError:
                    pass
            self._conn.commit()

    # ------------------------------------------------------------ utils
    def _exec(self, sql: str, params: tuple = ()) -> sqlite3.Cursor:
        with self._lock:
            cur = self._conn.execute(sql, params)
            self._conn.commit()
            return cur

    def _one(self, sql: str, params: tuple = ()) -> sqlite3.Row | None:
        with self._lock:
            return self._conn.execute(sql, params).fetchone()

    def _all(self, sql: str, params: tuple = ()) -> list[sqlite3.Row]:
        with self._lock:
            return self._conn.execute(sql, params).fetchall()

    # ------------------------------------------------------------ chats
    def register_chat(self, chat_id: int, title: str, chat_type: str) -> None:
        self._exec(
            "INSERT INTO chats(chat_id,title,type,enabled,present,added_at) "
            "VALUES(?,?,?,1,1,?) "
            "ON CONFLICT(chat_id) DO UPDATE SET title=excluded.title, "
            "type=excluded.type, present=1",
            (chat_id, title, chat_type, int(time.time())),
        )

    def set_present(self, chat_id: int, present: int) -> None:
        self._exec("UPDATE chats SET present=? WHERE chat_id=?",
                   (1 if present else 0, chat_id))

    def settings(self, chat_id: int) -> dict:
        row = self._one("SELECT * FROM chats WHERE chat_id=?", (chat_id,))
        cols = set(row.keys()) if row else set()

        def col(name, default):
            if row is None or name not in cols or row[name] is None:
                return default
            return row[name]

        return {
            "chat_id": chat_id,
            "title": col("title", None) or str(chat_id),
            "type": col("type", "") or "",
            "enabled": bool(col("enabled", 1)),
            "mode": col("mode", config.MODE),
            "threshold": col("threshold", config.SCORE_THRESHOLD),
            "strict": int(col("strict", config.STRICT_LEVEL)),
            "added_by": col("added_by", 0) or 0,
            "added_by_name": col("added_by_name", "") or "",
        }

    def set_added_by(self, chat_id: int, user_id: int, name: str) -> None:
        self._exec(
            "INSERT INTO chats(chat_id,added_by,added_by_name,added_at) VALUES(?,?,?,?) "
            "ON CONFLICT(chat_id) DO UPDATE SET added_by=excluded.added_by, "
            "added_by_name=excluded.added_by_name",
            (chat_id, user_id, name, int(time.time())),
        )

    def set_setting(self, chat_id: int, key: str, value) -> None:
        if key not in ("enabled", "mode", "threshold", "title", "strict"):
            raise ValueError(key)
        self._exec(
            f"INSERT INTO chats(chat_id,{key},added_at) VALUES(?,?,?) "
            f"ON CONFLICT(chat_id) DO UPDATE SET {key}=excluded.{key}",
            (chat_id, value, int(time.time())),
        )

    def all_chats(self, present_only: bool = False) -> list[dict]:
        where = "WHERE present IS NOT 0" if present_only else ""
        return [dict(r) for r in
                self._all(f"SELECT * FROM chats {where} ORDER BY added_at DESC")]

    def remove_chat(self, chat_id: int) -> None:
        """Kanalni bazadan to'liq o'chiradi."""
        self._exec("DELETE FROM chats WHERE chat_id=?", (chat_id,))
        self._exec("DELETE FROM whitelist WHERE chat_id=?", (chat_id,))

    # -------------------------------------------------------- whitelist
    def is_whitelisted(self, chat_id: int, user_id: int) -> bool:
        return self._one(
            "SELECT 1 FROM whitelist WHERE user_id=? AND chat_id IN (?,0)",
            (user_id, chat_id),
        ) is not None

    def whitelist_add(self, chat_id: int, user_id: int) -> None:
        self._exec(
            "INSERT OR IGNORE INTO whitelist(chat_id,user_id,added_at) VALUES(?,?,?)",
            (chat_id, user_id, int(time.time())),
        )

    def whitelist_remove(self, chat_id: int, user_id: int) -> None:
        self._exec("DELETE FROM whitelist WHERE chat_id=? AND user_id=?", (chat_id, user_id))

    def whitelist_list(self, chat_id: int) -> list[int]:
        return [r["user_id"] for r in self._all(
            "SELECT user_id FROM whitelist WHERE chat_id IN (?,0)", (chat_id,))]

    # ----------------------------------------------------------- joins
    def record_join(self, chat_id: int, user_id: int, link: str | None) -> None:
        self._exec(
            "INSERT INTO joins(chat_id,user_id,link,ts) VALUES(?,?,?,?)",
            (chat_id, user_id, link, int(time.time())),
        )

    def joins_in_window(self, chat_id: int, window: int) -> int:
        row = self._one(
            "SELECT COUNT(*) AS n FROM joins WHERE chat_id=? AND ts>=?",
            (chat_id, int(time.time()) - window),
        )
        return int(row["n"]) if row else 0

    def same_link_in_window(self, chat_id: int, link: str | None, window: int) -> int:
        if not link:
            return 0
        row = self._one(
            "SELECT COUNT(*) AS n FROM joins WHERE chat_id=? AND link=? AND ts>=?",
            (chat_id, link, int(time.time()) - window),
        )
        return int(row["n"]) if row else 0

    def cleanup_joins(self, older_than: int = 86_400) -> None:
        self._exec("DELETE FROM joins WHERE ts < ?", (int(time.time()) - older_than,))

    # ---------------------------------------------------------- events
    def log_event(self, chat_id: int, user_id: int, name: str, username: str | None,
                  score: int, reasons: list[str], action: str) -> int:
        cur = self._exec(
            "INSERT INTO events(chat_id,user_id,name,username,score,reasons,action,ts)"
            " VALUES(?,?,?,?,?,?,?,?)",
            (chat_id, user_id, name, username, score,
             json.dumps(reasons, ensure_ascii=False), action, int(time.time())),
        )
        return int(cur.lastrowid or 0)

    def _scope(self, chat_id: int | None, chat_ids: list[int] | None) -> tuple[str, tuple]:
        """WHERE qismi: bitta chat, chatlar ro'yxati yoki hammasi."""
        if chat_ids is not None:
            if not chat_ids:
                return "WHERE 0", ()
            marks = ",".join("?" * len(chat_ids))
            return f"WHERE chat_id IN ({marks})", tuple(chat_ids)
        if chat_id:
            return "WHERE chat_id=?", (chat_id,)
        return "", ()

    def stats(self, chat_id: int | None = None,
              chat_ids: list[int] | None = None) -> dict:
        where, params = self._scope(chat_id, chat_ids)
        day = int(time.time()) - 86_400
        total = self._one(f"SELECT COUNT(*) AS n FROM events {where}", params)
        blocked = self._one(
            f"SELECT COUNT(*) AS n FROM events {where or 'WHERE 1=1'}"
            " AND action IN ('ban','kick','mute','decline')", params)
        today = self._one(
            f"SELECT COUNT(*) AS n FROM events {where or 'WHERE 1=1'}"
            " AND action IN ('ban','kick','mute','decline') AND ts>=?", params + (day,))
        passed = self._one(
            f"SELECT COUNT(*) AS n FROM events {where or 'WHERE 1=1'}"
            " AND action IN ('pass','approve')", params)
        failed = self._one(
            f"SELECT COUNT(*) AS n FROM events {where or 'WHERE 1=1'}"
            " AND action='failed'", params)
        return {
            "total": int(total["n"]) if total else 0,
            "blocked": int(blocked["n"]) if blocked else 0,
            "blocked_today": int(today["n"]) if today else 0,
            "passed": int(passed["n"]) if passed else 0,
            "failed": int(failed["n"]) if failed else 0,
        }

    def last_passed(self, chat_id: int | None = None, limit: int = 15,
                    chat_ids: list[int] | None = None) -> list[dict]:
        """O'tkazib yuborilganlar — chegarani sozlash uchun."""
        where, params = self._scope(chat_id, chat_ids)
        clause = f"{where or 'WHERE 1=1'} AND action IN ('pass','approve')"
        rows = self._all(
            f"SELECT * FROM events {clause} ORDER BY id DESC LIMIT ?",
            params + (limit,))
        return [dict(r) for r in rows]

    def last_events(self, chat_id: int | None = None, limit: int = 10,
                    chat_ids: list[int] | None = None) -> list[dict]:
        where, params = self._scope(chat_id, chat_ids)
        rows = self._all(
            f"SELECT * FROM events {where} ORDER BY id DESC LIMIT ?",
            params + (limit,))
        return [dict(r) for r in rows]

    def block_counts(self) -> dict[int, int]:
        """Har kanal bo'yicha bloklanganlar soni."""
        rows = self._all(
            "SELECT chat_id, COUNT(*) AS n FROM events "
            "WHERE action IN ('ban','kick','mute','decline') GROUP BY chat_id")
        return {int(r["chat_id"]): int(r["n"]) for r in rows}

    def customers(self) -> list[tuple[int, str]]:
        """Botni qo'shgan noyob foydalanuvchilar (mijozlar)."""
        rows = self._all(
            "SELECT DISTINCT added_by, added_by_name FROM chats "
            "WHERE added_by IS NOT NULL AND added_by <> 0")
        return [(int(r["added_by"]), r["added_by_name"] or "") for r in rows]

    def close(self) -> None:
        with self._lock:
            self._conn.close()
