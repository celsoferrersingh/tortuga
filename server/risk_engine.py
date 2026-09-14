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

5) Combinação Poisson × Binomial Negativa (Pascal) — validação da premissa.
   A Poisson supõe variância = média (equidispersão). Medimos o índice de
   dispersão φ (Pearson). Se φ ≈ 1, a Poisson é adequada. Se φ > 1
   (superdispersão — comum quando os operadores são heterogêneos), escalamos
   para a Binomial Negativa / quasi-Poisson: alargamos os IC por √φ e usamos um
   p-valor ROBUSTO — assim a estimativa nunca fica confiante demais. A Poisson é
   o CASO PARTICULAR da BN sem dispersão extra: começamos por ela (parcimônia,
   pouco dado) e ativamos a BN só quando os dados pedem.

6) "Quando" — tempo de espera até o próximo incidente (COMPLEMENTO da Poisson).
   A Poisson diz a PROBABILIDADE no próximo turno; a GEOMÉTRICA diz QUANTOS
   turnos faltam até o próximo incidente. Cada turno é um ensaio de Bernoulli
   com "sucesso" = ter ≥1 evento, de probabilidade p = 1 − e^(−λ̂). O nº de
   turnos até o próximo incidente segue a Geométrica — que é a Binomial Negativa
   (Pascal) com r = 1 ("nº de tentativas até o 1º sucesso"):
        E[turnos até o próximo] = 1 / p          (Pascal geral: r/p até o r-ésimo)
        P(≥1 incidente em m turnos) = 1 − (1 − p)^m
   A faixa (otimista–pessimista) usa o IC ROBUSTO de λ̂ (já alargado por √φ):
   taxa maior → espera menor; taxa menor → espera maior. Assim a mesma Binomial
   Negativa que dá robustez à contagem (§5) responde também "o próximo, quando?".

Sem dependências pesadas: apenas `math` (Poisson, Normal e Binomial Negativa aqui).
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


# ───────── Binomial Negativa (Pascal): Poisson com taxa Gama (superdispersão) ─────────
# A BN generaliza a Poisson: é o que se obtém quando a taxa NÃO é constante, mas
# varia (mistura Poisson–Gama) → variância > média. A Poisson é o caso particular
# sem dispersão extra. Usada como reforço quando os dados mostram superdispersão.
def nbinom_params_from_moments(mean: float, var: float):
    """r (dispersão) e p da BN por método dos momentos.
    Var = mean + mean²/r  ⇒  r = mean²/(var − mean),  p = r/(r + mean).
    Se var ≤ mean (sem superdispersão) devolve (None, None): use Poisson."""
    if mean <= 0 or var <= mean:
        return None, None
    r = mean * mean / (var - mean)
    p = r / (r + mean)
    return r, p


def _nbinom_pmf(k: int, r: float, p: float) -> float:
    """P(X = k) para X ~ BN(r, p), com r real (lgamma para estabilidade)."""
    return math.exp(math.lgamma(k + r) - math.lgamma(r) - math.lgamma(k + 1)
                    + r * math.log(p) + k * math.log1p(-p))


def nbinom_sf(k: int, r: float, p: float) -> float:
    """P(X ≥ k) para X ~ BN(r, p) — cauda superior inclusiva em k."""
    if k <= 0:
        return 1.0
    cdf = sum(_nbinom_pmf(j, r, p) for j in range(0, k))
    return min(1.0, max(0.0, 1.0 - cdf))


# ───────── "Quando?" — tempo de espera até o próximo incidente ─────────
# COMPLEMENTO da Poisson (a Poisson dá a probabilidade; a Geométrica dá o tempo).
# Cada turno é um ensaio de Bernoulli com p = 1 − e^(−λ) (prob. de ≥1 evento no
# turno). O nº de turnos até o próximo incidente segue a GEOMÉTRICA — a Binomial
# Negativa (Pascal) com r = 1: "nº de tentativas até o 1º sucesso".
def prob_event_in_shift(lam: float) -> float:
    """p = P(≥1 evento em um turno) = 1 − e^(−λ). O 'sucesso' do ensaio de Bernoulli."""
    return 1.0 - math.exp(-lam)


def expected_shifts_to_next(lam: float, r: int = 1) -> float:
    """E[turnos até o r-ésimo incidente] pela Pascal/Binomial Negativa: r/p.
    r = 1 → Geométrica (o PRÓXIMO incidente). Se p = 0 (λ = 0) → ∞ (sem risco previsto)."""
    p = prob_event_in_shift(lam)
    return (r / p) if p > 0 else float("inf")


def prob_incident_within(lam: float, m: int) -> float:
    """P(ao menos 1 incidente nos próximos m turnos) = 1 − (1 − p)^m."""
    p = prob_event_in_shift(lam)
    return 1.0 - (1.0 - p) ** m


