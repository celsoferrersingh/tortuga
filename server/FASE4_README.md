# Fase 4 — Solução integrada, replicável e robusta · Projeto Tortuga

Fundação da Fase 4: rodar em **qualquer ambiente industrial**, com **múltiplos
pontos de visão** e **robustez a iluminação adversa**. Tudo se apoia na pilha já
validada das Fases 1–3 (não reimplementa detecção).

## 1. Compatibilidade / multi-ambiente

"Na minha máquina roda; e no hardware da metaindústria?" — rode o diagnóstico
**antes** de subir o sistema:

```
python tortuga_doctor.py            # checa device, libs, modelos
python tortuga_doctor.py --camera 0 # também testa abrir a câmera
```

Ele reporta SO, Python, OpenCV, Torch (CUDA/Metal/CPU), Ultralytics, presença
dos modelos e câmera, e devolve exit-code (0 = pronto).

**Device automático e portátil.** A inferência escolhe sozinha o melhor device:
`Metal (MPS) → CUDA → CPU`. Em hardware sem GPU **não quebra**: cai para CPU
(reduza `--det-size` para 480 se faltar FPS). Para forçar:

```
python gui.py --device cpu          # ou: set TORTUGA_DEVICE=cpu  (Windows)
```

> Lembrete: no Windows, use o `venv` com torch CUDA (`run_demo.bat`), não o
> Python da Microsoft Store (que só tem torch CPU).

## 2. Múltiplos pontos de visão (várias câmeras)

Cada câmera é uma **estação** com seu `station_id`, todas alimentando o **mesmo**
dashboard, que já agrega por estação e resolve o operador ativo (check-in QR).

1. Copie `tortuga.config.example.json` para `tortuga.config.json` e ajuste as
   câmeras (`source` aceita webcam `0/1`, arquivo de vídeo ou `rtsp://` de câmera IP).
2. Suba todas as estações de uma vez:

```
python run_multicam.py              # uma janela/estação por câmera
python run_multicam.py --dry-run    # só mostra os comandos
```

Replicável por design: adicionar um ponto de visão = mais uma entrada no JSON.

## 3. Robustez a iluminação adversa

Antes da inferência, o frame é normalizado (módulo `preprocess.py`):

- **CLAHE** (equalização adaptativa local) realça contraste sem estourar áreas claras;
- **Gama automática** clareia cena escura / escurece cena estourada, mirando um
  brilho-alvo medido no próprio frame.

A tela mostra a cena **real**; só a cópia enviada ao modelo é tratada. Ativar:

```
python gui.py --preprocess
```

Validação: cena escura (brilho 0,11 → 0,45), estourada (0,91 → 0,66), normal
(0,50 → 0,51) — todas convergem ao alvo, ajudando o modelo a manter EPIs
pequenos (óculos, protetor) detectáveis.

## 4. Auditabilidade (trilha imutável + exportação assinada)

Cada evento detectado entra numa cadeia **append-only encadeada por hash**
(`audit_chain`): adulterar/remover qualquer registro quebra a cadeia. Verificação
e exportação assinada (HMAC do hash-cabeça, segredo em `TORTUGA_AUDIT_SECRET`),
filtrável por operador / estação(câmera) / turno / área.

```
python audit_export.py --worker OP-007      # gera CSV + HTML assinados
```
No dashboard: `GET /api/audit/verify` (integridade) e `GET /api/audit/export?format=csv|html`.

## 5. Modo headless (câmera IP, sem janela)

Para servidor sem monitor com câmeras RTSP, use `headless.py` (mesmo detector,
sem GUI, reconecta sozinho) — ou marque `"headless": true` na câmera do
`tortuga.config.json` e o `run_multicam.py` sobe nesse modo:

```
python headless.py --camera rtsp://user:senha@10.0.0.21/stream1 --station-id EST-PRE --preprocess
```

## 6. Energia do ESP32 (8 h em pilhas AA)

Resolvido por **modem-sleep** (push preservado, latência <1 s) + OLED ocioso —
ver `firmware/README.md` (orçamento de energia). Variante *pull* opcional pelo
endpoint `GET /api/belt-status?device_id=<cinto>`.

## 7. Ajuste fino de robustez em filmagem real

Cada câmera tem uma luz. Rode a calibração na **sua** filmagem e cole o preset
vencedor na câmera da config:

```
python tune_preprocess.py --source corredor.mp4        # compara off/adaptive/CLAHE/gama
python tune_preprocess.py --source frame.jpg --save cmp # salva antes/depois por preset
```

Com o detector instalado, ele ranqueia por **EPIs detectados/frame** (mais
recall sob luz ruim = melhor) e sugere o `preprocess`. Knob por câmera:

```json
{ "station_id": "EST-SOL", "source": "rtsp://…", "preprocess": { "adaptive": true, "clip": 4.0 } }
```

## 8. Fusão multi-câmera (vários ângulos → 1 decisão)

Duas câmeras na **mesma estação** veem a pessoa de ângulos diferentes. Em vez de
cada uma decidir sozinha (e gerar falso "sem capacete" quando o ângulo oculta o
EPI), cada câmera só **reporta** o que vê (`POST /api/observe`) e o servidor funde:

> presentes = **união** dos EPIs vistos por qualquer ângulo · falta só o que
> **nenhuma** câmera vê (com pessoa em cena). Resolve oclusão.

Ative com `--fusion` (gui.py ou headless.py) usando o **mesmo `station_id`** em
2+ câmeras — ou `"fusion": true` na config. Inspeção ao vivo: `GET /api/fusion/<estação>`.

```json
"cameras": [
  { "station_id": "EST-PRE", "name": "Prensa frontal", "source": "0", "fusion": true },
  { "station_id": "EST-PRE", "name": "Prensa lateral", "source": "1", "fusion": true }
]
```

## Próximos incrementos (sugestões)

- Painel de auditoria e de fusão no próprio dashboard (hoje via API/CLI).
- Calibração de homografia entre câmeras p/ casar a MESMA pessoa por geometria (hoje a fusão é por estação).
