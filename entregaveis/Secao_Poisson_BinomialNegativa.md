# Motor preditivo — Poisson × Binomial Negativa (robustez estatística)
*(Seção para inserir na Documentacao_Fase3_Tortuga.docx — Fase 3 · Projeto Tortuga)*

## Modelo base: Poisson

Cada operador é modelado como um processo de **Poisson**. Com `k` eventos de
segurança observados em `t` turnos de exposição, a taxa estimada (máxima
verossimilhança) é **λ̂ = k / t** (eventos por turno). A probabilidade de ao
menos um incidente no próximo turno vem **diretamente da Poisson**:

    P(N ≥ 1) = 1 − e^(−λ̂)          (horizonte h turnos: 1 − e^(−λ̂·h))

O **Teorema do Limite Central** fornece a incerteza — não a previsão: como na
Poisson a variância é igual à média, o intervalo de confiança de 95% da taxa é

    IC 95% = λ̂ ± 1,96 · √(λ̂ / t)

E um **teste de hipóteses** valida quem está de fato acima da base do grupo λ₀
(H0: λ = λ₀ vs H1: λ > λ₀), usando o p-valor **exato de Poisson**
P(K ≥ k | λ₀) como critério principal (α = 0,05) — sinal, não ruído.

## Validação da premissa: por que combinar com a Binomial Negativa

A Poisson supõe **equidispersão** (variância = média). No chão de fábrica, porém,
os operadores são heterogêneos: um punhado costuma concentrar quase todas as
ocorrências. Isso faz a variância ficar **maior** que a média — fenômeno chamado
**superdispersão** — e uma Poisson pura passaria a ser *confiante demais*
(intervalos estreitos, p-valores otimistas), correndo o risco de acusar alguém
por acaso.

Por isso o Tortuga **mede a dispersão** antes de confiar no modelo, com o índice
de dispersão de Pearson relativo à base:

    φ = (1 / gl) · Σ (kᵢ − λ₀·tᵢ)² / (λ₀·tᵢ)

- **φ ≈ 1** → equidispersão confirmada → mantém-se a **Poisson** (modelo mais
  parcimonioso, ideal com poucos dados).
- **φ > 1,5** → superdispersão → o motor escala para a **Binomial Negativa /
  quasi-Poisson**: os intervalos de confiança são **alargados por √φ** e a
  significância passa a usar um **p-valor robusto** (z' = z/√φ). Assim o modelo
  **nunca fica confiante demais**.

## Poisson e Binomial Negativa não são opostas — são aninhadas

A Binomial Negativa (Pascal) é a Poisson cuja taxa **não é fixa**, mas varia de
operador para operador (mistura Poisson–Gama); é exatamente isso que produz
variância maior que a média. A **Poisson é o caso particular** da Binomial
Negativa **sem dispersão extra**. A estratégia é começar pela mais simples
(parcimônia) e ativar a mais robusta **apenas quando os próprios dados pedem** —
o que se traduz em segurança: não se sinaliza um operador com base em otimismo
do modelo.

## "Quando?" — turnos até o próximo incidente (Geométrica = Binomial Negativa r=1)

A mesma Binomial Negativa que dá robustez à contagem (seção anterior) responde a
uma pergunta que a Poisson sozinha não responde: **em quantos turnos** deve ocorrer
o próximo incidente. Tratando cada turno como um ensaio de Bernoulli cujo "sucesso"
é ter ao menos um evento (probabilidade `p = 1 − e^(−λ̂)`), o número de turnos até
o próximo incidente segue a **Geométrica** — que é a Pascal / Binomial Negativa com
**r = 1** ("número de tentativas até o 1º sucesso"):

    E[turnos até o próximo] = 1 / p           (Pascal geral: r/p até o r-ésimo incidente)
    P(≥1 incidente em m turnos) = 1 − (1 − p)^m

A faixa otimista–pessimista usa o **intervalo de confiança robusto** de λ̂ (já
alargado por √φ): uma taxa maior implica espera menor, e vice-versa. Assim o mesmo
modelo entrega as duas metades da decisão preventiva: **a probabilidade** (Poisson,
"qual a chance no próximo turno") e **o tempo** (Geométrica/BN, "quantos turnos até
o próximo"). O gestor não só sabe *quem* está em risco, mas *quando* agir.

## Onde isso aparece no sistema

- **API** (`/api/risk`): expõe o diagnóstico do grupo em `dispersion` (φ,
  recomendação e o parâmetro `r` da Binomial Negativa) e, por operador, os campos
  `model` (Poisson ou Poisson + BN), `p_value_robust` e o tempo de espera
  `eta_shifts` / `eta_low` / `eta_high` (turnos até o próximo incidente).
- **Dashboard**: mostra um selo de validação — **“Poisson validada”** (φ ≈ 1) ou
  **“Binomial Negativa / quasi-Poisson ativada”** (φ > 1,5) — a coluna **Modelo**,
  o p-valor robusto e uma linha de destaque **“Próximo incidente previsto para
  OP-xxx em ~N turnos”**, além do tempo de espera por operador na tabela de risco.
- **Autoteste** (`python risk_engine.py`): imprime λ₀, φ, a coluna `p(robust)` e o
  efeito da correção no intervalo (Poisson puro vs ×√φ), com verificações
  automáticas de que o outlier permanece sinalizado de forma robusta e nenhum
  operador normal é falsamente acusado.
