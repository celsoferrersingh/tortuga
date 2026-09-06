"""
risk_engine.py — Motor preditivo de risco de acidente (Fase 3)
Challenge SPI 2026 · Projeto Tortuga

CIÊNCIA DE DADOS APLICADA ao chão de fábrica. Em vez de só contar violações,
modelamos a TAXA de eventos de cada operador e PREVEMOS a probabilidade de um
incidente no próximo turno — e VALIDAMOS estatisticamente quem está realmente
acima da média (sinal), não por acaso (ruído). Assim o gestor age de forma
pedagógica (treinamento dirigido) sobre quem mais precisa.

Fundamentos matemáticos
-----------------------
1) Distribuição de Poisson — eventos de segurança são contagens raras e
   (aprox.) independentes no tempo: o modelo canônico é Poisson. Para o
   operador i com k_i eventos em t_i turnos de exposição, a estimativa de
   máxima verossimilhança da taxa é  λ̂_i = k_i / t_i  (eventos por turno).

2) Predição — probabilidade de pelo menos um evento no próximo turno. Vem
   DIRETO da distribuição de Poisson, sem depender do TLC:
        P(N ≥ 1) = 1 − e^(−λ̂_i)            (horizonte h turnos: 1 − e^(−λ̂_i·h))

3) Teorema do Limite Central — usado SÓ para a incerteza, não para prever.
   O TLC nao "converte a distribuicao dos eventos em uma normal": ele garante
   que a SOMA de muitos turnos independentes — e, portanto, o estimador da taxa
   λ̂_i = k_i/t_i — seja aproximadamente normal quando t_i e grande:
        λ̂_i ≈ Normal(λ, λ/t_i).
   Como na Poisson a variancia = media, o desvio-padrao sai direto de λ. Daí o
   intervalo de confiança de 95%:  λ̂_i ± 1,96·√(λ̂_i / t_i)  (uma faixa, não um
   número cravado — quanto menos dados, mais larga).

4) Teste de hipóteses (validação) — H0: λ_i = λ0 (linha de base do grupo)
   vs H1: λ_i > λ0. Sob H0, k_i ~ Poisson(λ0·t_i).
     • p-valor exato de Poisson (PRINCIPAL, não usa aproximação):  P(K ≥ k_i | H0)
     • p-valor por aproximação normal do TLC (reforço):  z = (k_i − λ0 t_i)/√(λ0 t_i)
   Se p < α (0,05), o operador está significativamente acima da base.

Sem dependências pesadas: apenas `math` (Poisson e Normal implementados aqui).
"""
from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass, asdict

ALPHA = 0.05
Z95 = 1.959963984540054


# ─────────────────────────── distribuições ───────────────────────────
def _poisson_pmf(k: int, mu: float) -> float:
    """P(X = k) para X ~ Poisson(mu). Calculado em log para estabilidade."""
    if mu <= 0:
        return 1.0 if k == 0 else 0.0
    return math.exp(k * math.log(mu) - mu - math.lgamma(k + 1))


def poisson_sf(k: int, mu: float) -> float:
    """P(X ≥ k) para X ~ Poisson(mu) — cauda superior inclusiva em k."""
    if k <= 0:
        return 1.0
    cdf = sum(_poisson_pmf(j, mu) for j in range(0, k))   # P(X ≤ k−1)
    return min(1.0, max(0.0, 1.0 - cdf))


def norm_sf(z: float) -> float:
    """P(Z ≥ z) para Z ~ Normal(0, 1)."""
    return 0.5 * math.erfc(z / math.sqrt(2.0))


# ─────────────────────────── resultado ───────────────────────────
@dataclass
class WorkerRisk:
    worker_id: str
    area: str
    turno: str
    events: int
    shifts: int
    lambda_hat: float        # eventos por turno (taxa estimada)
    p_next_shift: float      # P(≥1 evento no próximo turno)
    ci_low: float            # IC 95% inferior da taxa (TLC)
    ci_high: float           # IC 95% superior da taxa (TLC)
    p_value_exact: float     # teste de Poisson exato (cauda superior)
    p_value_clt: float       # teste por aproximação normal (TLC)
    significant: bool        # acima da base com p < α
    risk_level: str          # Alto / Médio / Baixo
    recommendation: str

    def to_dict(self) -> dict:
        return asdict(self)


