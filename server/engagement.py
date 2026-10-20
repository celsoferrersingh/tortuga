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

3) Conformidade NR-7 (PCMSO) — SELO, NÃO PONTUAÇÃO. O ASO válido rende o selo
   "Exames em conformidade"; o exame não entra no cálculo de pontos nem somando,
   porque agendar é responsabilidade da empresa e pontuar isso rebaixaria no
   placar quem ainda não foi chamado pelo RH. A cobrança do vencimento vai
   inteira para o painel do gestor, que é quem pode acionar o RH. O sistema
   guarda apenas a DATA DE VALIDADE — nunca resultado, diagnóstico ou restrição.

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

# ── NR-7 (PCMSO) na gamificação: SELO SIM, PONTUAÇÃO NÃO ──────────────────────
# DECISÃO DE PROJETO: o exame ocupacional NÃO entra na pontuação — nem somando.
# Agendar o exame é responsabilidade da empresa (NR-7), não do trabalhador. Se o
# ASO rendesse pontos, quem ainda não foi chamado pelo RH ficaria ABAIXO no placar
# por uma pendência fora do seu controle — punição indireta, que é exatamente o
# que este projeto não faz. Então a pontuação depende só do que o operador
# controla (conformidade de EPI, postura, sequência limpa) e o ASO aparece
# apenas como SELO de reconhecimento, que não ordena ninguém.
# A cobrança do vencimento vai inteira para o painel do gestor
# (store.aso_report), que é quem pode acionar o RH e agendar.
# O sistema conhece apenas a DATA DE VALIDADE — nunca resultado ou diagnóstico.


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


def _badges(conformity, events, streak_days, aso=None):
    out = []
    if events == 0:
        out.append("Turnos impecáveis")
    if conformity >= 0.9:
        out.append("Ouro em conformidade")
    elif conformity >= 0.75:
        out.append("Prata em conformidade")
    if streak_days is not None and streak_days >= 7:
        out.append("7+ dias sem ocorrência")
    # NR-7: selo de reconhecimento para quem está com o ASO VÁLIDO — inclui quem
    # está na janela de alerta (o documento ainda vale; o prazo é problema de
    # agenda da empresa, não falta do operador). Não existe selo negativo e o
    # selo não altera a pontuação: reconhece sem ordenar.
    if aso and aso.get("ok"):
        out.append("Exames em conformidade")
    return out


def build(summaries, last_events, type_breakdown, now=None, shifts_with_events=None):
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
        # turnos COM evento (nao o nº de eventos): um turno ruim conta uma vez.
        com = (shifts_with_events or {}).get(wid)
        if com is None:
            com = min(e, s)                      # fallback se nao vier do store
        clean = max(0, s - min(int(com), s))
        conformity = clean / s
        # streak: dias desde o último evento (quanto mais alto, melhor)
        ts = last_events.get(wid)
        streak = None
        if ts:
            try:
                streak = max(0, (now - datetime.fromisoformat(ts)).days)
            except Exception:
                streak = None
        # O ASO NÃO entra aqui: a pontuação reflete só o que o operador controla.
        aso = w.get("aso") or {}
        points = round(conformity * 100) + (streak or 0) * 2 + (15 if e == 0 else 0)
        leaderboard.append({
            "worker_id": wid, "name": w.get("name", wid), "area": w.get("area", ""),
            "turno": w.get("turno", ""), "conformity": round(conformity * 100, 1),
            "streak_days": streak, "points": points, "events": e,
            "badges": _badges(conformity, e, streak, aso),
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
