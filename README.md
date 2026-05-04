# Tortuga — Deteccao de EPI em Tempo Real

Sistema de visao computacional para deteccao automatica de Equipamentos de Protecao Individual (EPI) em ambiente industrial. Usa cameras IP, YOLOv8 e ESP32 para monitorar estacoes de trabalho e bloquear maquinas quando ha violacao de EPI.

## Arquitetura

```
Camera IP ──RTSP/WiFi──> Servidor (YOLOv8) ──HTTP/WiFi──> ESP32 ──GPIO──> Rele
```

1. Camera IP transmite stream RTSP via WiFi
2. Servidor consome o stream e roda YOLOv8 no frame
3. Se violacao de EPI detectada → servidor envia comando pro ESP32
4. ESP32 aciona rele (bloqueia maquina)
5. Se EPI ok → servidor libera o rele

## Hardware por estacao

- 1x Camera IP (Tapo C200/C210 ou similar com RTSP)
- 1x ESP32 + modulo rele 1 canal com optoacoplador

## Estrutura do projeto

```
tortuga/
├── esp32/                          # Firmware do ESP32
│   ├── relay_controller/
│   │   ├── relay_controller.ino    # Firmware Arduino
│   │   └── config.h                # WiFi, GPIO, porta HTTP
│   └── README.md                   # Instrucoes de flash e fiacao
├── server/                         # Servidor Python unificado
│   ├── main.py                     # Entry point
│   ├── detector.py                 # YOLOv8 deteccao de EPI
│   ├── station_manager.py          # Gerencia N estacoes em threads
│   ├── stream_reader.py            # Consome RTSP com reconexao
│   ├── relay_client.py             # HTTP client pro ESP32
│   ├── app.py                      # Flask: dashboard + API REST
│   ├── database.py                 # SQLite (stations + violations)
│   ├── alarm_player.py             # Alarme sonoro
│   ├── detection_status.py         # Estado de deteccao
│   ├── utils.py                    # Helpers (desenho, FPS, screenshots)
│   ├── logger.py                   # Logger rotativo
│   ├── config/
│   │   └── stations_seed.json      # Seed para primeira execucao
│   ├── models/
│   │   ├── best.pt                 # Modelo treinado
│   │   └── yolov8n.pt              # Modelo base
│   ├── templates/
│   │   └── dashboard.html          # Dashboard multi-estacao
│   ├── static/
│   │   ├── style.css
│   │   └── alarm.wav
│   ├── tests/
│   └── requirements.txt
└── docs/
```

## Classes detectadas

| Classe         | Significado       | Cor      |
| -------------- | ----------------- | -------- |
| Hardhat        | Capacete presente | Verde    |
| NO-Hardhat     | Sem capacete      | Vermelho |
| Safety Vest    | Colete presente   | Verde    |
| NO-Safety Vest | Sem colete        | Vermelho |
| Mask           | Mascara presente  | Verde    |
| NO-Mask        | Sem mascara       | Vermelho |

## Requisitos

- Python 3.10+
- Webcam ou camera IP com stream RTSP
- ESP32 com modulo rele (opcional — o servidor funciona sem)

## Instalacao

### Servidor

```bash
cd server

# Criar ambiente virtual
python -m venv venv
source venv/bin/activate  # macOS/Linux
# venv\Scripts\activate   # Windows

# Instalar dependencias
pip install -r requirements.txt
```

### ESP32

1. Abra `esp32/relay_controller/relay_controller.ino` na Arduino IDE
2. Instale o ESP32 Board Package (Board Manager > esp32 by Espressif)
3. Edite `config.h` com o SSID e senha da sua rede WiFi
4. Selecione a placa ESP32 e faca upload

Fiacao:

```
ESP32 GPIO2 --> IN do modulo rele
ESP32 GND   --> GND do modulo rele
ESP32 5V    --> VCC do modulo rele (via VIN)
```

## Como usar

### 1. Configurar estacoes

Edite `server/config/stations_seed.json` com as URLs das suas cameras e ESP32s:

