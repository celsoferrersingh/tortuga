#!/bin/bash
# Tortuga (macOS) — sobe o dashboard + as cameras (config)
cd "$(dirname "$0")"; ROOT="$(pwd)"; SERVER="$ROOT/server"
if [ ! -f "$SERVER/venv_m4/bin/activate" ]; then
  echo "  Ambiente nao encontrado. Rode primeiro: ./setup_mac.command"; read -p "  Enter..."; exit 1
fi
source "$SERVER/venv_m4/bin/activate"
cd "$SERVER"
echo "  Iniciando dashboard..."
python dashboard.py &
DASH=$!
sleep 6
open "http://localhost:5005"
open "http://localhost:5005/checkin"
echo "  Iniciando cameras (tortuga.config.json)... (Ctrl+C encerra)"
python run_multicam.py
kill $DASH 2>/dev/null
