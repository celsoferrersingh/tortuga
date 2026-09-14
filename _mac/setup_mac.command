#!/bin/bash
# ============================================================
#  Tortuga — Setup no macOS (Apple Silicon / Metal-MPS)
#  Cria o ambiente, instala tudo e roda o diagnostico.
# ============================================================
cd "$(dirname "$0")"; ROOT="$(pwd)"
SERVER="$ROOT/server"
VENV="$SERVER/venv_m4"

echo ""
echo "  ============================================"
echo "  Tortuga - Setup macOS (Apple Silicon / MPS)"
echo "  ============================================"
echo ""

if ! command -v python3 >/dev/null 2>&1; then
  echo "  [ERRO] Python 3 nao encontrado. Instale: brew install python"
  read -p "  Enter para fechar..."; exit 1
fi
echo "  [OK] Python: $(python3 --version)"

if [ ! -f "$VENV/bin/activate" ]; then
  echo "  Criando ambiente (server/venv_m4)..."
  python3 -m venv "$VENV"
fi
source "$VENV/bin/activate"
echo "  [OK] venv ativado"

echo "  Instalando dependencias (pode demorar alguns minutos)..."
python -m pip install --upgrade pip >/dev/null
pip install torch torchvision ultralytics opencv-python numpy flask "qrcode[pil]" pillow-heif pyobjc-framework-Quartz
if [ $? -ne 0 ]; then
  echo "  [ERRO] Falha ao instalar dependencias. Confira a internet."
  read -p "  Enter para fechar..."; exit 1
fi

# device -> mps (Metal) na config
if [ -f "$SERVER/tortuga.config.json" ]; then
  sed -i '' 's/"device": *"cuda"/"device": "mps"/' "$SERVER/tortuga.config.json" 2>/dev/null || true
  echo "  [OK] device ajustado para MPS (Metal) na config"
fi

chmod +x "$ROOT"/*.command 2>/dev/null || true

echo ""
echo "  Rodando o diagnostico..."
cd "$SERVER"
python tortuga_doctor.py || true

echo ""
echo "  ============================================"
echo "  Setup concluido!"
echo "  Webcam:        ./run_demo.command"
echo "  Metaindustria: ./run_metaindustria.command"
echo "  ============================================"
echo ""
read -p "  Enter para fechar..."
