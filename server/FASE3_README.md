# Fase 3 — Notificação Inteligente + Dashboard Preditivo + Perfis/QR/Zonas

## Arquitetura (resposta aos apontamentos da Banca 2)

**Tudo é processado no servidor; o ESP32 é "burro".** O cinto só guarda um
`device_id` e recebe um JSON curto quando há alerta — sem visão, sem BLE, sem
lógica de perfil. Isso maximiza a duração das pilhas AA (turno de 8 h).

**Identificação por QR (escala para milhares de operadores):** no início do
turno o operador escaneia, com o celular, o QR impresso no cinto
(`/checkin?belt=<device_id>`), confirma quem é, e o **servidor** amarra
`operador ↔ cinto ↔ estação`. O celular fala com o servidor (não com o ESP),
então não há pareamento nem consumo extra no cinto.

**Perfis por operador:** cada perfil define **quais EPIs monitorar** — configurável
pelo gestor na tela `/config`. Assim a Pessoa A (estamparia) e a Pessoa B
(qualidade) têm regras diferentes, mesmo compartilhando cintos entre turnos.

**Calibração por estação (não por pessoa):** o **limiar de confiança do YOLO** é
propriedade do *arranjo óptico* (câmera, luz, distância), não do trabalhador — por
isso fica na **estação**. Todos os operadores que passam por aquela câmera são
medidos com o **mesmo instrumento**, condição para o teste de hipóteses contra λ0
ser válido (limiares por pessoa criariam diferenças de contagem puramente
instrumentais). Atenção ao sentido: o modelo é **só-positivos**, então EPI não
detectado = ausente — **subir** o limiar tende a **aumentar** as violações
registradas; **baixar** tende a **mascarar** violações reais. Cada evento grava o
limiar usado (campo `confidence`, também na trilha de auditoria), permitindo
segmentar a análise por período de calibração. Ajuste em `/config` ou por
`set_confidence.py --value 0.45 [--station EST-X]`; o detector aplica em ~4 s.

**Zonas de risco configuráveis por nível:** o gestor desenha polígonos em
`/config` (clicando os vértices) e escolhe o nível (crítica/alta/informativa);
o `gui.py` aplica as zonas sobre o vídeo e a entrada na zona aciona o alerta.

## Módulos (em `server/`)

| Arquivo | Papel |
|---|---|
| `risk_engine.py` | Motor preditivo: Poisson + TLC + teste de hipóteses + diagnóstico de superdispersão (Binomial Negativa / quasi-Poisson). |
| `events_store.py` | Perfis (EPIs), calibração por estação, cintos (device↔operador), zonas, exclusões e eventos. |
| `seed_events.py` | Dados sintéticos realistas (perfis, cintos, zonas, eventos). |
| `severity.py` / `notifier.py` | Severidade (3 níveis) + envio ao ESP (HTTP) e gestão. |
| `dashboard.py` | Flask: dashboard + `/config` + `/checkin` + APIs. |
| `dashboard_client.py` | Ponte `gui.py → dashboard`: ingestão real, perfil ativo, zonas. |
| `gen_qr.py` | Gera os QR dos cintos + folha imprimível. |
| `templates/` | `dashboard.html`, `config.html`, `checkin.html`. |
| `../firmware/tortuga_esp32/` | Sketch do cinto (OLED + LED + buzzer + vibração). |

## Motor preditivo — Poisson × Binomial Negativa (robustez)

O `risk_engine.py` modela cada operador como um processo de **Poisson**: com `k`
eventos em `t` turnos, a taxa estimada é `λ̂ = k/t` e a probabilidade de ao menos
um incidente no próximo turno vem **direto da Poisson**, `P(N≥1) = 1 − e^(−λ̂)`.
O **TLC** dá a incerteza (`IC 95% = λ̂ ± 1,96·√(λ̂/t)`) e um **teste de hipóteses**
(Poisson exato, `p = P(K ≥ k | λ₀)`) valida quem está acima da base do grupo `λ₀`.

**Validação da premissa (por que combinamos com a Binomial Negativa).** A Poisson
supõe **equidispersão** (variância = média). Quando os operadores são heterogêneos
— alguns concentram quase todas as ocorrências — a variância fica **maior** que a
média (**superdispersão**), e a Poisson pura ficaria *confiante demais* (IC estreito,
p-valor otimista). Por isso o motor **mede a dispersão** com o índice de Pearson

```
φ = (1/gl) · Σ (kᵢ − λ₀·tᵢ)² / (λ₀·tᵢ)
```

- **φ ≈ 1** → equidispersão confirmada → **Poisson** (modelo mais parcimonioso).
- **φ > 1,5** → superdispersão → escala para **Binomial Negativa / quasi-Poisson**:
  os IC são **alargados por √φ** e o p-valor passa a ser **robusto** (`z' = z/√φ`),
  usado na decisão de significância. Assim o modelo **nunca fica confiante demais**.

