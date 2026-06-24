"""dashboard_client.py — Ponte gui.py -> dashboard (Fase 3). Ingestao de eventos
reais (nao-bloqueante), perfil do operador ativo e zonas. A prova de falha."""
from __future__ import annotations
import json, os, threading, time, urllib.request


class DashboardClient:
    def __init__(self, base_url="http://localhost:5005", station_id=None,
                 min_interval=8.0, timeout=1.0, camera_id=None, observe_interval=1.0):
        self.base = base_url.rstrip("/")
        self.station_id = station_id
        self.camera_id = camera_id or f"{station_id}-{os.getpid()}"
        self.min_interval = float(min_interval)
        self.observe_interval = float(observe_interval)
        self.timeout = timeout
        self._last = {}
        self._last_obs = 0.0

    def observe(self, present, person):
        """Fusão multi-câmera: reporta o que ESTA câmera vê; o servidor decide."""
        now = time.time()
        if now - self._last_obs < self.observe_interval:
            return False
        self._last_obs = now
        payload = {"station_id": self.station_id, "camera_id": self.camera_id,
                   "present": list(present or []), "person": bool(person)}
        threading.Thread(target=self._post, args=("/api/observe", payload), daemon=True).start()
        return True

    def ingest(self, type, epi=None, severity=None, worker_id=None):
        key = f"{type}:{epi or ''}"
        now = time.time()
        if now - self._last.get(key, 0) < self.min_interval:
            return False
        self._last[key] = now
        payload = {"type": type, "epi": epi, "severity": severity,
                   "station_id": self.station_id, "worker_id": worker_id}
        threading.Thread(target=self._post, args=("/api/ingest", payload), daemon=True).start()
        return True

    def active_profile(self):
        belts = self._get("/api/belts") or []
        wid = next((b.get("active_worker_id") for b in belts
                    if b.get("station_id") == self.station_id), None)
        if not wid:
            return None
        profs = self._get("/api/profiles") or []
        return next((p for p in profs if p["worker_id"] == wid), None)

    def zones(self):
        q = f"/api/zones?station_id={self.station_id}" if self.station_id else "/api/zones"
        return self._get(q) or []

    def _post(self, path, payload):
        data = json.dumps(payload).encode()
        req = urllib.request.Request(self.base + path, data=data, method="POST",
                                     headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                return json.loads(r.read() or "{}")
        except Exception:
            return None

    def _get(self, path):
        try:
            with urllib.request.urlopen(self.base + path, timeout=self.timeout) as r:
                return json.loads(r.read() or "null")
        except Exception:
            return None