def dispersion_report(workers: list[dict], lambda0: float | None = None) -> dict:
    """
    Diagnóstico de SUPERDISPERSÃO — testa a premissa central da Poisson
    (variância = média). Usa a estatística de dispersão de Pearson relativa ao
    modelo Poisson de base:  φ = (1/dof) · Σ (k_i − λ0·t_i)² / (λ0·t_i).
      φ ≈ 1  → Poisson adequada (equidispersão).
      φ > 1  → superdispersão → Binomial Negativa / quasi-Poisson.
    Ajusta ainda uma BN às contagens (r = parâmetro de dispersão) para referência.
    """
    n = len(workers)
    if lambda0 is None:
        lambda0 = baseline_rate(workers)
    if n < 2 or lambda0 <= 0:
        return {"phi": 1.0, "overdispersed": False, "n": n, "nb_r": None,
                "recommendation": "Poisson", "note": "amostra pequena ou base zero"}
    chi2 = 0.0; dof = 0
    for w in workers:
        k = int(w["events"]); t = max(int(w["shifts"]), 1)
        mu = lambda0 * t
        if mu > 0:
            chi2 += (k - mu) ** 2 / mu; dof += 1
    dof = max(dof - 1, 1)
    phi = chi2 / dof
    over = phi > 1.5                              # limiar prático p/ acionar a correção
    z = (chi2 - dof) / math.sqrt(2.0 * dof)       # χ² ≈ Normal p/ dof grande
    p_over = norm_sf(z)
    counts = [int(w["events"]) for w in workers]
    mean_c = sum(counts) / n
    var_c = sum((c - mean_c) ** 2 for c in counts) / max(n - 1, 1)
    r_nb, _p_nb = nbinom_params_from_moments(mean_c, var_c)
    return {
        "phi": round(phi, 2), "chi2": round(chi2, 2), "dof": dof,
        "overdispersed": over, "p_value": round(p_over, 4),
        "nb_r": (round(r_nb, 2) if r_nb else None),
        "recommendation": "Binomial Negativa / quasi-Poisson" if over else "Poisson",
        "note": ("variância acima da média (superdispersão): IC e testes robustos ativados"
                 if over else "variância ≈ média: Poisson adequada"),
    }


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
    eta_shifts: float | None    # E[turnos até o próximo incidente] — Geométrica/BN(r=1)=1/p (None=sem risco)
    eta_low: float | None       # espera mínima (cenário de maior taxa, IC robusto)
    eta_high: float | None      # espera máxima (None = indefinida quando o IC toca ~0)
    ci_low: float            # IC 95% inferior da taxa (TLC)
    ci_high: float           # IC 95% superior da taxa (TLC)
    p_value_exact: float     # teste de Poisson exato (cauda superior)
    p_value_clt: float       # teste por aproximação normal (TLC)
    p_value_robust: float    # teste ROBUSTO a superdispersão (quasi-Poisson/BN)
    dispersion_phi: float    # φ do grupo (≈1 = Poisson; >1 = superdispersão → BN)
    model: str               # "Poisson" ou "Poisson + BN (quasi)"
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
                   alpha: float = ALPHA, phi: float = 1.0) -> WorkerRisk:
    """phi = fator de dispersão do grupo (1 = Poisson; >1 = superdispersão).
    Quando >1, alarga o IC por √φ e usa um teste robusto (quasi-Poisson/BN)."""
    k = int(w["events"]); t = max(int(w["shifts"]), 1)
    lam = k / t
    p_next = 1.0 - math.exp(-lam * horizon)       # PREVISÃO: vem DIRETO da Poisson

    phi = max(float(phi), 1.0)
    overdisp = phi > 1.0
    se = math.sqrt(lam / t)                       # erro-padrão (TLC)
    se_r = se * math.sqrt(phi)                    # inflado se superdisperso (quasi-Poisson/BN)
    ci_low = max(0.0, lam - Z95 * se_r)
    ci_high = lam + Z95 * se_r

    # "Quando?": turnos até o próximo incidente — Geométrica = Binomial Negativa(r=1).
    # Faixa vinda do IC ROBUSTO: taxa maior (ci_high) → espera menor; ci_low → maior.
    eta = expected_shifts_to_next(lam)
    eta_lo = expected_shifts_to_next(ci_high)     # cenário de maior taxa → menos turnos
    eta_hi = expected_shifts_to_next(ci_low)      # cenário de menor taxa → mais turnos (pode ser ∞)

    mu0 = lambda0 * t                             # esperado sob H0
    p_exact = poisson_sf(k, mu0)                  # teste EXATO de Poisson (principal)
    z = (k - mu0) / math.sqrt(mu0) if mu0 > 0 else 0.0
    p_clt = norm_sf(z)                            # aproximação normal do TLC (reforço)
    p_robust = norm_sf(z / math.sqrt(phi))        # robusto a superdispersão (quasi-Poisson)
    # decisão: superdisperso → usa o p robusto (mais conservador); senão → o exato
    p_decision = p_robust if overdisp else p_exact
    sig = (p_decision < alpha) and (lam > lambda0)
    model = "Poisson + BN (quasi)" if overdisp else "Poisson"

    if sig and p_next >= 0.5:
        level, rec = "Alto", "Treinamento dirigido + acompanhamento (risco significativo)"
    elif sig or p_next >= 0.4:
        level, rec = "Médio", "Reforço educativo / micro-treino preventivo"
    else:
        level, rec = "Baixo", "Manter monitoramento"

    return WorkerRisk(
        worker_id=w["worker_id"], area=w.get("area", ""), turno=w.get("turno", ""),
        events=k, shifts=t, lambda_hat=round(lam, 3), p_next_shift=round(p_next, 3),
        eta_shifts=(round(eta, 1) if math.isfinite(eta) else None),
        eta_low=(round(eta_lo, 1) if math.isfinite(eta_lo) else None),
        eta_high=(round(eta_hi, 1) if math.isfinite(eta_hi) else None),
        ci_low=round(ci_low, 3), ci_high=round(ci_high, 3),
        p_value_exact=round(p_exact, 4), p_value_clt=round(p_clt, 4),
        p_value_robust=round(p_robust, 4), dispersion_phi=round(phi, 2), model=model,
        significant=sig, risk_level=level, recommendation=rec,
    )


