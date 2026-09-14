# Tortuga — versão macOS (Apple Silicon / ARM · Metal-MPS)

Versão do Tortuga para rodar em **Mac com chip Apple (M1/M2/M3…)**. O código é o
mesmo do Windows; a diferença é que no Mac a IA usa **Metal (MPS)** em vez de CUDA,
e a inicialização é por scripts `.command` (não `.bat`).

## Passo 0 — Montar a pasta (no WINDOWS, uma vez)
No PC, dê **duplo clique** em `C:\tortuga\montar_tortuga_mac.bat`. Ele cria
`C:\tortuga_mac` com o código (server + firmware + modelos, **sem** venvs/datasets)
e estes scripts. Depois **leve a pasta `C:\tortuga_mac` inteira para o Mac**
(AirDrop, pen drive ou nuvem).

## Pré-requisitos no Mac
- **Python 3.11+** — se faltar: `brew install python` (ou python.org).
- **Internet** (o setup baixa PyTorch etc., ~1–2 GB).

## Passo a passo (no Mac)
1. Abra o **Terminal** dentro da pasta `tortuga_mac`.
2. Libere os scripts (uma vez):
   ```
   chmod +x *.command
   xattr -dr com.apple.quarantine .
   ```
3. Rode o setup:  `./setup_mac.command`
   (cria o ambiente, instala tudo com Metal/MPS, ajusta o device e roda o diagnóstico)
4. Rodar:
   - Demo com webcam:  `./run_demo.command`
   - Metaindústria (câmeras IP):  edite `server/tortuga.config.json` e rode `./run_metaindustria.command`
   - Diagnóstico:  `./run_doctor.command`
   - Testar zona de exclusão:  `./testar_zona.command`
   - Cinto ESP32:  `./find_esp.command` → `./set_esp_metaindustria.command`

## Observações
- O **device MPS (Metal)** é ajustado automaticamente pelo setup.
- O **modo multitarefa** (pausar a pose ao minimizar) é específico do Windows; no Mac
  o sistema usa a **config mista** (1 câmera com janela + 3 headless), que já vem pronta.
  A pose (Fase 2) roda normal na câmera com janela.
- Se um `.command` não abrir por duplo clique, rode pelo Terminal: `bash setup_mac.command`.
