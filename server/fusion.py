"""
fusion.py — Fusão de múltiplos pontos de visão (Fase 4) · Projeto Tortuga

Na metaindústria a mesma estação é vista por 2+ câmeras de ângulos diferentes.
Um capacete pode estar oculto para a câmera A mas visível para a câmera B. Se
cada câmera decidisse sozinha, a A geraria um falso "sem capacete".

A FUSÃO resolve isso no servidor: cada câmera só REPORTA o que vê (os EPIs
presentes na pessoa, e se há pessoa). O servidor combina, por estação, as
observações frescas de TODAS as câmeras:

    presentes = UNIÃO dos EPIs vistos por qualquer ângulo
    faltando  = exigidos − presentes        (só se houver pessoa)

Ou seja: só alerta quando NENHUM ângulo vê o EPI — robustez a oclusão. Um
cooldown por (estação, EPI) evita repetir o mesmo alerta a cada quadro.
"""
from __future__ import annotations
import threading, time


class FusionCoordinator:
    def __init__(self, window: float = 6.0, cooldown: float = 8.0):
        self.window = float(window)        # seg: idade máxima de uma observação
        self.cooldown = float(cooldown)    # seg: anti-spam de evento por (estação, EPI)
        self._obs: dict[tuple, dict] = {}  # (station, camera) -> {present:set, person, ts}
        self._last_alert: dict[tuple, float] = {}
        self._lock = threading.Lock()

    def observe(self, station, camera, present, person, now=None):
        now = now or time.time()
        with self._lock:
            self._obs[(station, camera)] = {
                "present": set(present or []), "person": bool(person), "ts": now}

    def fused(self, station, required, now=None) -> dict:
        now = now or time.time()
        with self._lock:
            obs = [v for (s, c), v in self._obs.items()
                   if s == station and now - v["ts"] <= self.window]
            cams = sorted(c for (s, c) in self._obs
                          if s == station and now - self._obs[(s, c)]["ts"] <= self.window)
        union = set()
        for o in obs:
            union |= o["present"]
        person = any(o["person"] for o in obs)
        missing = [e for e in (required or []) if e not in union] if person else []
        return {"cameras": len(obs), "camera_ids": cams, "present": sorted(union),
                "person": person, "missing": missing}

    def alertable(self, station, epi, now=None) -> bool:
        """True (e arma o cooldown) se já passou o intervalo desde o último alerta."""
        now = now or time.time()
        with self._lock:
            if now - self._last_alert.get((station, epi), 0) < self.cooldown:
                return False
            self._last_alert[(station, epi)] = now
            return True

    def stations(self, now=None) -> list[str]:
        now = now or time.time()
        with self._lock:
            return sorted({s for (s, c), v in self._obs.items() if now - v["ts"] <= self.window})
