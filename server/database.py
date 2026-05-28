"""Persistencia em SQLite: tabelas stations e violations."""

from __future__ import annotations

import json
import os
import sqlite3
import threading
from datetime import datetime


class Database:
    """Gerencia banco SQLite unificado com stations e violations."""

    def __init__(self, db_path: str = "data/tortuga.db"):
        dir_name = os.path.dirname(db_path)
        if dir_name:
            os.makedirs(dir_name, exist_ok=True)
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._lock = threading.Lock()
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._create_tables()

    def _create_tables(self) -> None:
        with self._lock:
            self._conn.executescript("""
                CREATE TABLE IF NOT EXISTS stations (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    camera_url TEXT NOT NULL,
                    esp32_url TEXT NOT NULL,
                    required_epis TEXT NOT NULL,
                    confidence REAL NOT NULL DEFAULT 0.4,
                    enabled INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS violations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    station_id TEXT NOT NULL REFERENCES stations(id),
                    timestamp TEXT NOT NULL,
                    violations TEXT NOT NULL,
                    screenshot_path TEXT,
                    created_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_violations_station
                    ON violations(station_id);
                CREATE INDEX IF NOT EXISTS idx_violations_time
                    ON violations(timestamp);
            """)
            self._conn.commit()

    def seed_from_file(self, path: str) -> None:
        """Carrega estacoes do JSON seed se a tabela estiver vazia."""
        if self.get_station_count() > 0:
            return
        if not os.path.exists(path):
            return
        with open(path, encoding="utf-8") as f:
            stations = json.load(f)
        for s in stations:
            self.insert_station(
                station_id=s["id"],
                name=s["name"],
                camera_url=s["camera_url"],
                esp32_url=s["esp32_url"],
                required_epis=s.get("required_epis", []),
                confidence=s.get("confidence", 0.4),
                enabled=s.get("enabled", True),
            )

    # --- Stations ---

    def insert_station(
        self,
        station_id: str,
        name: str,
        camera_url: str,
        esp32_url: str,
        required_epis: list[str],
        confidence: float = 0.4,
        enabled: bool = True,
    ) -> dict:
        now = datetime.now().isoformat()
        with self._lock:
            self._conn.execute(
                """INSERT INTO stations (id, name, camera_url, esp32_url,
                   required_epis, confidence, enabled, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    station_id, name, camera_url, esp32_url,
                    json.dumps(required_epis), confidence, int(enabled), now,
                ),
            )
            self._conn.commit()
        return self.get_station(station_id)

    def get_station(self, station_id: str) -> dict | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM stations WHERE id = ?", (station_id,),
            ).fetchone()
        if row is None:
            return None
        return self._row_to_station(row)

    def get_all_stations(self) -> list[dict]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM stations ORDER BY created_at",
            ).fetchall()
        return [self._row_to_station(r) for r in rows]

    def get_enabled_stations(self) -> list[dict]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM stations WHERE enabled = 1 ORDER BY created_at",
            ).fetchall()
        return [self._row_to_station(r) for r in rows]

    def update_station(self, station_id: str, **kwargs) -> dict | None:
        station = self.get_station(station_id)
        if station is None:
            return None
        fields = []
        values = []
        for key in ("name", "camera_url", "esp32_url", "confidence"):
            if key in kwargs:
                fields.append(f"{key} = ?")
                values.append(kwargs[key])
        if "required_epis" in kwargs:
            fields.append("required_epis = ?")
            values.append(json.dumps(kwargs["required_epis"]))
        if "enabled" in kwargs:
            fields.append("enabled = ?")
            values.append(int(kwargs["enabled"]))
        if not fields:
            return station
        values.append(station_id)
        with self._lock:
            self._conn.execute(
                f"UPDATE stations SET {', '.join(fields)} WHERE id = ?",
                values,
            )
            self._conn.commit()
        return self.get_station(station_id)

    def delete_station(self, station_id: str) -> bool:
        with self._lock:
            cursor = self._conn.execute(
                "DELETE FROM stations WHERE id = ?", (station_id,),
            )
            self._conn.commit()
        return cursor.rowcount > 0

    def get_station_count(self) -> int:
        with self._lock:
            return self._conn.execute(
                "SELECT COUNT(*) FROM stations",
            ).fetchone()[0]

    # --- Violations ---

    def insert_violation(
        self,
        station_id: str,
        violations: list[str],
        screenshot_path: str | None = None,
    ) -> None:
        now = datetime.now().isoformat()
        with self._lock:
            self._conn.execute(
                """INSERT INTO violations
                   (station_id, timestamp, violations, screenshot_path, created_at)
                   VALUES (?, ?, ?, ?, ?)""",
                (station_id, now, json.dumps(violations), screenshot_path, now),
            )
            self._conn.commit()

    def get_violations(
        self,
        limit: int = 50,
        station_id: str | None = None,
    ) -> list[dict]:
        with self._lock:
            if station_id:
                cursor = self._conn.execute(
                    """SELECT * FROM violations WHERE station_id = ?
                       ORDER BY id DESC LIMIT ?""",
                    (station_id, limit),
                )
            else:
                cursor = self._conn.execute(
                    "SELECT * FROM violations ORDER BY id DESC LIMIT ?",
                    (limit,),
                )
            rows = cursor.fetchall()
        return [self._row_to_violation(r) for r in rows]

    def get_violation_count(self, station_id: str | None = None) -> int:
        with self._lock:
            if station_id:
                cursor = self._conn.execute(
                    "SELECT COUNT(*) FROM violations WHERE station_id = ?",
                    (station_id,),
                )
            else:
                cursor = self._conn.execute("SELECT COUNT(*) FROM violations")
            return cursor.fetchone()[0]

    def get_violations_by_date(
        self,
        start: str,
        end: str,
        station_id: str | None = None,
    ) -> list[dict]:
        with self._lock:
            if station_id:
                cursor = self._conn.execute(
                    """SELECT * FROM violations
                       WHERE station_id = ? AND timestamp BETWEEN ? AND ?
                       ORDER BY id DESC""",
                    (station_id, start, end),
                )
            else:
                cursor = self._conn.execute(
                    """SELECT * FROM violations
                       WHERE timestamp BETWEEN ? AND ?
                       ORDER BY id DESC""",
                    (start, end),
                )
            rows = cursor.fetchall()
        return [self._row_to_violation(r) for r in rows]

    def close(self) -> None:
        self._conn.close()

    # --- Helpers ---

    @staticmethod
    def _row_to_station(row) -> dict:
        return {
            "id": row["id"],
            "name": row["name"],
            "camera_url": row["camera_url"],
            "esp32_url": row["esp32_url"],
            "required_epis": json.loads(row["required_epis"]),
            "confidence": row["confidence"],
            "enabled": bool(row["enabled"]),
            "created_at": row["created_at"],
        }

    @staticmethod
    def _row_to_violation(row) -> dict:
        return {
            "id": row["id"],
            "station_id": row["station_id"],
            "timestamp": row["timestamp"],
            "violations": json.loads(row["violations"]),
            "screenshot_path": row["screenshot_path"],
            "created_at": row["created_at"],
        }
