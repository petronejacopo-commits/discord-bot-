import aiosqlite
import asyncio
import os

class Database:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(Database, cls).__new__(cls)
            cls._instance.db_path = "data/bot.db"
            cls._instance.conn = None
        return cls._instance

    async def connect(self):
        if self.conn is None:
            self.conn = await aiosqlite.connect(self.db_path, isolation_level=None)
            # Enable foreign keys
            await self.conn.execute("PRAGMA foreign_keys = ON")

            # Setup tables
            await self._create_tables()

    async def _create_tables(self):
        tables = [
            """
            CREATE TABLE IF NOT EXISTS tickets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id INTEGER NOT NULL,
                channel_id INTEGER NOT NULL UNIQUE,
                owner_id INTEGER NOT NULL,
                category TEXT NOT NULL,
                priority TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'active', -- 'active' or 'closed'
                assigned_to INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                first_response_at TIMESTAMP,
                closed_at TIMESTAMP
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS ticket_categories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                emoji TEXT,
                description TEXT,
                welcome_message TEXT
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS authorized_users (
                guild_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                PRIMARY KEY (guild_id, user_id)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS guild_config (
                guild_id INTEGER NOT NULL,
                key TEXT NOT NULL,
                value TEXT NOT NULL,
                PRIMARY KEY (guild_id, key)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS transcript_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id INTEGER NOT NULL,
                channel_id INTEGER NOT NULL,
                file_path TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        ]

        for table in tables:
            await self.conn.execute(table)
        await self.conn.commit()

    async def get_config(self, guild_id: int, key: str, default=None):
        async with self.conn.execute(
            "SELECT value FROM guild_config WHERE guild_id = ? AND key = ?",
            (guild_id, key)
        ) as cursor:
            row = await cursor.fetchone()
            if row:
                return row[0]
            return default

    async def set_config(self, guild_id: int, key: str, value: str):
        await self.conn.execute(
            """
            INSERT INTO guild_config (guild_id, key, value)
            VALUES (?, ?, ?)
            ON CONFLICT(guild_id, key) DO UPDATE SET value = excluded.value
            """,
            (guild_id, key, str(value))
        )
        await self.conn.commit()

    async def remove_config(self, guild_id: int, key: str):
        await self.conn.execute(
            "DELETE FROM guild_config WHERE guild_id = ? AND key = ?",
            (guild_id, key)
        )
        await self.conn.commit()

    async def clear_guild_config(self, guild_id: int):
        await self.conn.execute("DELETE FROM guild_config WHERE guild_id = ?", (guild_id,))
        await self.conn.execute("DELETE FROM ticket_categories WHERE guild_id = ?", (guild_id,))
        await self.conn.commit()

    async def get_ticket_by_channel(self, channel_id: int):
        async with self.conn.execute(
            "SELECT * FROM tickets WHERE channel_id = ?",
            (channel_id,)
        ) as cursor:
            row = await cursor.fetchone()
            if row:
                # Return dict mapping column name to value
                columns = [desc[0] for desc in cursor.description]
                return dict(zip(columns, row))
            return None

    async def get_ticket_count(self, guild_id: int, owner_id: int) -> int:
        async with self.conn.execute(
            "SELECT COUNT(*) FROM tickets WHERE guild_id = ? AND owner_id = ? AND status = 'active'",
            (guild_id, owner_id)
        ) as cursor:
            row = await cursor.fetchone()
            return row[0] if row else 0

    async def create_ticket(self, guild_id: int, channel_id: int, owner_id: int, category: str, priority: str, ticket_limit: int) -> bool:
        # Use a transaction to safely handle the ticket limit check and insert
        try:
            # Begin an immediate transaction to acquire a write lock immediately
            await self.conn.execute("BEGIN IMMEDIATE")

            # Check limit
            async with self.conn.execute(
                "SELECT COUNT(*) FROM tickets WHERE guild_id = ? AND owner_id = ? AND status = 'active'",
                (guild_id, owner_id)
            ) as cursor:
                row = await cursor.fetchone()
                current_count = row[0] if row else 0

            if current_count >= ticket_limit:
                # Limit reached, rollback
                await self.conn.execute("ROLLBACK")
                return False

            # Insert the new ticket
            await self.conn.execute(
                """
                INSERT INTO tickets (guild_id, channel_id, owner_id, category, priority, status)
                VALUES (?, ?, ?, ?, ?, 'active')
                """,
                (guild_id, channel_id, owner_id, category, priority)
            )
            await self.conn.commit()
            return True
        except Exception as e:
            await self.conn.execute("ROLLBACK")
            raise e

    async def close_ticket(self, channel_id: int):
        await self.conn.execute(
            "UPDATE tickets SET status = 'closed', closed_at = CURRENT_TIMESTAMP WHERE channel_id = ?",
            (channel_id,)
        )
        await self.conn.commit()

    async def assign_ticket(self, channel_id: int, user_id: int):
        # Update assigned_to and first_response_at if not set
        await self.conn.execute(
            """
            UPDATE tickets
            SET assigned_to = ?,
                first_response_at = COALESCE(first_response_at, CURRENT_TIMESTAMP)
            WHERE channel_id = ?
            """,
            (user_id, channel_id)
        )
        await self.conn.commit()

    async def release_ticket(self, channel_id: int):
        await self.conn.execute(
            "UPDATE tickets SET assigned_to = NULL WHERE channel_id = ?",
            (channel_id,)
        )
        await self.conn.commit()

    async def update_ticket_priority(self, channel_id: int, priority: str):
        await self.conn.execute(
            "UPDATE tickets SET priority = ? WHERE channel_id = ?",
            (priority, channel_id)
        )
        await self.conn.commit()

    async def get_categories(self, guild_id: int):
        async with self.conn.execute(
            "SELECT name, emoji, description, welcome_message FROM ticket_categories WHERE guild_id = ?",
            (guild_id,)
        ) as cursor:
            rows = await cursor.fetchall()
            return [
                {
                    "name": r[0],
                    "emoji": r[1],
                    "description": r[2],
                    "welcome_message": r[3]
                }
                for r in rows
            ]

    async def get_category_names(self, guild_id: int):
        async with self.conn.execute(
            "SELECT name FROM ticket_categories WHERE guild_id = ?",
            (guild_id,)
        ) as cursor:
            rows = await cursor.fetchall()
            return [r[0] for r in rows]

    async def add_category(self, guild_id: int, name: str, emoji: str, description: str, welcome_message: str):
        await self.conn.execute(
            """
            INSERT INTO ticket_categories (guild_id, name, emoji, description, welcome_message)
            VALUES (?, ?, ?, ?, ?)
            """,
            (guild_id, name, emoji, description, welcome_message)
        )
        await self.conn.commit()

    async def remove_category(self, guild_id: int, name: str):
        await self.conn.execute(
            "DELETE FROM ticket_categories WHERE guild_id = ? AND name = ?",
            (guild_id, name)
        )
        await self.conn.commit()

    async def is_authorized(self, guild_id: int, user_id: int) -> bool:
        async with self.conn.execute(
            "SELECT 1 FROM authorized_users WHERE guild_id = ? AND user_id = ?",
            (guild_id, user_id)
        ) as cursor:
            row = await cursor.fetchone()
            return row is not None

    async def get_authorized_users(self, guild_id: int):
        async with self.conn.execute(
            "SELECT user_id FROM authorized_users WHERE guild_id = ?",
            (guild_id,)
        ) as cursor:
            rows = await cursor.fetchall()
            return [r[0] for r in rows]

    async def add_authorized_user(self, guild_id: int, user_id: int):
        await self.conn.execute(
            "INSERT OR IGNORE INTO authorized_users (guild_id, user_id) VALUES (?, ?)",
            (guild_id, user_id)
        )
        await self.conn.commit()

    async def remove_authorized_user(self, guild_id: int, user_id: int):
        await self.conn.execute(
            "DELETE FROM authorized_users WHERE guild_id = ? AND user_id = ?",
            (guild_id, user_id)
        )
        await self.conn.commit()

    async def add_transcript_log(self, guild_id: int, channel_id: int, file_path: str):
        await self.conn.execute(
            "INSERT INTO transcript_logs (guild_id, channel_id, file_path) VALUES (?, ?, ?)",
            (guild_id, channel_id, file_path)
        )
        await self.conn.commit()

    async def get_active_tickets(self, guild_id: int = None):
        query = "SELECT * FROM tickets WHERE status = 'active'"
        params = []
        if guild_id:
            query += " AND guild_id = ?"
            params.append(guild_id)

        async with self.conn.execute(query, tuple(params)) as cursor:
            rows = await cursor.fetchall()
            columns = [desc[0] for desc in cursor.description]
            return [dict(zip(columns, row)) for row in rows]

    async def get_expired_tickets(self, max_age_days: int):
        async with self.conn.execute(
            "SELECT * FROM tickets WHERE status = 'active' AND (julianday(CURRENT_TIMESTAMP) - julianday(created_at)) > ?",
            (max_age_days,)
        ) as cursor:
            rows = await cursor.fetchall()
            columns = [desc[0] for desc in cursor.description]
            return [dict(zip(columns, row)) for row in rows]

    async def get_avg_response_time(self, guild_id: int) -> float:
        # returns in minutes
        async with self.conn.execute(
            """
            SELECT AVG((julianday(first_response_at) - julianday(created_at)) * 24 * 60)
            FROM tickets
            WHERE guild_id = ? AND first_response_at IS NOT NULL
            """,
            (guild_id,)
        ) as cursor:
            row = await cursor.fetchone()
            return row[0] if row and row[0] is not None else 0.0

db = Database()