# ─────────────────────────── núcleo ───────────────────────────
def baseline_rate(workers: list[dict]) -> float:
    """Taxa de base do grupo (pooled): total de eventos / total de turnos."""
    K = sum(w["events"] for w in workers)
    T = sum(w["shifts"] for w in workers)
    return (K / T) if T > 0 else 0.0


def analyze_worker(w: dict, lambda0: float, horizon: int = 1,
                   alpha: float = ALPHA) -> WorkerRisk:
    k = int(w["events"]); t = max(int(w["shifts"]), 1)
    lam = k / t
    p_next = 1.0 - math.exp(-lam * horizon)

    se = math.sqrt(lam / t)                       # erro-padrão (TLC)
    ci_low = max(0.0, lam - Z95 * se)
    ci_high = lam + Z95 * se

    mu0 = lambda0 * t                             # esperado sob H0
    p_exact = poisson_sf(k, mu0)
    z = (k - mu0) / math.sqrt(mu0) if mu0 > 0 else 0.0
    p_clt = norm_sf(z)
    sig = (p_exact < alpha) and (lam > lambda0)

    if sig and p_next >= 0.5:
        level, rec = "Alto", "Treinamento dirigido + acompanhamento (risco significativo)"
    elif sig or p_next >= 0.4:
        level, rec = "Médio", "Reforço educativo / micro-treino preventivo"
    else:
        level, rec = "Baixo", "Manter monitoramento"

    return WorkerRisk(
        worker_id=w["worker_id"], area=w.get("area", ""), turno=w.get("turno", ""),
        events=k, shifts=t, lambda_hat=round(lam, 3), p_next_shift=round(p_next, 3),
        ci_low=round(ci_low, 3), ci_high=round(ci_high, 3),
        p_value_exact=round(p_exact, 4), p_value_clt=round(p_clt, 4),
        significant=sig, risk_level=level, recommendation=rec,
    )


def rank_workers(workers: list[dict], horizon: int = 1, alpha: float = ALPHA):
    """Retorna (lambda0, [WorkerRisk ordenado por probabilidade desc])."""
    lambda0 = baseline_rate(workers)
    res = [analyze_worker(w, lambda0, horizon, alpha) for w in workers]
    res.sort(key=lambda r: (r.p_next_shift, r.lambda_hat), reverse=True)
    return lambda0, res


# ─────────────────────── risco agregado por ÁREA ───────────────────────
@dataclass
class AreaRisk:
    area: str
    n_workers: int
    events: int
    shifts: int             # turnos-pessoa de exposição (soma dos operadores)
    lambda_hat: float       # eventos por turno-pessoa
    ratio: float            # λ̂_área / λ0 (quantas vezes a base)
    p_next_shift: float     # P(≥1 evento por turno-pessoa na área)
    ci_low: float
    ci_high: float
    p_value_exact: float
    significant: bool
    suggested_level: str    # SUGESTÃO da IA: Alto / Médio / Baixo
    rationale: str

    def to_dict(self) -> dict:
        return asdict(self)


