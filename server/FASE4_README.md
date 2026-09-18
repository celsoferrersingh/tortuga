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

## 9. Zonas de exclusão de máquina (falso positivo estrutural)

Apontamento de campo: um **braço robótico fixo** era detectado como pessoa,
contaminando EPI *e* postura. Zonas de exclusão são retângulos normalizados
`[x1,y1,x2,y2]` que **subtraem** a região da análise (o oposto da zona de risco,
que gera alerta). Valem para `gui.py` **e** `headless.py`.

O gestor desenha em `/config` **sobre o quadro real da câmera** (cada detector
envia um JPEG a cada ~5 s, que vira o fundo do canvas). A mudança chega ao
detector em ~4 s, sem reiniciar. Também aceita o caminho por arquivo:

```json
{ "station_id": "EST-FRESA2", "ignore": [[0.52, 0.26, 0.88, 1.0]] }
```

## 10. Calibração do detector por ESTAÇÃO

O limiar de confiança é propriedade do **arranjo óptico**, não do trabalhador —
fica na estação, não no perfil. Todos os operadores daquela câmera são medidos
com o **mesmo instrumento**, condição para o teste de hipóteses contra λ0 ser
válido. Cada evento grava o limiar usado (campo `confidence`, também na trilha
de auditoria).

> Atenção ao sentido: modelo só-positivos ⇒ EPI não detectado = ausente. **Subir**
> o limiar **aumenta** as violações registradas; **baixar** mascara violações reais.

```
python set_confidence.py --list
python set_confidence.py --value 0.45 [--station EST-FRESA1]
```

## 11. Instrumentação de diagnóstico de campo

Implantação real quebra por rede, não por modelo. Utilitários criados na
metaindústria (reduzem o diagnóstico de horas para minutos):

| Ferramenta | Para que serve |
|---|---|
| `check_rtsp.bat` | A máquina alcança a câmera? A porta 554 responde? |
| `diag_rtsp.py --ip X --compare` | Compara stream principal × secundário (tempo e resolução). |
| `diag_rtsp.py --ips A,B,C` | Salva um print de cada câmera em `cams_preview/` para identificar qual é qual. |
| `find_cams.bat` | Varre a sub-rede procurando câmeras (porta 554 aberta). |

**Achados que viraram requisito:** endereços de câmera **mudam entre visitas**
(um deles deixou de existir); câmeras de **lotes diferentes usam senhas
diferentes** (a config suporta credencial por câmera); e o **stream principal**
em 1080p é instável sobre Wi-Fi — como a inferência reduz para 640 px, o
**secundário** entrega a mesma qualidade útil com fração da banda.

## 12. Cinto em rede corporativa (isolamento de clientes)

O ESP conectava ao Wi-Fi, mas o servidor não o alcançava: a rede isola clientes
entre si. Solução sem depender da TI do cliente: o PC publica um **ponto de
acesso próprio em 2,4 GHz** só para o cinto, enquanto segue na rede da planta
para as câmeras. O SSID fica salvo na flash do ESP, que reconecta sozinho.
Validado em campo: violação aciona som/visual/tátil, normalização volta ao verde.

## Próximos incrementos (sugestões)

- Painel de auditoria e de fusão no próprio dashboard (hoje via API/CLI).
- Calibração de homografia entre câmeras p/ casar a MESMA pessoa por geometria (hoje a fusão é por estação).
