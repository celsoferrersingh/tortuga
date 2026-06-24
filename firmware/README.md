# Firmware do cinto — ESP32 (Fase 3)

Nó de borda que recebe o veredito do Tortuga e responde no posto: OLED, LEDs,
buzzer e vibração. O backend (`server/notifier.py`) faz `POST http://<ip>/status`.

## Bibliotecas (Arduino IDE → Library Manager)
- Adafruit SSD1306
- Adafruit GFX Library
- ArduinoJson

Placa: **ESP32 Dev Module** (instale o core "esp32 by Espressif").

## Ligações (ESP32 DevKit v1)
| Componente | Pino ESP32 | Observação |
|---|---|---|
| OLED SDA | GPIO21 | I²C |
| OLED SCL | GPIO22 | I²C |
| OLED VCC / GND | 3V3 / GND | endereço 0x3C |
| LED verde | GPIO25 | + resistor 220 Ω |
| LED vermelho | GPIO26 | + resistor 220 Ω |
| Buzzer (passivo) | GPIO27 | canal LEDC |
| Motor de vibração | GPIO14 | via transistor NPN/MOSFET + diodo flyback |

> O motor de vibração **não** liga direto no GPIO (corrente alta): use um
> transistor (ex.: 2N2222/BC548) ou MOSFET com diodo de roda-livre.

## Protocolo
`POST /status`  (JSON):
```json
{ "status": "VIOLACAO", "severity": "critica", "message": "Capacete necessário", "epi": "Capacete" }
```
- `status: CONFORME` → LED verde, sem alarme.
- `severity: alta` → vermelho fixo, bipes espaçados, vibração curta.
- `severity: critica` → vermelho rápido, bipes 2,3 kHz, vibração forte.
- `severity: informativa` → só dashboard (não aciona o cinto).

## Passos
1. Edite `WIFI_SSID` / `WIFI_PASS` no `.ino`.
2. Carregue na placa; abra o Monitor Serial (115200) e anote o **IP do ESP32**.
3. Cadastre esse IP no campo `esp32_url` da estação (ex.: `http://192.168.0.42`).
4. Teste: `curl -X POST http://192.168.0.42/status -H "Content-Type: application/json" -d "{\"status\":\"VIOLACAO\",\"severity\":\"critica\",\"message\":\"Teste\",\"epi\":\"Capacete\"}"`

## Fase 4 — Energia (meta: 1–2 pilhas AA por turno de 8 h)

**Decisão de engenharia (honesta):** para um wearable de *segurança*, latência
importa — o alerta crítico precisa chegar em <1 s. Por isso **não** usamos
deep-sleep (que desliga o rádio e cega o cinto) nem trocamos para *pull* lento.
Em vez disso, mantemos o modelo *push* e cortamos o consumo com **modem-sleep**.

| Técnica (implementada no `.ino`) | Efeito |
|---|---|
| `esp_wifi_set_ps(WIFI_PS_MIN_MODEM)` | O rádio dorme entre beacons e acorda no DTIM para receber o push. Consumo médio cai de **~120 mA** para **~20–40 mA**, **sem** perder a latência <1 s. |
| OLED apaga após 30 s em CONFORME | Economiza os ~10–15 mA da tela; o LED verde segue indicando "ok". Qualquer alerta reacende. |
| Buzzer/vibração só pulsam em alerta | Picos raros e curtos; média desprezível no turno. |

**Orçamento aproximado.** 2× AA ≈ 2500–2900 mAh. A ~30 mA médios →
**~80–95 h** de autonomia teórica, com folga para um turno de 8 h mesmo
considerando perdas e picos de TX. (Em RX contínuo, sem modem-sleep, seriam
~24 h — já passaria de 8 h, mas com muito menos margem.)

**Variante ultra-baixo-consumo (opcional, *pull*).** Se o cliente exigir vários
dias por carga e tolerar latência de ~1–2 s no alerta, dá para inverter para
*pull*: o ESP consulta `GET /api/belt-status?device_id=<cinto>` a cada ~1,5 s
com light-sleep entre as consultas. Isso troca latência por autonomia — não é o
default justamente por causa do requisito de segurança em tempo real.
