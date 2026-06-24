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

**Perfis por operador:** cada perfil define **quais EPIs monitorar** e a
**confiança mínima do YOLO** — configurável pelo gestor na tela `/config`.
Assim a Pessoa A (estamparia) e a Pessoa B (qualidade) têm regras diferentes,
mesmo compartilhando cintos entre turnos.

**Zonas de risco configuráveis por nível:** o gestor desenha polígonos em
`/config` (clicando os vértices) e escolhe o nível (crítica/alta/informativa);
o `gui.py` aplica as zonas sobre o vídeo e a entrada na zona aciona o alerta.

## Módulos (em `server/`)

| Arquivo | Papel |
|---|---|
| `risk_engine.py` | Motor preditivo: Poisson + TLC + teste de hipóteses. |
| `events_store.py` | Perfis (EPIs/confiança), cintos (device↔operador), zonas e eventos. |
| `seed_events.py` | Dados sintéticos realistas (perfis, cintos, zonas, eventos). |
| `severity.py` / `notifier.py` | Severidade (3 níveis) + envio ao ESP (HTTP) e gestão. |
| `dashboard.py` | Flask: dashboard + `/config` + `/checkin` + APIs. |
| `dashboard_client.py` | Ponte `gui.py → dashboard`: ingestão real, perfil ativo, zonas. |
| `gen_qr.py` | Gera os QR dos cintos + folha imprimível. |
| `templates/` | `dashboard.html`, `config.html`, `checkin.html`. |
| `../firmware/tortuga_esp32/` | Sketch do cinto (OLED + LED + buzzer + vibração). |

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
1. Abra o `/config` e mostre os EPIs e a confiança **por perfil** + uma zona desenhada.
2. No celular, escaneie o QR do cinto → escolha o operador → **check-in** (o perfil entra em vigor).
3. Rode o `gui.py --ingest`: cometa uma violação na câmera → o evento real entra no
   `/api/ingest`, é **atribuído ao operador ativo** e aparece no dashboard na hora; a
   probabilidade dele se move. Narrativa: *"o histórico é a base; este evento é real, agora."*

## APIs principais
- `GET/POST /api/profiles`, `PUT /api/profiles/<id>` — perfis e EPIs/confiança.
- `GET /api/belts`, `POST /api/assign {device_id,worker_id}` — atribuição (QR).
- `GET/POST /api/zones`, `PUT/DELETE /api/zones/<id>` — zonas de risco.
- `POST /api/ingest {station_id,type,epi}` — evento real (resolve o operador ativo).
- `GET /api/risk | /api/stats | /api/timeseries | /api/events` — dashboard.
