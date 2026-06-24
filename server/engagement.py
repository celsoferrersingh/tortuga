"""
engagement.py — Estímulos "out of the box" (Fase 3) · Projeto Tortuga

Dois mecanismos, ambos NÃO punitivos (princípio pedagógico da Fase 3):

1) Gamificação POSITIVA — em vez de ranquear quem mais infringe, celebramos
   conformidade: pontos por turnos limpos, sequências (streaks) sem ocorrência
   e selos de reconhecimento. O placar premia o bom comportamento.

2) Feedback educativo PERSONALIZADO — para cada operador, o sistema identifica
   o ponto fraco dominante (qual EPI/risco aparece mais nos eventos dele) e
   devolve uma microorientação objetiva, ancorada na NR aplicável. É o "treino
   dirigido" que o motor preditivo recomenda, agora com conteúdo concreto.

O wearable já é o cinto ESP32 (vibração + som) — aqui tratamos só do reforço
educativo/positivo que acompanha o alerta, não de outro dispositivo.
"""
from __future__ import annotations
from datetime import datetime


# ── conteúdo educativo por EPI (aceita rótulo EN do perfil e PT do evento) ──
EPI_TIPS = {
    "hardhat": ("Capacete", "O capacete protege contra impacto e queda de objetos (NR-6). "
                "Confira a jugular antes de entrar na área."),
    "capacete": ("Capacete", "O capacete protege contra impacto e queda de objetos (NR-6). "
                 "Confira a jugular antes de entrar na área."),
    "safety vest": ("Colete", "O colete de alta visibilidade faz máquinas e colegas te enxergarem "
                    "(NR-6 / NR-12). Mantenha-o fechado e limpo."),
    "colete": ("Colete", "O colete de alta visibilidade faz máquinas e colegas te enxergarem "
               "(NR-6 / NR-12). Mantenha-o fechado e limpo."),
    "safety glasses": ("Óculos", "Os óculos evitam lesões por partículas e respingos (NR-6). "
                       "Use sempre na zona de corte e solda."),
    "óculos": ("Óculos", "Os óculos evitam lesões por partículas e respingos (NR-6). "
               "Use sempre na zona de corte e solda."),
    "mask": ("Máscara", "A máscara/respirador protege as vias respiratórias contra vapores e poeira "
             "(NR-6 / NR-15). Verifique a vedação."),
    "máscara": ("Máscara", "A máscara/respirador protege as vias respiratórias contra vapores e poeira "
                "(NR-6 / NR-15). Verifique a vedação."),
    "ear protection": ("Protetor auricular", "O protetor auricular previne perda auditiva por ruído "
                       "contínuo (NR-15). Reposicione a cada troca de posto."),
    "protetor auricular": ("Protetor auricular", "O protetor auricular previne perda auditiva por ruído "
                           "contínuo (NR-15). Reposicione a cada troca de posto."),
    "safety boots": ("Bota", "A botina com biqueira protege contra esmagamento e perfuração (NR-6). "
                     "Confira o cadarço e o solado."),
    "bota": ("Bota", "A botina com biqueira protege contra esmagamento e perfuração (NR-6). "
             "Confira o cadarço e o solado."),
}

TYPE_TIPS = {
    "POSTURA_RISCO": ("Ergonomia", "Sua postura acumulou score RULA/REBA alto (NR-17). "
                      "Ajuste a altura da bancada e alterne posições a cada ciclo."),
    "ZONA_CRITICA": ("Zona crítica", "Evite permanência na zona crítica; respeite a sinalização "
                     "e o tempo máximo de exposição do posto."),
    "FADIGA": ("Fadiga", "Sinais de fadiga detectados. Faça as pausas previstas (NR-17), "
               "hidrate-se e comunique o líder se persistir."),
    "QUEDA": ("Queda", "Risco de queda identificado (NR-35). Use ancoragem em altura "
              "e mantenha três pontos de apoio ao subir/descer."),
}

POSITIVE = "Conformidade exemplar — siga assim e ajude a manter o turno limpo."


def _norm(s):
    return (s or "").strip().lower()


def _dominant(breakdown):
    """Maior contribuinte de risco do operador: (type, epi, n)."""
    if not breakdown:
        return None
    top = max(breakdown, key=lambda b: b["n"])
    return top


def _coach_for(breakdown):
    """Microorientação personalizada a partir do ponto fraco dominante."""
    top = _dominant(breakdown)
    if not top:
        return None
    if top["type"] == "EPI_AUSENTE" and top["epi"]:
        epi = EPI_TIPS.get(_norm(top["epi"]))
        if epi:
            return {"focus": "EPI: " + epi[0], "tip": epi[1]}
        return {"focus": "EPI: " + top["epi"], "tip":
                "EPI obrigatório ausente. Confira a lista do seu posto antes de iniciar o turno (NR-6)."}
    t = TYPE_TIPS.get(top["type"])
    if t:
        return {"focus": t[0], "tip": t[1]}
    return None


def _badges(conformity, events, streak_days):
    out = []
    if events == 0:
        out.append("Turnos impecáveis")
    if conformity >= 0.9:
        out.append("Ouro em conformidade")
    elif conformity >= 0.75:
        out.append("Prata em conformidade")
    if streak_days is not None and streak_days >= 7:
        out.append("7+ dias sem ocorrência")
    return out


def build(summaries, last_events, type_breakdown, now=None):
    """
    summaries: [{worker_id,name,area,turno,shifts,events,...}]
    last_events: {worker_id: iso_timestamp}
    type_breakdown: {worker_id: [{type,epi,n}, ...]}
    Retorna {"leaderboard": [...], "coaching": [...]}.
    """
    now = now or datetime.now()
    leaderboard, coaching = [], []
    for w in summaries:
        wid = w["worker_id"]; s = max(int(w["shifts"]), 1); e = int(w["events"])
        clean = max(0, s - e)
        conformity = clean / s
        # streak: dias desde o último evento (quanto mais alto, melhor)
        ts = last_events.get(wid)
        streak = None
        if ts:
            try:
                streak = max(0, (now - datetime.fromisoformat(ts)).days)
            except Exception:
                streak = None
        points = round(conformity * 100) + (streak or 0) * 2 + (15 if e == 0 else 0)
        leaderboard.append({
            "worker_id": wid, "name": w.get("name", wid), "area": w.get("area", ""),
            "turno": w.get("turno", ""), "conformity": round(conformity * 100, 1),
            "streak_days": streak, "points": points, "events": e,
            "badges": _badges(conformity, e, streak),
        })
        c = _coach_for(type_breakdown.get(wid))
        if c:
            coaching.append({"worker_id": wid, "name": w.get("name", wid),
                             "area": w.get("area", ""), "focus": c["focus"], "tip": c["tip"],
                             "events": e})

    leaderboard.sort(key=lambda x: x["points"], reverse=True)
    # quem mais precisa de reforço primeiro (mais eventos)
    coaching.sort(key=lambda x: x["events"], reverse=True)
    return {"leaderboard": leaderboard, "coaching": coaching}
