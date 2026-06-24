"""
notifier.py — Camada de notificação da Fase 3.
Roteia cada evento para os canais corretos segundo a severidade:

  • CAMPO (operador): ESP32 no cinto via HTTP (POST {esp32_url}/status) →
    OLED + LED + buzzer + vibração. Atende a 'sonoro'/'visual'.
  • GESTÃO: persiste no banco (dashboard) e, opcionalmente, dispara um
    webhook (push/Slack/Teams) em eventos críticos.

Tudo não-bloqueante (threads daemon) para não travar o loop de visão.
Sem dependências externas: usa urllib da stdlib.
"""
from __future__ import annotations

import json
import logging
import threading
import time
import urllib.request

import severity as sev_policy

log = logging.getLogger("tortuga")


def _post_json(url: str, payload: dict, timeout: float = 1.0) -> tuple[bool, float]:
    """POST JSON simples (stdlib). Retorna (ok, latencia_s)."""
    t0 = time.time()
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST",
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            r.read()
        return True, time.time() - t0
    except Exception as e:
        log.debug("notify POST falhou (%s): %s", url, e)
        return False, time.time() - t0


class Notifier:
    """
    Orquestra os canais. `event_store` (EventStore) registra a ocorrência para
    o dashboard; `webhook_url` é opcional para push à gestão em eventos críticos.
    """

    def __init__(self, event_store=None, webhook_url: str | None = None):
        self.store = event_store
        self.webhook_url = webhook_url

    # ── API principal ──────────────────────────────────────
    def notify(self, station: dict, *, worker_id: str, event_type: str,
               severity: str | None = None, epi: str | None = None,
               message: str | None = None, altura: bool = False) -> dict:
        sev = severity or sev_policy.classify(event_type, altura=altura)
        pol = sev_policy.policy_for(sev)
        status = "CONFORME" if event_type == "CONFORME" else "VIOLACAO"
        msg = message or self._default_msg(event_type, epi)

        # 1) GESTÃO — registra para o dashboard (assíncrono leve)
        if self.store is not None and status == "VIOLACAO":
            try:
                self.store.add_event(worker_id=worker_id, type=event_type,
                                     severity=sev, epi=epi,
                                     area=station.get("area"), turno=station.get("turno"),
                                     station_id=station.get("id"))
            except Exception as e:
                log.warning("falha ao registrar evento: %s", e)

        # 2) CAMPO — ESP32 (som/visual) quando a severidade exige
        if station.get("esp32_url") and sev_policy.is_field(sev):
            payload = {"status": status, "severity": sev,
                       "severity_label": pol["label"], "message": msg,
                       "epi": epi, "worker_id": worker_id}
            self._async(self._push_esp32, station["esp32_url"], payload, pol["max_latency_s"])

        # 3) PUSH à gestão em eventos críticos (webhook opcional)
        if self.webhook_url and sev == "critica":
            self._async(_post_json, self.webhook_url,
                        {"text": f"[CRÍTICO] {station.get('name','estação')}: {msg}"}, 3.0)

        return {"severity": sev, "channels": pol["channels"], "status": status,
                "message": msg, "max_latency_s": pol["max_latency_s"]}

    def set_conforme(self, station: dict) -> None:
        """Devolve o posto ao estado CONFORME no ESP32 (LED verde, sem alarme)."""
        if station.get("esp32_url"):
            self._async(self._push_esp32, station["esp32_url"],
                        {"status": "CONFORME", "severity": "ok",
                         "severity_label": "Conforme", "message": "Tudo certo"}, 2.0)

    # ── internos ───────────────────────────────────────────
    def _push_esp32(self, esp32_url: str, payload: dict, budget_s) -> None:
        url = esp32_url.rstrip("/") + "/status"
        ok, lat = _post_json(url, payload, timeout=max(0.8, float(budget_s or 1)))
        if ok and budget_s and lat > budget_s:
            log.info("ESP32 fora do orçamento de latência: %.2fs > %ss", lat, budget_s)

    @staticmethod
    def _async(fn, *args):
        threading.Thread(target=fn, args=args, daemon=True).start()

    @staticmethod
    def _default_msg(event_type: str, epi: str | None) -> str:
        m = {
            "EPI_AUSENTE": f"{epi or 'EPI'} necessário nesta área",
            "POSTURA_RISCO": "Postura de risco detectada",
            "ZONA_CRITICA": "Aproximação de zona restrita",
            "QUEDA": "Queda detectada — verificar operador",
            "FADIGA": "Sinais de fadiga — pausa recomendada",
        }
        # linguagem educativa, não punitiva (UX da Fase 3)
        return m.get(event_type, "Atenção à conformidade de segurança")
