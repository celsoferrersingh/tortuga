"""
events_store.py — Camada de dados da Fase 3 · Projeto Tortuga
Tabelas: workers (perfis), belts (cintos ESP32 + operador ativo via QR),
zones (zonas de risco com nível) e safety_events. Todo o estado no servidor;
o ESP só guarda um device_id e recebe JSON curto (bateria).
"""
from __future__ import annotations
import hashlib, json, os, sqlite3, threading
from datetime import datetime, timedelta

EVENT_TYPES = ["EPI_AUSENTE", "POSTURA_RISCO", "ZONA_CRITICA", "QUEDA", "FADIGA"]
DEFAULT_EPIS = ["Hardhat", "Safety Vest", "Safety Glasses"]


class EventStore:
    def __init__(self, db_path="data/tortuga.db"):
        d = os.path.dirname(db_path)
        if d: os.makedirs(d, exist_ok=True)
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._lock = threading.Lock()
        self._create()

    def _create(self):
        with self._lock:
            self._conn.executescript("""
                CREATE TABLE IF NOT EXISTS workers (
                    worker_id TEXT PRIMARY KEY, name TEXT NOT NULL, area TEXT NOT NULL,
                    turno TEXT NOT NULL, shifts INTEGER NOT NULL DEFAULT 0,
                    required_epis TEXT NOT NULL DEFAULT '[]', confidence REAL NOT NULL DEFAULT 0.4);
                CREATE TABLE IF NOT EXISTS belts (
                    device_id TEXT PRIMARY KEY, name TEXT NOT NULL, station_id TEXT,
                    active_worker_id TEXT, updated_at TEXT, esp32_url TEXT);
                CREATE TABLE IF NOT EXISTS belt_status (
                    device_id TEXT PRIMARY KEY, status TEXT, severity TEXT,
                    message TEXT, epi TEXT, updated_at TEXT);
                CREATE TABLE IF NOT EXISTS zones (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, station_id TEXT,
                    level TEXT NOT NULL DEFAULT 'alta', points TEXT NOT NULL DEFAULT '[]',
                    required_epis TEXT NOT NULL DEFAULT '[]', enabled INTEGER NOT NULL DEFAULT 1);
                CREATE TABLE IF NOT EXISTS area_levels (
                    area TEXT PRIMARY KEY, level TEXT NOT NULL, updated_at TEXT);
                CREATE TABLE IF NOT EXISTS safety_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, worker_id TEXT NOT NULL, station_id TEXT,
                    area TEXT, turno TEXT, type TEXT NOT NULL, epi TEXT, severity TEXT NOT NULL,
                    timestamp TEXT NOT NULL);
                CREATE INDEX IF NOT EXISTS idx_ev_worker ON safety_events(worker_id);
                CREATE INDEX IF NOT EXISTS idx_ev_time ON safety_events(timestamp);
                CREATE INDEX IF NOT EXISTS idx_ev_sev ON safety_events(severity);
                CREATE TABLE IF NOT EXISTS audit_chain (
                    seq INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT NOT NULL,
                    payload TEXT NOT NULL, prev_hash TEXT NOT NULL, hash TEXT NOT NULL);
            """)
            # migração p/ bancos já existentes: adiciona esp32_url em belts se faltar
            try:
                self._conn.execute("ALTER TABLE belts ADD COLUMN esp32_url TEXT")
            except Exception:
                pass
            self._conn.commit()

    # perfis
    def upsert_worker(self, worker_id, name, area, turno, shifts=0, required_epis=None, confidence=0.4):
        epis = json.dumps(required_epis if required_epis is not None else DEFAULT_EPIS)
        with self._lock:
            self._conn.execute("""INSERT INTO workers (worker_id,name,area,turno,shifts,required_epis,confidence)
                VALUES (?,?,?,?,?,?,?) ON CONFLICT(worker_id) DO UPDATE SET name=excluded.name,
                area=excluded.area, turno=excluded.turno, shifts=excluded.shifts,
                required_epis=excluded.required_epis, confidence=excluded.confidence""",
                (worker_id, name, area, turno, shifts, epis, confidence))
            self._conn.commit()

    def update_profile(self, worker_id, **kw):
        sets, vals = [], []
        for k in ("name","area","turno","confidence"):
            if k in kw: sets.append(k+"=?"); vals.append(kw[k])
        if "required_epis" in kw: sets.append("required_epis=?"); vals.append(json.dumps(kw["required_epis"]))
        if not sets: return
        vals.append(worker_id)
        with self._lock:
            self._conn.execute("UPDATE workers SET "+",".join(sets)+" WHERE worker_id=?", vals); self._conn.commit()

    def get_roster(self):
        with self._lock:
            rows = self._conn.execute("SELECT * FROM workers ORDER BY worker_id").fetchall()
        return [self._worker(r) for r in rows]

    def get_profile(self, worker_id):
        with self._lock:
            r = self._conn.execute("SELECT * FROM workers WHERE worker_id=?", (worker_id,)).fetchone()
        return self._worker(r) if r else None

    @staticmethod
    def _worker(r):
        d = dict(r); d["required_epis"] = json.loads(r["required_epis"]); return d

    # cintos + QR
    def upsert_belt(self, device_id, name, station_id=None):
        with self._lock:
            self._conn.execute("""INSERT INTO belts (device_id,name,station_id,updated_at) VALUES (?,?,?,?)
                ON CONFLICT(device_id) DO UPDATE SET name=excluded.name, station_id=excluded.station_id""",
                (device_id, name, station_id, datetime.now().isoformat()))
            self._conn.commit()

    def assign(self, device_id, worker_id):
        with self._lock:
            self._conn.execute("UPDATE belts SET active_worker_id=?, updated_at=? WHERE device_id=?",
                (worker_id, datetime.now().isoformat(), device_id)); self._conn.commit()
        return self.get_belt(device_id)

    def get_belt(self, device_id):
        with self._lock:
            r = self._conn.execute("SELECT * FROM belts WHERE device_id=?", (device_id,)).fetchone()
        return dict(r) if r else None

    def list_belts(self):
        with self._lock:
            rows = self._conn.execute("SELECT * FROM belts ORDER BY device_id").fetchall()
        return [dict(r) for r in rows]

    def active_worker(self, device_id=None, station_id=None):
        with self._lock:
            if device_id:
                r = self._conn.execute("SELECT active_worker_id a FROM belts WHERE device_id=?", (device_id,)).fetchone()
            else:
                r = self._conn.execute("SELECT active_worker_id a FROM belts WHERE station_id=?", (station_id,)).fetchone()
        return r["a"] if r else None

    def belt_for_station(self, station_id):
        with self._lock:
            r = self._conn.execute("SELECT device_id FROM belts WHERE station_id=? LIMIT 1", (station_id,)).fetchone()
        return r["device_id"] if r else None

    # URL HTTP do ESP32 do cinto (modelo PUSH: o servidor manda o alerta pro IP)
    def set_belt_esp(self, device_id, esp32_url):
        with self._lock:
            self._conn.execute("UPDATE belts SET esp32_url=? WHERE device_id=?",
                               (esp32_url, device_id)); self._conn.commit()

    def esp_for_station(self, station_id):
        with self._lock:
            r = self._conn.execute(
                "SELECT esp32_url FROM belts WHERE station_id=? AND esp32_url IS NOT NULL AND esp32_url<>'' LIMIT 1",
                (station_id,)).fetchone()
        return r["esp32_url"] if r else None

    # estado pendente do cinto (modelo PULL ultra-baixo-consumo: o ESP consulta)
    def set_belt_status(self, device_id, severity, message=None, epi=None):
        with self._lock:
            self._conn.execute("""INSERT INTO belt_status (device_id,status,severity,message,epi,updated_at)
                VALUES (?,?,?,?,?,?) ON CONFLICT(device_id) DO UPDATE SET status=excluded.status,
                severity=excluded.severity, message=excluded.message, epi=excluded.epi, updated_at=excluded.updated_at""",
                (device_id, "VIOLACAO", severity, message, epi, datetime.now().isoformat()))
            self._conn.commit()

    def get_belt_status(self, device_id, ttl=12):
        with self._lock:
            r = self._conn.execute("SELECT * FROM belt_status WHERE device_id=?", (device_id,)).fetchone()
        if not r or not r["updated_at"]:
            return {"status": "CONFORME"}
        try:
            age = (datetime.now() - datetime.fromisoformat(r["updated_at"])).total_seconds()
        except Exception:
            age = 1e9
        if age > ttl:        # alerta "expira" -> cinto volta ao verde sozinho
            return {"status": "CONFORME"}
        return {"status": r["status"] or "VIOLACAO", "severity": r["severity"],
                "message": r["message"], "epi": r["epi"]}

    def clear_belt_status(self, device_id):
        """Zera o alerta do cinto (volta a CONFORME imediatamente)."""
        with self._lock:
            self._conn.execute("DELETE FROM belt_status WHERE device_id=?", (device_id,)); self._conn.commit()

    # zonas
    def add_zone(self, name, level, points, station_id=None, required_epis=None):
        with self._lock:
            cur = self._conn.execute("""INSERT INTO zones (name,station_id,level,points,required_epis,enabled)
                VALUES (?,?,?,?,?,1)""", (name, station_id, level, json.dumps(points), json.dumps(required_epis or [])))
            self._conn.commit(); return cur.lastrowid

    def list_zones(self, station_id=None):
        with self._lock:
            if station_id:
                rows = self._conn.execute("SELECT * FROM zones WHERE station_id=? ORDER BY id", (station_id,)).fetchall()
            else:
                rows = self._conn.execute("SELECT * FROM zones ORDER BY id").fetchall()
        return [self._zone(r) for r in rows]

    def update_zone(self, zid, **kw):
        sets, vals = [], []
        for k in ("name","level","station_id","enabled"):
            if k in kw: sets.append(k+"=?"); vals.append(int(kw[k]) if k=="enabled" else kw[k])
        for k in ("points","required_epis"):
            if k in kw: sets.append(k+"=?"); vals.append(json.dumps(kw[k]))
        if not sets: return
        vals.append(zid)
        with self._lock:
            self._conn.execute("UPDATE zones SET "+",".join(sets)+" WHERE id=?", vals); self._conn.commit()

    def delete_zone(self, zid):
        with self._lock:
            self._conn.execute("DELETE FROM zones WHERE id=?", (zid,)); self._conn.commit()

    @staticmethod
    def _zone(r):
        d = dict(r); d["points"] = json.loads(r["points"]); d["required_epis"] = json.loads(r["required_epis"])
        d["enabled"] = bool(r["enabled"]); return d

    # classificação manual de risco por ÁREA (override da sugestão da IA)
    def set_area_level(self, area, level):
        with self._lock:
            if not level:   # vazio/None → volta a usar a sugestão da IA
                self._conn.execute("DELETE FROM area_levels WHERE area=?", (area,))
            else:
                self._conn.execute("""INSERT INTO area_levels (area,level,updated_at) VALUES (?,?,?)
                    ON CONFLICT(area) DO UPDATE SET level=excluded.level, updated_at=excluded.updated_at""",
                    (area, level, datetime.now().isoformat()))
            self._conn.commit()

    def get_area_levels(self):
        with self._lock:
            rows = self._conn.execute("SELECT area, level FROM area_levels").fetchall()
        return {r["area"]: r["level"] for r in rows}

    # eventos
    def add_event(self, worker_id, type, severity, epi=None, area=None, turno=None, station_id=None, timestamp=None):
        ts = timestamp or datetime.now().isoformat()
        with self._lock:
            self._conn.execute("""INSERT INTO safety_events (worker_id,station_id,area,turno,type,epi,severity,timestamp)
                VALUES (?,?,?,?,?,?,?,?)""", (worker_id, station_id, area, turno, type, epi, severity, ts))
            # trilha de auditoria append-only, encadeada por hash (tamper-evident)
            payload = json.dumps({"worker_id": worker_id, "station_id": station_id, "area": area,
                "turno": turno, "type": type, "epi": epi, "severity": severity, "event_ts": ts},
                sort_keys=True, ensure_ascii=False)
            row = self._conn.execute("SELECT hash FROM audit_chain ORDER BY seq DESC LIMIT 1").fetchone()
            prev = row["hash"] if row else "GENESIS"
            ats = datetime.now().isoformat()
            h = hashlib.sha256((prev + "|" + ats + "|" + payload).encode("utf-8")).hexdigest()
            self._conn.execute("INSERT INTO audit_chain (ts,payload,prev_hash,hash) VALUES (?,?,?,?)",
                               (ats, payload, prev, h))
            self._conn.commit()

    def audit_rows(self):
        with self._lock:
            rows = self._conn.execute("SELECT * FROM audit_chain ORDER BY seq").fetchall()
        return [dict(r) for r in rows]

    def recent_events(self, limit=40):
        with self._lock:
            rows = self._conn.execute("SELECT * FROM safety_events ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return [dict(r) for r in rows]

    def count_by_severity(self):
        with self._lock:
            rows = self._conn.execute("SELECT severity, COUNT(*) c FROM safety_events GROUP BY severity").fetchall()
        return {r["severity"]: r["c"] for r in rows}

    def count_by_type(self):
        with self._lock:
            rows = self._conn.execute("SELECT type, COUNT(*) c FROM safety_events GROUP BY type").fetchall()
        return {r["type"]: r["c"] for r in rows}

    def daily_counts(self, days=14):
        since = (datetime.now() - timedelta(days=days)).date().isoformat()
        with self._lock:
            rows = self._conn.execute("""SELECT substr(timestamp,1,10) d, COUNT(*) c FROM safety_events
                WHERE substr(timestamp,1,10) >= ? GROUP BY d ORDER BY d""", (since,)).fetchall()
        return [{"date": r["d"], "count": r["c"]} for r in rows]

    def events_per_worker(self):
        with self._lock:
            rows = self._conn.execute("SELECT worker_id, COUNT(*) c FROM safety_events GROUP BY worker_id").fetchall()
        return {r["worker_id"]: r["c"] for r in rows}

    def total_events(self):
        with self._lock:
            return self._conn.execute("SELECT COUNT(*) FROM safety_events").fetchone()[0]

    def worker_summaries(self):
        epw = self.events_per_worker(); out = []
        for w in self.get_roster():
            out.append({"worker_id": w["worker_id"], "area": w["area"], "turno": w["turno"],
                "shifts": int(w["shifts"]), "events": int(epw.get(w["worker_id"], 0)),
                "name": w["name"], "required_epis": w["required_epis"]})
        return out

    def conformity_rate(self):
        total = sum(int(w["shifts"]) for w in self.get_roster()) or 1
        ev = min(self.total_events(), total); return round(100.0*(1-ev/total), 1)

    # ── engajamento / gamificação ──
    def last_event_per_worker(self):
        with self._lock:
            rows = self._conn.execute(
                "SELECT worker_id, MAX(timestamp) t FROM safety_events GROUP BY worker_id").fetchall()
        return {r["worker_id"]: r["t"] for r in rows}

    def worker_type_breakdown(self):
        """{worker_id: {(type, epi): n}} — para o feedback educativo personalizado."""
        with self._lock:
            rows = self._conn.execute(
                "SELECT worker_id, type, epi, COUNT(*) c FROM safety_events GROUP BY worker_id, type, epi").fetchall()
        out = {}
        for r in rows:
            out.setdefault(r["worker_id"], []).append({"type": r["type"], "epi": r["epi"], "n": r["c"]})
        return out

    def days_since_last_critical(self):
        with self._lock:
            r = self._conn.execute(
                "SELECT MAX(timestamp) t FROM safety_events WHERE severity='critica'").fetchone()
        if not r or not r["t"]:
            return None
        try:
            return max(0, (datetime.now() - datetime.fromisoformat(r["t"])).days)
        except Exception:
            return None

    def close(self):
        self._conn.close()
