"""
DiskSentinel - Core Database Module

Provides SQLite database operations for disk scanning, snapshot management,
file tracking, change detection, and real-time watch event logging.
"""

import os
import sqlite3
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional


# Default database path: ~/.disksentinel/data.db
_DEFAULT_DB_DIR = os.path.join(Path.home(), ".disksentinel")
_DEFAULT_DB_PATH = os.path.join(_DEFAULT_DB_DIR, "data.db")


# ---------------------------------------------------------------------------
# SQL DDL – table creation
# ---------------------------------------------------------------------------

_CREATE_TABLES_SQL = """
-- 扫描配置
CREATE TABLE IF NOT EXISTS scan_configs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    path        TEXT    NOT NULL,
    exclude_patterns TEXT DEFAULT '[]',   -- JSON array of glob patterns
    schedule_type   TEXT NOT NULL DEFAULT 'manual',  -- manual / interval / cron
    schedule_value  TEXT DEFAULT '',
    enabled     INTEGER NOT NULL DEFAULT 1,
    created_at  TEXT    NOT NULL DEFAULT (datetime('now','localtime')),
    updated_at  TEXT    NOT NULL DEFAULT (datetime('now','localtime'))
);

-- 快照记录
CREATE TABLE IF NOT EXISTS snapshots (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    config_id   INTEGER NOT NULL,
    file_count  INTEGER NOT NULL DEFAULT 0,
    total_size  INTEGER NOT NULL DEFAULT 0,  -- bytes
    duration    REAL    NOT NULL DEFAULT 0.0, -- seconds
    created_at  TEXT    NOT NULL DEFAULT (datetime('now','localtime')),
    FOREIGN KEY (config_id) REFERENCES scan_configs(id) ON DELETE CASCADE
);

-- 文件条目
CREATE TABLE IF NOT EXISTS file_entries (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    snapshot_id     INTEGER NOT NULL,
    path            TEXT    NOT NULL,
    size            INTEGER NOT NULL DEFAULT 0,
    modified_time   TEXT    NOT NULL,
    is_dir          INTEGER NOT NULL DEFAULT 0,
    FOREIGN KEY (snapshot_id) REFERENCES snapshots(id) ON DELETE CASCADE
);

-- 变化记录
CREATE TABLE IF NOT EXISTS changes (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    snapshot_id     INTEGER NOT NULL,
    change_type     TEXT    NOT NULL,  -- added / removed / modified / moved
    path            TEXT    NOT NULL,
    size            INTEGER DEFAULT 0,
    old_size        INTEGER DEFAULT 0,
    created_at      TEXT    NOT NULL DEFAULT (datetime('now','localtime')),
    FOREIGN KEY (snapshot_id) REFERENCES snapshots(id) ON DELETE CASCADE
);

-- 实时监控事件
CREATE TABLE IF NOT EXISTS watch_events (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    config_id   INTEGER NOT NULL,
    event_type  TEXT    NOT NULL,       -- created / deleted / modified / moved
    src_path    TEXT    NOT NULL,
    dest_path   TEXT    DEFAULT '',
    size        INTEGER DEFAULT 0,
    created_at  TEXT    NOT NULL DEFAULT (datetime('now','localtime')),
    FOREIGN KEY (config_id) REFERENCES scan_configs(id) ON DELETE CASCADE
);

-- Indexes for common queries
CREATE INDEX IF NOT EXISTS idx_snapshots_config_id ON snapshots(config_id);
CREATE INDEX IF NOT EXISTS idx_snapshots_created_at ON snapshots(created_at);
CREATE INDEX IF NOT EXISTS idx_file_entries_snapshot_id ON file_entries(snapshot_id);
CREATE INDEX IF NOT EXISTS idx_changes_snapshot_id ON changes(snapshot_id);
CREATE INDEX IF NOT EXISTS idx_changes_created_at ON changes(created_at);
CREATE INDEX IF NOT EXISTS idx_watch_events_config_id ON watch_events(config_id);
CREATE INDEX IF NOT EXISTS idx_watch_events_created_at ON watch_events(created_at);
"""


