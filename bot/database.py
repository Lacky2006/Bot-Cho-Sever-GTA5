from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import aiosqlite


def utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class Database:
    def __init__(self, path: Path) -> None:
        self.path = path

    async def initialize(self) -> None:
        async with aiosqlite.connect(self.path) as db:
            await db.executescript(
                """
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS guild_settings (
                    guild_id INTEGER PRIMARY KEY,
                    welcome_channel_id INTEGER,
                    goodbye_channel_id INTEGER,
                    ticket_category_id INTEGER,
                    closed_category_id INTEGER,
                    panel_channel_id INTEGER,
                    panel_message_id INTEGER,
                    log_channel_id INTEGER,
                    citizen_panel_channel_id INTEGER,
                    citizen_panel_message_id INTEGER,
                    citizen_log_channel_id INTEGER
                );
                CREATE TABLE IF NOT EXISTS tickets (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    guild_id INTEGER NOT NULL,
                    channel_id INTEGER UNIQUE NOT NULL,
                    owner_id INTEGER NOT NULL,
                    ticket_type TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'open',
                    slug TEXT UNIQUE NOT NULL,
                    created_at TEXT NOT NULL,
                    closed_at TEXT,
                    expires_at TEXT,
                    log_message_id INTEGER
                );
                CREATE INDEX IF NOT EXISTS idx_ticket_owner
                    ON tickets(guild_id, owner_id, status);
                CREATE INDEX IF NOT EXISTS idx_ticket_expiry
                    ON tickets(expires_at);
                CREATE TABLE IF NOT EXISTS citizen_applications (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    guild_id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL,
                    answers_json TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending',
                    created_at TEXT NOT NULL,
                    reviewed_at TEXT,
                    reviewer_id INTEGER,
                    rejection_reason TEXT,
                    log_message_id INTEGER
                );
                CREATE INDEX IF NOT EXISTS idx_citizen_pending
                    ON citizen_applications(guild_id, user_id, status);
                """
            )
            columns = await (await db.execute("PRAGMA table_info(guild_settings)")).fetchall()
            existing = {column[1] for column in columns}
            for column in ("citizen_panel_channel_id", "citizen_panel_message_id", "citizen_log_channel_id"):
                if column not in existing:
                    await db.execute(f"ALTER TABLE guild_settings ADD COLUMN {column} INTEGER")
            await db.commit()

    async def fetchone(self, query: str, params: tuple[Any, ...] = ()) -> dict[str, Any] | None:
        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(query, params) as cursor:
                row = await cursor.fetchone()
                return dict(row) if row else None

    async def fetchall(self, query: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(query, params) as cursor:
                return [dict(row) for row in await cursor.fetchall()]

    async def execute(self, query: str, params: tuple[Any, ...] = ()) -> int:
        async with aiosqlite.connect(self.path) as db:
            cursor = await db.execute(query, params)
            await db.commit()
            return cursor.lastrowid

    async def get_guild_settings(self, guild_id: int) -> dict[str, Any]:
        row = await self.fetchone("SELECT * FROM guild_settings WHERE guild_id = ?", (guild_id,))
        if row:
            return row
        await self.execute("INSERT OR IGNORE INTO guild_settings(guild_id) VALUES (?)", (guild_id,))
        return {"guild_id": guild_id}

    async def update_guild_settings(self, guild_id: int, **values: int | None) -> None:
        if not values:
            return
        allowed = {
            "welcome_channel_id", "goodbye_channel_id", "ticket_category_id",
            "closed_category_id", "panel_channel_id", "panel_message_id", "log_channel_id",
            "citizen_panel_channel_id", "citizen_panel_message_id", "citizen_log_channel_id",
        }
        if not set(values).issubset(allowed):
            raise ValueError("Trường cấu hình guild không hợp lệ")
        assignments = ", ".join(f"{key} = ?" for key in values)
        params = (*values.values(), guild_id)
        await self.execute(f"UPDATE guild_settings SET {assignments} WHERE guild_id = ?", params)

    async def find_open_ticket(self, guild_id: int, owner_id: int) -> dict[str, Any] | None:
        return await self.fetchone(
            "SELECT * FROM tickets WHERE guild_id = ? AND owner_id = ? AND status = 'open' ORDER BY id DESC LIMIT 1",
            (guild_id, owner_id),
        )

    async def get_ticket(self, channel_id: int) -> dict[str, Any] | None:
        return await self.fetchone("SELECT * FROM tickets WHERE channel_id = ?", (channel_id,))

    async def create_ticket(
        self, guild_id: int, channel_id: int, owner_id: int, ticket_type: str, slug: str
    ) -> int:
        return await self.execute(
            "INSERT INTO tickets(guild_id, channel_id, owner_id, ticket_type, slug, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (guild_id, channel_id, owner_id, ticket_type, slug, utc_iso()),
        )

    async def close_ticket(self, channel_id: int, expires_at: str, status: str = "closed") -> None:
        await self.execute(
            "UPDATE tickets SET status = ?, closed_at = ?, expires_at = ? WHERE channel_id = ?",
            (status, utc_iso(), expires_at, channel_id),
        )

    async def create_citizen_application(self, guild_id: int, user_id: int, answers_json: str) -> int:
        return await self.execute(
            "INSERT INTO citizen_applications(guild_id, user_id, answers_json, created_at) VALUES (?, ?, ?, ?)",
            (guild_id, user_id, answers_json, utc_iso()),
        )

    async def pending_citizen_application(self, guild_id: int, user_id: int) -> dict[str, Any] | None:
        return await self.fetchone(
            "SELECT * FROM citizen_applications WHERE guild_id = ? AND user_id = ? AND status = 'pending' ORDER BY id DESC LIMIT 1",
            (guild_id, user_id),
        )

    async def pending_citizen_applications(self) -> list[dict[str, Any]]:
        return await self.fetchall("SELECT * FROM citizen_applications WHERE status = 'pending'")

    async def get_citizen_application(self, application_id: int) -> dict[str, Any] | None:
        return await self.fetchone("SELECT * FROM citizen_applications WHERE id = ?", (application_id,))

    async def review_citizen_application(
        self, application_id: int, reviewer_id: int, status: str, rejection_reason: str | None = None
    ) -> None:
        await self.execute(
            "UPDATE citizen_applications SET status = ?, reviewer_id = ?, reviewed_at = ?, rejection_reason = ? WHERE id = ? AND status = 'pending'",
            (status, reviewer_id, utc_iso(), rejection_reason, application_id),
        )
