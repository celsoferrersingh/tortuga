#!/bin/bash
# Tortuga (macOS) — pre-voo da zona de exclusao (webcam)
cd "$(dirname "$0")"; ROOT="$(pwd)"
if [ ! -f "$ROOT/server/venv_m4/bin/activate" ]; then
  echo "  Rode primeiro: ./setup_mac.command"; read -p "  Enter..."; exit 1
fi
source "$ROOT/server/venv_m4/bin/activate"
cd "$ROOT/server"
echo "  Abrindo a webcam com a zona de exclusao no canto direito..."
python gui.py --camera 0 --device mps --confidence 0.45 --ignore "[[0.6,0.4,1.0,1.0]]"
read -p "  Enter para fechar..."