class DatabaseManager:
    """Manages all SQLite database operations for DiskSentinel.

    Usage::

        db = DatabaseManager()
        db.init_db()
        # ... call methods ...
        db.close()

    Or as a context manager::

        with DatabaseManager() as db:
            db.init_db()
            # ... call methods ...
    """

    def __init__(self, db_path: Optional[str] = None):
        """Initialise the DatabaseManager.

        Args:
            db_path: Path to the SQLite database file. Defaults to
                     ``~/.disksentinel/data.db``.
        """
        self.db_path = db_path or _DEFAULT_DB_PATH
        self._connection: Optional[sqlite3.Connection] = None

    # ------------------------------------------------------------------
    # Context manager support
    # ------------------------------------------------------------------

    def __enter__(self) -> "DatabaseManager":
        """Enter the context manager; opens a database connection."""
        self._ensure_dir()
        self._connection = sqlite3.connect(self.db_path, check_same_thread=False)
        self._connection.row_factory = sqlite3.Row
        self._connection.execute("PRAGMA journal_mode=WAL;")
        self._connection.execute("PRAGMA foreign_keys=ON;")
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Exit the context manager; closes the database connection."""
        if self._connection:
            self._connection.close()
            self._connection = None

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _ensure_dir(self) -> None:
        """Create the directory for the database file if it does not exist."""
        db_dir = os.path.dirname(self.db_path)
        if db_dir:
            os.makedirs(db_dir, exist_ok=True)

    def _get_connection(self) -> sqlite3.Connection:
        """Return the active connection, creating one lazily if needed.

        Returns:
            An open ``sqlite3.Connection`` with ``Row`` row factory.
        """
        if self._connection is None:
            self._ensure_dir()
            self._connection = sqlite3.connect(self.db_path, check_same_thread=False)
            self._connection.row_factory = sqlite3.Row
            self._connection.execute("PRAGMA journal_mode=WAL;")
            self._connection.execute("PRAGMA foreign_keys=ON;")
        return self._connection

    def _execute(self, sql: str, params: tuple = ()) -> sqlite3.Cursor:
        """Execute a single SQL statement and return the cursor.

        Args:
            sql: SQL statement with ``?`` placeholders.
            params: Tuple of parameter values.

        Returns:
            The ``sqlite3.Cursor`` after execution.
        """
        conn = self._get_connection()
        return conn.execute(sql, params)

    def _commit(self) -> None:
        """Commit the current transaction."""
        conn = self._get_connection()
        conn.commit()

    # ------------------------------------------------------------------
    # Public query helpers (used by snapshot, reporter, UI modules)
    # ------------------------------------------------------------------

    def execute_insert(self, sql: str, params: tuple = ()) -> int:
        """Execute an INSERT statement and return the lastrowid."""
        conn = self._get_connection()
        cursor = conn.execute(sql, params)
        conn.commit()
        return cursor.lastrowid

    def execute_query(self, sql: str, params: tuple = ()) -> list[dict]:
        """Execute a SELECT statement and return rows as list of dicts."""
        conn = self._get_connection()
        cursor = conn.execute(sql, params)
        columns = [desc[0] for desc in cursor.description] if cursor.description else []
        return [dict(zip(columns, row)) for row in cursor.fetchall()]

    def fetch_one(self, sql: str, params: tuple = ()):
        """Execute a SELECT statement and return a single row as dict, or None."""
        conn = self._get_connection()
        cursor = conn.execute(sql, params)
        row = cursor.fetchone()
        if row is None:
            return None
        columns = [desc[0] for desc in cursor.description] if cursor.description else []
        return dict(zip(columns, row))

    def fetch_all(self, sql: str, params: tuple = ()) -> list[dict]:
        """Alias for execute_query — fetch all rows as list of dicts."""
        return self.execute_query(sql, params)

    def execute_many(self, sql: str, params_list: list[tuple]) -> None:
        """Execute a SQL statement with multiple parameter sets (batch)."""
        conn = self._get_connection()
        conn.executemany(sql, params_list)
        conn.commit()

    # ------------------------------------------------------------------
    # Database initialisation
    # ------------------------------------------------------------------

    def init_db(self) -> None:
        """Create all required tables and indexes if they do not already exist.

        This method is idempotent – calling it multiple times is safe.
        """
        conn = self._get_connection()
        conn.executescript(_CREATE_TABLES_SQL)
        conn.commit()

    # ------------------------------------------------------------------
    # Scan configuration CRUD
    # ------------------------------------------------------------------

    def add_scan_config(
        self,
        path: str,
        exclude_patterns: Optional[list] = None,
        schedule_type: str = "manual",
        schedule_value: str = "",
    ) -> int:
        """Add a new scan configuration.

        Args:
            path: The root directory path to scan.
            exclude_patterns: List of glob patterns to exclude (e.g. ``["*.tmp", "__pycache__"]``).
            schedule_type: Schedule type – ``manual``, ``interval``, or ``cron``.
            schedule_value: Schedule parameter (e.g. ``"3600"`` for 1-hour interval).

        Returns:
            The integer ``id`` of the newly created scan configuration.
        """
        patterns_json = json.dumps(exclude_patterns or [], ensure_ascii=False)
        cursor = self._execute(
            """
            INSERT INTO scan_configs (path, exclude_patterns, schedule_type, schedule_value)
            VALUES (?, ?, ?, ?)
            """,
            (path, patterns_json, schedule_type, schedule_value),
        )
        self._commit()
        return cursor.lastrowid  # type: ignore[return-value]

    def get_scan_configs(self) -> list[dict]:
        """Return all scan configurations ordered by id.

        Returns:
            A list of dictionaries, each representing a scan configuration row.
        """
        cursor = self._execute(
            "SELECT * FROM scan_configs ORDER BY id"
        )
        return [dict(row) for row in cursor.fetchall()]

    def update_scan_config(
        self,
        config_id: int,
        path: Optional[str] = None,
        exclude_patterns: Optional[list] = None,
        schedule_type: Optional[str] = None,
        schedule_value: Optional[str] = None,
        enabled: Optional[int] = None,
    ) -> bool:
        """Update fields of an existing scan configuration.

        Only the arguments that are not ``None`` will be updated.

        Args:
            config_id: The id of the scan configuration to update.
            path: New root directory path.
            exclude_patterns: New list of exclude glob patterns.
            schedule_type: New schedule type.
            schedule_value: New schedule value.
            enabled: ``1`` to enable, ``0`` to disable.

        Returns:
            ``True`` if a row was updated, ``False`` otherwise.
        """
        updates: list[str] = []
        params: list = []

        if path is not None:
            updates.append("path = ?")
            params.append(path)
        if exclude_patterns is not None:
            updates.append("exclude_patterns = ?")
            params.append(json.dumps(exclude_patterns, ensure_ascii=False))
        if schedule_type is not None:
            updates.append("schedule_type = ?")
            params.append(schedule_type)
        if schedule_value is not None:
            updates.append("schedule_value = ?")
            params.append(schedule_value)
        if enabled is not None:
            updates.append("enabled = ?")
            params.append(enabled)

        if not updates:
            return False

        updates.append("updated_at = datetime('now','localtime')")
        params.append(config_id)

        sql = f"UPDATE scan_configs SET {', '.join(updates)} WHERE id = ?"
        cursor = self._execute(sql, tuple(params))
        self._commit()
        return cursor.rowcount > 0

    def delete_scan_config(self, config_id: int) -> bool:
        """Delete a scan configuration by id.

        Args:
            config_id: The id of the scan configuration to delete.

        Returns:
            ``True`` if a row was deleted, ``False`` otherwise.
        """
        cursor = self._execute(
            "DELETE FROM scan_configs WHERE id = ?", (config_id,)
        )
        self._commit()
        return cursor.rowcount > 0

    # ------------------------------------------------------------------
    # Snapshots
    # ------------------------------------------------------------------

    def create_snapshot(
        self,
        config_id: int,
        file_count: int = 0,
        total_size: int = 0,
        duration: float = 0.0,
    ) -> int:
        """Create a new snapshot record.

        Args:
            config_id: The scan configuration this snapshot belongs to.
            file_count: Number of files recorded in this snapshot.
            total_size: Total size in bytes of all files in the snapshot.
            duration: Wall-clock duration of the scan in seconds.

        Returns:
            The integer ``id`` of the newly created snapshot.
        """
        cursor = self._execute(
            """
            INSERT INTO snapshots (config_id, file_count, total_size, duration)
            VALUES (?, ?, ?, ?)
            """,
            (config_id, file_count, total_size, duration),
        )
        self._commit()
        return cursor.lastrowid  # type: ignore[return-value]

    def get_snapshots(self, limit: int = 20, offset: int = 0) -> list[dict]:
        """Retrieve snapshots with pagination, newest first.

        Args:
            limit: Maximum number of snapshots to return.
            offset: Number of snapshots to skip (for pagination).

        Returns:
            A list of snapshot dictionaries.
        """
        cursor = self._execute(
            """
            SELECT s.*, sc.path AS config_path
            FROM snapshots s
            JOIN scan_configs sc ON s.config_id = sc.id
            ORDER BY s.created_at DESC
            LIMIT ? OFFSET ?
            """,
            (limit, offset),
        )
        return [dict(row) for row in cursor.fetchall()]

    def get_latest_snapshot(self, config_id: int) -> Optional[dict]:
        """Return the most recent snapshot for a given configuration.

        Args:
            config_id: The scan configuration id.

        Returns:
            A dictionary representing the latest snapshot, or ``None`` if no
            snapshots exist for the given configuration.
        """
        cursor = self._execute(
            """
            SELECT * FROM snapshots
            WHERE config_id = ?
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (config_id,),
        )
        row = cursor.fetchone()
        return dict(row) if row else None

    # ------------------------------------------------------------------
    # File entries
    # ------------------------------------------------------------------

    def add_file_entry(
        self,
        snapshot_id: int,
        path: str,
        size: int,
        modified_time: str,
        is_dir: bool = False,
    ) -> int:
        """Add a single file (or directory) entry to a snapshot.

        Args:
            snapshot_id: The snapshot this entry belongs to.
            path: Full path of the file or directory.
            size: Size in bytes.
            modified_time: Modification timestamp as an ISO-8601 string.
            is_dir: ``True`` if this entry represents a directory.

        Returns:
            The integer ``id`` of the newly created file entry.
        """
        cursor = self._execute(
            """
            INSERT INTO file_entries (snapshot_id, path, size, modified_time, is_dir)
            VALUES (?, ?, ?, ?, ?)
            """,
            (snapshot_id, path, size, modified_time, 1 if is_dir else 0),
        )
        self._commit()
        return cursor.lastrowid  # type: ignore[return-value]

    def add_file_entries_bulk(self, entries: list[tuple]) -> None:
        """Bulk-insert file entries for better performance.

        Args:
            entries: A list of tuples ``(snapshot_id, path, size, modified_time, is_dir)``.
        """
        conn = self._get_connection()
        conn.executemany(
            """
            INSERT INTO file_entries (snapshot_id, path, size, modified_time, is_dir)
            VALUES (?, ?, ?, ?, ?)
            """,
            entries,
        )
        conn.commit()

    # ------------------------------------------------------------------
    # Changes
    # ------------------------------------------------------------------

    def add_change(
        self,
        snapshot_id: int,
        change_type: str,
        path: str,
        size: int = 0,
        old_size: int = 0,
    ) -> int:
        """Record a detected change between snapshots.

        Args:
            snapshot_id: The snapshot during which the change was detected.
            change_type: One of ``added``, ``removed``, ``modified``, or ``moved``.
            path: File path of the changed item.
            size: New size in bytes (``0`` for deletions).
            old_size: Previous size in bytes (``0`` for additions).

        Returns:
            The integer ``id`` of the newly created change record.
        """
        cursor = self._execute(
            """
            INSERT INTO changes (snapshot_id, change_type, path, size, old_size)
            VALUES (?, ?, ?, ?, ?)
            """,
            (snapshot_id, change_type, path, size, old_size),
        )
        self._commit()
        return cursor.lastrowid  # type: ignore[return-value]

    def add_changes_bulk(self, changes: list[tuple]) -> None:
        """Bulk-insert change records for better performance.

        Args:
            changes: A list of tuples ``(snapshot_id, change_type, path, size, old_size)``.
        """
        conn = self._get_connection()
        conn.executemany(
            """
            INSERT INTO changes (snapshot_id, change_type, path, size, old_size)
            VALUES (?, ?, ?, ?, ?)
            """,
            changes,
        )
        conn.commit()

    def get_changes_for_snapshot(self, snapshot_id: int) -> list[dict]:
        """Retrieve all change records for a given snapshot.

        Args:
            snapshot_id: The snapshot id to query.

        Returns:
            A list of change dictionaries ordered by creation time.
        """
        cursor = self._execute(
            """
            SELECT * FROM changes
            WHERE snapshot_id = ?
            ORDER BY created_at
            """,
            (snapshot_id,),
        )
        return [dict(row) for row in cursor.fetchall()]

    # ------------------------------------------------------------------
    # Watch events (real-time monitoring)
    # ------------------------------------------------------------------

    def add_watch_event(
        self,
        config_id: int,
        event_type: str,
        src_path: str,
        dest_path: str = "",
        size: int = 0,
    ) -> int:
        """Log a single real-time filesystem watch event.

        Args:
            config_id: The scan configuration that owns the watcher.
            event_type: One of ``created``, ``deleted``, ``modified``, or ``moved``.
            src_path: Source path of the event.
            dest_path: Destination path (only meaningful for ``moved`` events).
            size: File size in bytes at the time of the event.

        Returns:
            The integer ``id`` of the newly created watch event.
        """
        cursor = self._execute(
            """
            INSERT INTO watch_events (config_id, event_type, src_path, dest_path, size)
            VALUES (?, ?, ?, ?, ?)
            """,
            (config_id, event_type, src_path, dest_path, size),
        )
        self._commit()
        return cursor.lastrowid  # type: ignore[return-value]

    def get_watch_events(self, limit: int = 50, offset: int = 0) -> list[dict]:
        """Retrieve watch events with pagination, newest first.

        Args:
            limit: Maximum number of events to return.
            offset: Number of events to skip.

        Returns:
            A list of watch-event dictionaries.
        """
        cursor = self._execute(
            """
            SELECT we.*, sc.path AS config_path
            FROM watch_events we
            JOIN scan_configs sc ON we.config_id = sc.id
            ORDER BY we.created_at DESC
            LIMIT ? OFFSET ?
            """,
            (limit, offset),
        )
        return [dict(row) for row in cursor.fetchall()]

    # ------------------------------------------------------------------
    # Dashboard statistics
    # ------------------------------------------------------------------

    def get_dashboard_stats(self) -> dict:
        """Compute aggregate statistics for the dashboard view.

        Returns:
            A dictionary with the following keys:

            - ``total_configs`` – number of scan configurations
            - ``total_snapshots`` – total snapshot count
            - ``total_files`` – file count from the latest snapshot across all configs
            - ``total_size`` – total size (bytes) from the latest snapshot
            - ``changes_today`` – number of changes recorded today
            - ``watch_events_today`` – number of watch events recorded today
            - ``last_scan_time`` – timestamp of the most recent snapshot
        """
        stats: dict = {
            "total_configs": 0,
            "total_snapshots": 0,
            "total_files": 0,
            "total_size": 0,
            "changes_today": 0,
            "watch_events_today": 0,
            "last_scan_time": None,
        }

        # Total configs
        row = self._execute("SELECT COUNT(*) AS cnt FROM scan_configs").fetchone()
        stats["total_configs"] = row["cnt"] if row else 0

        # Total snapshots
        row = self._execute("SELECT COUNT(*) AS cnt FROM snapshots").fetchone()
        stats["total_snapshots"] = row["cnt"] if row else 0

        # Aggregate from the latest snapshot per config
        row = self._execute(
            """
            SELECT COALESCE(SUM(s.file_count), 0) AS total_files,
                   COALESCE(SUM(s.total_size), 0) AS total_size
            FROM snapshots s
            WHERE s.id IN (
                SELECT MAX(id) FROM snapshots GROUP BY config_id
            )
            """
        ).fetchone()
        if row:
            stats["total_files"] = row["total_files"]
            stats["total_size"] = row["total_size"]

        # Changes today
        row = self._execute(
            """
            SELECT COUNT(*) AS cnt FROM changes
            WHERE date(created_at) = date('now','localtime')
            """
        ).fetchone()
        stats["changes_today"] = row["cnt"] if row else 0

        # Watch events today
        row = self._execute(
            """
            SELECT COUNT(*) AS cnt FROM watch_events
            WHERE date(created_at) = date('now','localtime')
            """
        ).fetchone()
        stats["watch_events_today"] = row["cnt"] if row else 0

        # Last scan time
        row = self._execute(
            "SELECT created_at FROM snapshots ORDER BY created_at DESC LIMIT 1"
        ).fetchone()
        if row:
            stats["last_scan_time"] = row["created_at"]

        return stats

    # ------------------------------------------------------------------
    # Data cleanup
    # ------------------------------------------------------------------

    def cleanup_old_data(self, days_to_keep: int = 90) -> dict:
        """Delete records older than the specified retention period.

        Data is removed from ``snapshots``, ``file_entries``, ``changes``,
        and ``watch_events`` tables.  Scan configurations are **not** deleted.

        Args:
            days_to_keep: Number of days of history to retain. Records with a
                          ``created_at`` timestamp older than this will be
                          permanently removed.

        Returns:
            A dictionary summarising the number of deleted rows per table:

            - ``deleted_snapshots``
            - ``deleted_file_entries``
            - ``deleted_changes``
            - ``deleted_watch_events``
        """
        cutoff = (datetime.now() - timedelta(days=days_to_keep)).isoformat()

        # Find snapshot ids to delete (for cascading file_entries & changes)
        old_snapshot_ids = [
            row["id"]
            for row in self._execute(
                "SELECT id FROM snapshots WHERE created_at < ?", (cutoff,)
            ).fetchall()
        ]

        deleted_file_entries = 0
        deleted_changes = 0
        deleted_snapshots = 0

        if old_snapshot_ids:
            placeholders = ",".join("?" for _ in old_snapshot_ids)

            cur = self._execute(
                f"DELETE FROM file_entries WHERE snapshot_id IN ({placeholders})",
                tuple(old_snapshot_ids),
            )
            deleted_file_entries = cur.rowcount

            cur = self._execute(
                f"DELETE FROM changes WHERE snapshot_id IN ({placeholders})",
                tuple(old_snapshot_ids),
            )
            deleted_changes = cur.rowcount

            cur = self._execute(
                f"DELETE FROM snapshots WHERE id IN ({placeholders})",
                tuple(old_snapshot_ids),
            )
            deleted_snapshots = cur.rowcount

        # Watch events (not tied to snapshots)
        cur = self._execute(
            "DELETE FROM watch_events WHERE created_at < ?", (cutoff,)
        )
        deleted_watch_events = cur.rowcount

        self._commit()

        return {
            "deleted_snapshots": deleted_snapshots,
            "deleted_file_entries": deleted_file_entries,
            "deleted_changes": deleted_changes,
            "deleted_watch_events": deleted_watch_events,
        }

    # ------------------------------------------------------------------
    # Lifecycle helpers
    # ------------------------------------------------------------------

    def close(self) -> None:
        """Close the database connection if it is currently open."""
        if self._connection:
            self._connection.close()
            self._connection = None
