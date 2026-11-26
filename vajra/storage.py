"""Vajra-Kavach: Local Offline Storage & Database Adapter.

Provides 100% offline persistence using local SQLite or filesystem JSON/CSV.
Replaces any remote cloud databases (Neon, PostgreSQL, S3, Firebase) with
zero-network, air-gapped local storage.
"""
from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from vajra.config import POLICY


class LocalStorageAdapter:
    """Local SQLite-backed storage engine with zero network dependencies."""

    def __init__(self, db_path: str | Path | None = None):
        if db_path is None:
            db_path = POLICY.get("sqlite_path", "./data/vajra_records.db")
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), timeout=30.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode = WAL;")
        conn.execute("PRAGMA synchronous = NORMAL;")
        return conn

    def _init_db(self) -> None:
        with self._get_connection() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS patients (
                    psn TEXT PRIMARY KEY,
                    hash_anchor TEXT,
                    age_band TEXT,
                    stay_days INTEGER,
                    records_count INTEGER DEFAULT 1,
                    created_at TEXT
                );

                CREATE TABLE IF NOT EXISTS records (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    file_hash TEXT,
                    rel_path TEXT,
                    row_loc TEXT,
                    psn TEXT,
                    status TEXT,
                    timestamp TEXT,
                    FOREIGN KEY (psn) REFERENCES patients(psn)
                );

                CREATE TABLE IF NOT EXISTS quarantine_log (
                    file_hash TEXT PRIMARY KEY,
                    original_name TEXT,
                    reason TEXT,
                    timestamp TEXT
                );

                CREATE TABLE IF NOT EXISTS audit_events (
                    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_type TEXT,
                    details TEXT,
                    timestamp TEXT
                );

                CREATE INDEX IF NOT EXISTS idx_records_psn ON records(psn);
                CREATE INDEX IF NOT EXISTS idx_records_file ON records(file_hash);
            """)

    def store_patient(
        self,
        psn: str,
        hash_anchor: str = "",
        age_band: str = "",
        stay_days: int = 0
    ) -> None:
        now = datetime.now(timezone.utc).isoformat()
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO patients (psn, hash_anchor, age_band, stay_days, records_count, created_at)
                VALUES (?, ?, ?, ?, 1, ?)
                ON CONFLICT(psn) DO UPDATE SET
                    records_count = records_count + 1,
                    age_band = COALESCE(NULLIF(excluded.age_band, ''), age_band)
                """,
                (psn, hash_anchor, age_band, stay_days, now)
            )

    def link_record(
        self,
        file_hash: str,
        rel_path: str,
        row_loc: str,
        psn: str,
        status: str = "sanitized"
    ) -> None:
        now = datetime.now(timezone.utc).isoformat()
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO records (file_hash, rel_path, row_loc, psn, status, timestamp)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (file_hash, rel_path, row_loc, psn, status, now)
            )

    def log_quarantine(self, file_hash: str, original_name: str, reason: str) -> None:
        now = datetime.now(timezone.utc).isoformat()
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO quarantine_log (file_hash, original_name, reason, timestamp)
                VALUES (?, ?, ?, ?)
                """,
                (file_hash, original_name, reason, now)
            )

    def log_audit(self, event_type: str, details: Dict[str, Any]) -> None:
        now = datetime.now(timezone.utc).isoformat()
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO audit_events (event_type, details, timestamp)
                VALUES (?, ?, ?)
                """,
                (event_type, json.dumps(details), now)
            )

    def get_summary_stats(self) -> Dict[str, Any]:
        with self._get_connection() as conn:
            total_patients = conn.execute("SELECT COUNT(*) FROM patients").fetchone()[0]
            total_records = conn.execute("SELECT COUNT(*) FROM records").fetchone()[0]
            total_quarantined = conn.execute("SELECT COUNT(*) FROM quarantine_log").fetchone()[0]
            return {
                "total_patients": total_patients,
                "total_records": total_records,
                "total_quarantined": total_quarantined,
                "database_engine": "SQLite 3 (Air-Gapped Local)",
                "db_path": str(self.db_path)
            }

    def export_to_json(self, output_path: str | Path) -> None:
        out_p = Path(output_path)
        out_p.parent.mkdir(parents=True, exist_ok=True)
        stats = self.get_summary_stats()
        with self._get_connection() as conn:
            records = [dict(r) for r in conn.execute("SELECT * FROM records LIMIT 5000").fetchall()]
            quarantine = [dict(r) for r in conn.execute("SELECT * FROM quarantine_log").fetchall()]
        data = {
            "stats": stats,
            "records": records,
            "quarantine": quarantine
        }
        out_p.write_text(json.dumps(data, indent=2), encoding="utf-8")


_STORAGE_INSTANCE: Optional[LocalStorageAdapter] = None


def get_storage(db_path: str | Path | None = None) -> LocalStorageAdapter:
    """Singleton provider for local storage adapter."""
    global _STORAGE_INSTANCE
    if _STORAGE_INSTANCE is None:
        _STORAGE_INSTANCE = LocalStorageAdapter(db_path)
    return _STORAGE_INSTANCE
