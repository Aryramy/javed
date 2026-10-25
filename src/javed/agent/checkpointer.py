"""Persistent SQLite checkpointer for thread-scoped LangGraph state."""

import logging
import sqlite3
from pathlib import Path

import aiosqlite
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

logger = logging.getLogger("javed.agent.checkpointer")


class AgentCheckpointerManager:
    """Manages SQLite checkpoint database and thread state persistence."""

    def __init__(self, db_path: str = "data/checkpoints.db") -> None:
        self.db_path = db_path
        self._async_conn: aiosqlite.Connection | None = None
        self._async_saver: AsyncSqliteSaver | None = None
        self._sync_conn: sqlite3.Connection | None = None
        self._sync_saver: SqliteSaver | None = None

    async def initialize_async(self) -> AsyncSqliteSaver:
        """Initialize the async SQLite connection and setup checkpoint tables."""
        if self._async_saver is not None:
            return self._async_saver

        if self.db_path != ":memory:":
            path = Path(self.db_path)
            path.parent.mkdir(parents=True, exist_ok=True)

        self._async_conn = await aiosqlite.connect(self.db_path, timeout=30.0)
        await self._async_conn.execute("PRAGMA journal_mode=WAL;")
        await self._async_conn.execute("PRAGMA busy_timeout=30000;")
        self._async_saver = AsyncSqliteSaver(self._async_conn)
        await self._async_saver.setup()
        logger.info("Initialized AsyncSqliteSaver at %s (WAL enabled)", self.db_path)
        return self._async_saver

    def initialize_sync(self) -> SqliteSaver:
        """Initialize sync SQLite connection (useful for unit testing and inspection)."""
        if self._sync_saver is not None:
            return self._sync_saver

        if self.db_path != ":memory:":
            path = Path(self.db_path)
            path.parent.mkdir(parents=True, exist_ok=True)

        self._sync_conn = sqlite3.connect(self.db_path, check_same_thread=False, timeout=30.0)
        self._sync_conn.execute("PRAGMA journal_mode=WAL;")
        self._sync_conn.execute("PRAGMA busy_timeout=30000;")
        self._sync_saver = SqliteSaver(self._sync_conn)
        self._sync_saver.setup()
        logger.info("Initialized SqliteSaver at %s (WAL enabled)", self.db_path)
        return self._sync_saver

    def initialize(self) -> SqliteSaver:
        """Alias for initialize_sync for backward compatibility."""
        return self.initialize_sync()

    @property
    def checkpointer(self) -> BaseCheckpointSaver:
        """Return the active checkpointer."""
        if self._async_saver is not None:
            return self._async_saver
        if self._sync_saver is not None:
            return self._sync_saver
        return self.initialize_sync()

    async def get_async_checkpointer(self) -> AsyncSqliteSaver:
        """Return initialized async checkpointer."""
        if self._async_saver is None:
            return await self.initialize_async()
        return self._async_saver

    async def list_threads(self) -> list[str]:
        """Return all distinct thread IDs stored in the checkpointer."""
        if self.db_path == ":memory:":
            if self._async_conn:
                async with self._async_conn.execute(
                    "SELECT DISTINCT thread_id FROM checkpoints ORDER BY thread_id;"
                ) as cursor:
                    rows = await cursor.fetchall()
                    return [r[0] for r in rows]
            if self._sync_conn:
                cursor = self._sync_conn.cursor()
                cursor.execute("SELECT DISTINCT thread_id FROM checkpoints ORDER BY thread_id;")
                return [r[0] for r in cursor.fetchall()]
            return []

        if not Path(self.db_path).exists():
            return []

        conn = sqlite3.connect(self.db_path)
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT DISTINCT thread_id FROM checkpoints ORDER BY thread_id;")
            return [r[0] for r in cursor.fetchall()]
        except Exception:
            return []
        finally:
            conn.close()

    async def thread_exists(self, thread_id: str) -> bool:
        """Check whether checkpoints exist for the specified thread."""
        threads = await self.list_threads()
        return thread_id in threads

    async def close(self) -> None:
        """Close database connections cleanly."""
        if self._async_conn is not None:
            try:
                await self._async_conn.close()
                logger.info("Closed AsyncSqliteSaver connection for %s", self.db_path)
            except Exception as e:
                logger.warning("Error closing async checkpointer connection: %s", e)
            finally:
                self._async_conn = None
                self._async_saver = None

        if self._sync_conn is not None:
            try:
                self._sync_conn.close()
                logger.info("Closed SqliteSaver connection for %s", self.db_path)
            except Exception as e:
                logger.warning("Error closing sync checkpointer connection: %s", e)
            finally:
                self._sync_conn = None
                self._sync_saver = None