def rank_areas(workers: list[dict], horizon: int = 1, alpha: float = ALPHA):
    """
    Agrega os operadores por ÁREA e devolve (lambda0, [AreaRisk]) — a SUGESTÃO
    automática (IA) de qual área é de maior/menor risco. Mesma matemática do
    ranking por operador (Poisson + TLC + teste de hipóteses), agora por área.
    O nível é apenas uma SUGESTÃO; a classificação final é do gestor.
    """
    lambda0 = baseline_rate(workers)
    agg: dict[str, dict] = {}
    for w in workers:
        a = w.get("area") or "—"
        d = agg.setdefault(a, {"events": 0, "shifts": 0, "n": 0})
        d["events"] += int(w["events"]); d["shifts"] += int(w["shifts"]); d["n"] += 1

    out: list[AreaRisk] = []
    for area, d in agg.items():
        k = int(d["events"]); t = max(int(d["shifts"]), 1)
        lam = k / t
        ratio = (lam / lambda0) if lambda0 > 0 else 0.0
        p_next = 1.0 - math.exp(-lam * horizon)
        se = math.sqrt(lam / t)
        ci_low = max(0.0, lam - Z95 * se); ci_high = lam + Z95 * se
        mu0 = lambda0 * t
        p_exact = poisson_sf(k, mu0)
        sig = (p_exact < alpha) and (lam > lambda0)

        if sig and ratio >= 1.25:
            level = "Alto"
            rationale = "Taxa significativamente acima da base (p<0,05) e ≥25% maior."
        elif ratio >= 1.05 or (sig and ratio >= 1.0):
            level = "Médio"
            rationale = "Em torno ou acima da base do grupo."
        else:
            level = "Baixo"
            rationale = "Taxa igual ou abaixo da base do grupo."

        out.append(AreaRisk(
            area=area, n_workers=d["n"], events=k, shifts=t,
            lambda_hat=round(lam, 3), ratio=round(ratio, 2), p_next_shift=round(p_next, 3),
            ci_low=round(ci_low, 3), ci_high=round(ci_high, 3),
            p_value_exact=round(p_exact, 4), significant=sig,
            suggested_level=level, rationale=rationale))
    out.sort(key=lambda r: (r.lambda_hat, r.events), reverse=True)
    return lambda0, out


def summarize_events(events: list[dict], roster: list[dict]) -> list[dict]:
    """
    Agrega eventos brutos (cada um com 'worker_id') em contagens por operador,
    usando o roster para a exposição (turnos observados) e metadados.
    events: [{worker_id, ...}], roster: [{worker_id, area, turno, shifts}]
    """
    counts = Counter(e["worker_id"] for e in events)
    out = []
    for r in roster:
        out.append({
            "worker_id": r["worker_id"], "area": r.get("area", ""),
            "turno": r.get("turno", ""), "shifts": int(r.get("shifts", 1)),
            "events": int(counts.get(r["worker_id"], 0)),
        })
    return out


# ─────────────────────────── autoteste ───────────────────────────
if __name__ == "__main__":
    # 9 operadores "normais" (~0,3 ev/turno) + 1 plantado de alto risco.
    import random
    random.seed(7)
    workers = []
    for i in range(1, 10):
        t = 40
        k = sum(1 for _ in range(t) if random.random() < 0.3)
        workers.append({"worker_id": f"OP-{i:03d}", "area": "Solda", "turno": "A",
                        "shifts": t, "events": k})
    # operador de alto risco: taxa ~1,3/turno
    workers.append({"worker_id": "OP-010", "area": "Prensa", "turno": "B",
                    "shifts": 40, "events": 52})

    lambda0, ranking = rank_workers(workers)
    print(f"Taxa de base do grupo (λ0): {lambda0:.3f} eventos/turno\n")
    print(f"{'Operador':9} {'ev':>3} {'λ̂':>6} {'P(próx)':>8} {'IC95%':>14} "
          f"{'p(exato)':>9} {'sig':>4} {'nível':>6}")
    for r in ranking:
        print(f"{r.worker_id:9} {r.events:3d} {r.lambda_hat:6.2f} {r.p_next_shift:8.2f} "
              f"[{r.ci_low:.2f};{r.ci_high:.2f}]".ljust(15)
              + f" {r.p_value_exact:9.4f} {str(r.significant):>4} {r.risk_level:>6}")

    top = ranking[0]
    assert top.worker_id == "OP-010", f"esperava OP-010 no topo, veio {top.worker_id}"
    assert top.significant, "OP-010 deveria ser estatisticamente significativo"
    assert not any(r.significant for r in ranking if r.worker_id != "OP-010"), \
        "nenhum operador normal deveria ser sinalizado"
    print("\nOK — o operador de alto risco foi previsto no topo e validado (p<0,05); "
          "nenhum operador normal foi falsamente sinalizado.")