def rank_workers(workers: list[dict], horizon: int = 1, alpha: float = ALPHA):
    """Retorna (lambda0, [WorkerRisk ordenado por probabilidade desc]).
    Diagnostica superdispersão (φ) e, se houver, aplica a correção robusta
    (quasi-Poisson / Binomial Negativa) nos IC e no teste — nunca fica confiante
    demais. Use dispersion_report(workers) para o diagnóstico do grupo."""
    lambda0 = baseline_rate(workers)
    disp = dispersion_report(workers, lambda0)
    phi = disp["phi"] if disp["overdispersed"] else 1.0
    res = [analyze_worker(w, lambda0, horizon, alpha, phi=phi) for w in workers]
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
    _disp = dispersion_report(workers, lambda0)
    _sphi = math.sqrt(_disp["phi"]) if _disp["overdispersed"] else 1.0
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
        se = math.sqrt(lam / t) * _sphi          # IC robusto a superdispersão (√φ)
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
    disp = dispersion_report(workers, lambda0)
    print(f"Taxa de base do grupo (λ0): {lambda0:.3f} eventos/turno")
    print(f"Dispersão φ = {disp['phi']}  (>1,5 = superdispersão)  ->  {disp['recommendation']}"
          + (f"  ·  BN r={disp['nb_r']}" if disp.get('nb_r') else "") + "\n")
    print(f"{'Operador':9} {'ev':>3} {'λ̂':>6} {'P(próx)':>8} {'IC95%':>14} "
          f"{'p(exato)':>9} {'p(robust)':>10} {'sig':>5} {'nível':>6}")
    for r in ranking:
        print(f"{r.worker_id:9} {r.events:3d} {r.lambda_hat:6.2f} {r.p_next_shift:8.2f} "
              f"[{r.ci_low:.2f};{r.ci_high:.2f}]".ljust(15)
              + f" {r.p_value_exact:9.4f} {r.p_value_robust:10.4f} {str(r.significant):>5} {r.risk_level:>6}")

    # Efeito da correção robusta no IC do operador de maior risco
    top = ranking[0]
    se = math.sqrt(top.lambda_hat / max(top.shifts, 1))
    print(f"\nIC 95% de {top.worker_id} (λ̂={top.lambda_hat}):")
    print(f"  Poisson puro : +/-{Z95 * se:.2f}")
    print(f"  Robusto (x√φ): +/-{Z95 * se * math.sqrt(disp['phi']):.2f}"
          f"   <- Binomial Negativa / quasi-Poisson (nao fica confiante demais)")

    # "Quando?": turnos até o próximo incidente — Geométrica = Binomial Negativa(r=1)
    print(f"\nQuando (turnos ate o proximo incidente) — Geometrica = Binomial Negativa(r=1):")
    print(f"  {'Operador':9} {'esperado':>9}   faixa (robusta)")
    for r in ranking[:5]:
        hi = "∞" if r.eta_high is None else f"{r.eta_high}"
        est = "—" if r.eta_shifts is None else f"~{r.eta_shifts} turnos"
        print(f"  {r.worker_id:9} {est:>9}   [{r.eta_low}; {hi}]")
    print(f"  Leitura: {top.worker_id} tende a repetir a cada ~{top.eta_shifts} turno(s); "
          f"P(nos proximos 3) = {prob_incident_within(top.lambda_hat,3)*100:.0f}%.")

    assert top.eta_shifts is not None and top.eta_shifts < 3, \
        "o operador de alto risco deveria ter espera curta (poucos turnos ate o proximo)"
    assert top.worker_id == "OP-010", f"esperava OP-010 no topo, veio {top.worker_id}"
    assert top.significant, "OP-010 deveria ser significativo mesmo com a correção robusta"
    assert not any(r.significant for r in ranking if r.worker_id != "OP-010"), \
        "nenhum operador normal deveria ser sinalizado"
    assert disp["overdispersed"], "o autoteste tem um outlier -> deveria detectar superdispersão"
    print("\nOK — superdispersão detectada (φ>1,5) e tratada com quasi-Poisson/BN; "
          "OP-010 segue sinalizado de forma ROBUSTA; nenhum normal falsamente sinalizado.")
