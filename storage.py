"""SQLite-backed repo registry and audit log."""
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime

DB_PATH = os.getenv("DB_PATH", "/tmp/contextbot.db")


@contextmanager
def _db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init():
    with _db() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS repos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                workspace_id TEXT NOT NULL,
                github_url TEXT NOT NULL,
                local_path TEXT NOT NULL,
                name TEXT NOT NULL,
                file_count INTEGER DEFAULT 0,
                redaction_count INTEGER DEFAULT 0,
                indexed_at TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(workspace_id, github_url)
            );
            CREATE TABLE IF NOT EXISTS audit_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                workspace_id TEXT NOT NULL,
                repo_name TEXT NOT NULL,
                pattern TEXT NOT NULL,
                file_path TEXT NOT NULL,
                ts TEXT DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS active_repo (
                workspace_id TEXT PRIMARY KEY,
                github_url TEXT NOT NULL
            );
        """)


def upsert_repo(workspace_id: str, github_url: str, local_path: str, name: str,
                file_count: int = 0, redaction_count: int = 0):
    with _db() as conn:
        conn.execute("""
            INSERT INTO repos (workspace_id, github_url, local_path, name, file_count,
                               redaction_count, indexed_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(workspace_id, github_url) DO UPDATE SET
                local_path=excluded.local_path,
                file_count=excluded.file_count,
                redaction_count=excluded.redaction_count,
                indexed_at=excluded.indexed_at
        """, (workspace_id, github_url, local_path, name, file_count,
              redaction_count, datetime.utcnow().isoformat()))
        conn.execute("""
            INSERT OR REPLACE INTO active_repo (workspace_id, github_url)
            VALUES (?, ?)
        """, (workspace_id, github_url))


def set_active(workspace_id: str, github_url: str):
    with _db() as conn:
        conn.execute("""
            INSERT OR REPLACE INTO active_repo (workspace_id, github_url) VALUES (?, ?)
        """, (workspace_id, github_url))


def get_active_repo(workspace_id: str) -> dict | None:
    with _db() as conn:
        row = conn.execute("""
            SELECT r.* FROM repos r
            JOIN active_repo a ON a.github_url = r.github_url
              AND a.workspace_id = r.workspace_id
            WHERE r.workspace_id = ?
        """, (workspace_id,)).fetchone()
    return dict(row) if row else None


def get_repos(workspace_id: str) -> list[dict]:
    with _db() as conn:
        rows = conn.execute(
            "SELECT * FROM repos WHERE workspace_id = ? ORDER BY created_at DESC",
            (workspace_id,)
        ).fetchall()
    return [dict(r) for r in rows]


def log_redaction(workspace_id: str, repo_name: str, pattern: str, file_path: str):
    with _db() as conn:
        conn.execute("""
            INSERT INTO audit_log (workspace_id, repo_name, pattern, file_path)
            VALUES (?, ?, ?, ?)
        """, (workspace_id, repo_name, pattern, file_path))


def get_audit_log(workspace_id: str, limit: int = 20) -> list[dict]:
    with _db() as conn:
        rows = conn.execute("""
            SELECT * FROM audit_log WHERE workspace_id = ?
            ORDER BY ts DESC LIMIT ?
        """, (workspace_id, limit)).fetchall()
    return [dict(r) for r in rows]


def total_redactions(workspace_id: str) -> int:
    with _db() as conn:
        row = conn.execute(
            "SELECT COALESCE(SUM(redaction_count), 0) FROM repos WHERE workspace_id = ?",
            (workspace_id,)
        ).fetchone()
    return row[0] if row else 0