```json
[
  {
    "id": "solda-01",
    "name": "Estacao Solda",
    "camera_url": "rtsp://192.168.1.10:554/stream1",
    "esp32_url": "http://192.168.1.20",
    "required_epis": ["Hardhat", "Mask", "Safety Vest"],
    "confidence": 0.4,
    "enabled": true
  }
]
```

O seed so e carregado na primeira execucao (banco vazio). Depois, use a API ou o dashboard para gerenciar estacoes.

### 2. Iniciar o servidor

```bash
cd server

# Uso basico (carrega seed e inicia)
python main.py

# Especificar porta e modelo
python main.py --port 8080 --model models/best.pt

# Salvar screenshots de violacoes
python main.py --save-violations

# Ajustar intervalo de registro de violacoes (segundos)
python main.py --violation-interval 10
```

### 3. Acessar o dashboard

Abra no navegador: `http://localhost:5000`

O dashboard mostra:

- Cards com stream ao vivo de cada estacao
- Status: verde (ok), vermelho (bloqueado), cinza (offline)
- EPIs obrigatorios e FPS de cada estacao
- Historico de violacoes
- Formulario para criar/remover estacoes

### 4. Gerenciar via API

```bash
# Listar estacoes
curl http://localhost:5000/api/stations

# Criar estacao
curl -X POST http://localhost:5000/api/stations \
  -H "Content-Type: application/json" \
  -d '{"id":"corte-01","name":"Estacao Corte","camera_url":"rtsp://192.168.1.11:554/stream1","esp32_url":"http://192.168.1.21","required_epis":["Hardhat"]}'

# Editar estacao
curl -X PUT http://localhost:5000/api/stations/corte-01 \
  -H "Content-Type: application/json" \
  -d '{"confidence":0.5,"required_epis":["Hardhat","Safety Vest"]}'

# Desabilitar/habilitar estacao
curl -X POST http://localhost:5000/api/stations/corte-01/disable
curl -X POST http://localhost:5000/api/stations/corte-01/enable

# Remover estacao
curl -X DELETE http://localhost:5000/api/stations/corte-01

# Historico de violacoes
curl http://localhost:5000/api/violations?limit=20
curl http://localhost:5000/api/violations?station_id=solda-01

# Estatisticas
curl http://localhost:5000/api/violations/stats

# Silenciar alarme
curl -X POST http://localhost:5000/api/silence
```

## Argumentos do servidor

| Argumento              | Padrao                      | Descricao                              |
| ---------------------- | --------------------------- | -------------------------------------- |
| `--model`              | `models/best.pt`            | Caminho para o modelo YOLOv8           |
| `--db`                 | `data/tortuga.db`           | Caminho do banco SQLite                |
| `--seed`               | `config/stations_seed.json` | JSON seed de estacoes                  |
| `--port`               | `5000`                      | Porta do servidor web                  |
| `--host`               | `0.0.0.0`                   | Host do servidor                       |
| `--save-violations`    | desligado                   | Salvar screenshots de violacoes        |
| `--violation-interval` | `5.0`                       | Intervalo minimo (seg) entre registros |

## Endpoints do ESP32

| Metodo | Rota         | Descricao                              |
| ------ | ------------ | -------------------------------------- |
| GET    | `/status`    | `{"relay":"on"\|"off","uptime":12345}` |
| POST   | `/relay/on`  | Aciona rele (bloqueia maquina)         |
| POST   | `/relay/off` | Desaciona rele (libera maquina)        |

Fail-safe: se o ESP32 nao receber comando por 30 segundos, bloqueia automaticamente.

## Tratamento de falhas

| Falha                     | Comportamento                                              |
| ------------------------- | ---------------------------------------------------------- |
| Camera IP cai             | Reconexao automatica a cada 5s. Dashboard mostra "offline" |
| ESP32 nao responde        | Log de warning. Dashboard mostra "ESP32 offline"           |
| ESP32 sem comando por 30s | Fail-safe: ESP32 bloqueia sozinho                          |
| Servidor cai              | ESP32 fail-safe bloqueia apos 30s                          |

## Testes

```bash
cd server
python -m pytest tests/ -v
```
