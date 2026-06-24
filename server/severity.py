"""
severity.py — Política de severidade da Fase 3 (Tabela 7 do descritivo).
Classifica cada evento em 3 níveis, definindo canais e latência-alvo.

  Crítica     risco imediato à integridade (queda, zona crítica, ausência de
              cinto em altura) → sonoro + visual + push + log, < 1 s.
  Alta        violação de EPI obrigatório, postura de risco persistente,
              aproximação de zona perigosa → visual + dashboard + log, < 5 s.
  Informativa postura ergonômica, fadiga, recomendações → dashboard, sem
              interromper a operação.
"""
from __future__ import annotations

POLICY = {
    "critica": {
        "label": "Crítica", "color": "#EF4444",
        "channels": ["sonoro", "visual", "push", "log"], "max_latency_s": 1,
    },
    "alta": {
        "label": "Alta", "color": "#F59E0B",
        "channels": ["visual", "dashboard", "log"], "max_latency_s": 5,
    },
    "informativa": {
        "label": "Informativa", "color": "#22D3EE",
        "channels": ["dashboard"], "max_latency_s": None,
    },
}

# tipo de evento → severidade padrão
_TYPE_SEVERITY = {
    "QUEDA": "critica",
    "ZONA_CRITICA": "critica",
    "EPI_AUSENTE": "alta",
    "POSTURA_RISCO": "alta",
    "POSTURA_ERGONOMICA": "informativa",
    "FADIGA": "informativa",
}


def classify(event_type: str, *, altura: bool = False, persistente: bool = False) -> str:
    """
    Retorna a severidade ('critica' | 'alta' | 'informativa') de um evento.
    `altura`: trabalho em altura eleva ausência de cinto a crítica (NR-35).
    `persistente`: postura de risco mantida no tempo permanece 'alta'.
    """
    sev = _TYPE_SEVERITY.get(event_type, "alta")
    if event_type == "EPI_AUSENTE" and altura:
        sev = "critica"          # sem cinto em altura
    if event_type == "POSTURA_RISCO" and not persistente:
        sev = "alta"             # mantém alta; só rebaixa se for ergonômica pura
    return sev


def policy_for(severity: str) -> dict:
    return POLICY.get(severity, POLICY["alta"])


def channels_for(severity: str) -> list[str]:
    return policy_for(severity)["channels"]


def is_field(severity: str) -> bool:
    """Severidade que deve acionar o canal de CAMPO (ESP32: som/visual)?"""
    ch = channels_for(severity)
    return ("sonoro" in ch) or ("visual" in ch)