A Binomial Negativa (Pascal) é a Poisson com taxa que varia (mistura Poisson–Gama),
o que produz variância > média; a **Poisson é o caso particular** sem dispersão
extra. Começamos por ela (parcimônia, pouco dado) e ativamos a BN só quando os
próprios dados pedem. O `/api/risk` expõe o diagnóstico do grupo (`dispersion`: φ,
recomendação, `r` da BN) e, por operador, o `model` e o `p_value_robust`; o
dashboard mostra o selo **“Poisson validada”** ou **“Binomial Negativa ativada”**.

**“Quando?” — turnos até o próximo incidente (Geométrica = Binomial Negativa r=1).**
A Poisson responde *qual a probabilidade* no próximo turno; a Binomial Negativa
responde também *em quantos turnos* o próximo incidente tende a ocorrer. Tratando
cada turno como um ensaio de Bernoulli com “sucesso” = ter ≥1 evento (probabilidade
`p = 1 − e^(−λ̂)`), o número de turnos até o próximo incidente segue a **Geométrica**,
que é a Pascal/Binomial Negativa com **r = 1** (“nº de tentativas até o 1º sucesso”):

```
E[turnos até o próximo] = 1 / p            (Pascal geral: r/p até o r-ésimo incidente)
P(≥1 incidente em m turnos) = 1 − (1 − p)^m
```

A faixa (otimista–pessimista) usa o **IC robusto** de λ̂ (já alargado por √φ): taxa
maior → espera menor; taxa menor → espera maior. O motor expõe `eta_shifts`,
`eta_low` e `eta_high` por operador, e o dashboard traz a linha *“Próximo incidente
previsto para OP-xxx em ~N turnos”* — a mesma Binomial Negativa que dá robustez à
contagem responde “o próximo, quando?”, fechando o ciclo prever → validar → agir.

Autoteste: `python risk_engine.py` imprime λ₀, φ, a coluna `p(robust)` e o efeito
da correção no IC (Poisson puro vs ×√φ), com asserts que garantem que o outlier
segue sinalizado de forma robusta e nenhum operador normal é falsamente acusado.

## Como rodar (e demonstrar na banca)

```bash
cd server
pip install flask "qrcode[pil]"

# 1) Sobe o dashboard (popula dados sintéticos na 1ª vez)
python dashboard.py
#   http://localhost:5005          -> dashboard do gestor
#   http://localhost:5005/config   -> perfis, cintos e zonas
#   http://localhost:5005/checkin  -> check-in do operador (celular)

# 2) Gera os QR dos cintos (use o IP do servidor na rede!)
python gen_qr.py --base http://SEU_IP:5005
#   -> server/qr_cintos/*.png + sheet.html (imprimível)

# 3) Detecção ao vivo enviando eventos REAIS pro dashboard
python gui.py --ingest --station-id EST-PRE --dashboard http://localhost:5005 --det-size 960
```

### Roteiro sugerido da demo (dados reais ao vivo)
1. Abra o `/config`: mostre os **EPIs por perfil**, a **calibração por estação** (com o aviso sobre o sentido do ajuste) e desenhe uma **zona sobre a imagem real** da câmera.
2. No celular, escaneie o QR do cinto → escolha o operador → **check-in** (o perfil entra em vigor).
3. Rode o `gui.py --ingest`: cometa uma violação na câmera → o evento real entra no
   `/api/ingest`, é **atribuído ao operador ativo** e aparece no dashboard na hora; a
   probabilidade dele se move. Narrativa: *"o histórico é a base; este evento é real, agora."*

## APIs principais
- `GET/POST /api/profiles`, `PUT /api/profiles/<id>` — perfis e EPIs monitorados.
- `GET/POST /api/stations`, `GET /api/station-confidence?station_id=` — calibração do detector por estação.
- `GET/POST /api/exclusions`, `PUT/DELETE /api/exclusions/<id>` — zonas de exclusão de máquina.
- `POST /api/snapshot`, `GET /api/snapshot/<station>`, `GET /api/snapshots` — frame da câmera (fundo do `/config`).
- `GET /api/belts`, `POST /api/assign {device_id,worker_id}` — atribuição (QR).
- `GET/POST /api/zones`, `PUT/DELETE /api/zones/<id>` — zonas de risco.
- `POST /api/ingest {station_id,type,epi,confidence}` — evento real (resolve o operador ativo; grava o limiar usado).
- `GET /api/risk | /api/stats | /api/timeseries | /api/events` — dashboard.
  O `/api/risk` inclui `dispersion` (φ, recomendação, `r` da BN) e, por operador,
  `model` e `p_value_robust` (validação Poisson × Binomial Negativa).
