"""
Async SQLite storage for conversation history, rate limits, escalations,
and dead-end tracking.

The schema is deliberately denormalized — single `messages` table,
single `escalations` table, single `dead_end_state` row per user.
Reads and writes are mostly indexed lookups; no joins needed.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import aiosqlite
from loguru import logger


SCHEMA = """
CREATE TABLE IF NOT EXISTS messages (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id      INTEGER NOT NULL,
    role         TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
    content      TEXT NOT NULL,
    created_at   TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_messages_user_time
    ON messages(user_id, created_at);

CREATE TABLE IF NOT EXISTS escalations (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id      INTEGER NOT NULL,
    reason       TEXT NOT NULL,
    created_at   TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_escalations_time
    ON escalations(created_at);

CREATE TABLE IF NOT EXISTS dead_end_state (
    user_id      INTEGER PRIMARY KEY,
    streak       INTEGER NOT NULL DEFAULT 0,
    updated_at   TEXT NOT NULL DEFAULT (datetime('now'))
);
"""


class Storage:
    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path
        self._db: aiosqlite.Connection | None = None

    async def initialize(self) -> None:
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._db = await aiosqlite.connect(self._db_path)
        await self._db.executescript(SCHEMA)
        await self._db.commit()
        logger.info("SQLite ready at {}", self._db_path)

    async def close(self) -> None:
        if self._db is not None:
            await self._db.close()
            self._db = None

    # ---------- Messages / history ----------

    async def add_message(self, user_id: int, role: str, content: str) -> None:
        await self._require_db().execute(
            "INSERT INTO messages (user_id, role, content) VALUES (?, ?, ?)",
            (user_id, role, content),
        )
        await self._require_db().commit()

    async def get_recent_history(
        self,
        user_id: int,
        max_turns: int = 10,
    ) -> list[dict]:
        """
        Return up to `max_turns` * 2 most recent messages (a turn = user + assistant),
        oldest first — ready to pass directly to the Claude API.
        """
        max_messages = max_turns * 2
        async with self._require_db().execute(
            """
            SELECT role, content FROM messages
            WHERE user_id = ?
            ORDER BY id DESC
            LIMIT ?
            """,
            (user_id, max_messages),
        ) as cursor:
            rows = await cursor.fetchall()

        # Returned in reverse order, flip to chronological
        return [
            {"role": row[0], "content": row[1]}
            for row in reversed(rows)
        ]

    # ---------- Rate limiting ----------

    async def is_rate_limited(self, user_id: int, per_hour: int) -> bool:
        """True if the user has sent at least `per_hour` messages in the last 60 minutes."""
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=1)).strftime(
            "%Y-%m-%d %H:%M:%S"
        )
        async with self._require_db().execute(
            """
            SELECT COUNT(*) FROM messages
            WHERE user_id = ? AND role = 'user' AND created_at >= ?
            """,
            (user_id, cutoff),
        ) as cursor:
            row = await cursor.fetchone()

        return (row[0] if row else 0) >= per_hour

    # ---------- Dead-end streak ----------

    async def update_dead_end_streak(self, user_id: int, no_context: bool) -> int:
        """
        Increment the streak if this turn had no context, reset otherwise.
        Returns the new streak value.
        """
        db = self._require_db()
        async with db.execute(
            "SELECT streak FROM dead_end_state WHERE user_id = ?",
            (user_id,),
        ) as cursor:
            row = await cursor.fetchone()

        current = row[0] if row else 0
        new_streak = current + 1 if no_context else 0

        await db.execute(
            """
            INSERT INTO dead_end_state (user_id, streak, updated_at)
            VALUES (?, ?, datetime('now'))
            ON CONFLICT(user_id) DO UPDATE SET
                streak = excluded.streak,
                updated_at = excluded.updated_at
            """,
            (user_id, new_streak),
        )
        await db.commit()
        return new_streak

    # ---------- Escalations ----------

    async def mark_escalation(self, user_id: int, reason: str) -> None:
        await self._require_db().execute(
            "INSERT INTO escalations (user_id, reason) VALUES (?, ?)",
            (user_id, reason),
        )
        await self._require_db().commit()

    # ---------- Stats ----------

    async def get_stats(self) -> dict:
        db = self._require_db()
        now = datetime.now(timezone.utc)
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0).strftime(
            "%Y-%m-%d %H:%M:%S"
        )
        week_start = (now - timedelta(days=7)).strftime("%Y-%m-%d %H:%M:%S")

        async with db.execute(
            """
            SELECT
                COUNT(*) FILTER (WHERE created_at >= ?) AS today_msgs,
                COUNT(DISTINCT user_id) FILTER (WHERE created_at >= ?) AS today_users,
                COUNT(*) FILTER (WHERE created_at >= ?) AS week_msgs,
                COUNT(DISTINCT user_id) FILTER (WHERE created_at >= ?) AS week_users,
                COUNT(*) AS total_msgs,
                COUNT(DISTINCT user_id) AS total_users
            FROM messages
            WHERE role = 'user'
            """,
            (today_start, today_start, week_start, week_start),
        ) as cursor:
            row = await cursor.fetchone()

        async with db.execute(
            "SELECT COUNT(*) FROM escalations WHERE created_at >= ?",
            (today_start,),
        ) as cursor:
            esc_row = await cursor.fetchone()

        return {
            "today_messages": (row[0] if row else 0) or 0,
            "today_users": (row[1] if row else 0) or 0,
            "week_messages": (row[2] if row else 0) or 0,
            "week_users": (row[3] if row else 0) or 0,
            "total_messages": (row[4] if row else 0) or 0,
            "total_users": (row[5] if row else 0) or 0,
            "today_escalations": (esc_row[0] if esc_row else 0) or 0,
        }

    # ---------- Internal ----------

    def _require_db(self) -> aiosqlite.Connection:
        if self._db is None:
            raise RuntimeError("Storage not initialized")
        return self._db
