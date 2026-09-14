#!/bin/bash
# Tortuga (macOS) — demo com a webcam (MPS)
cd "$(dirname "$0")"; ROOT="$(pwd)"; SERVER="$ROOT/server"
if [ ! -f "$SERVER/venv_m4/bin/activate" ]; then
  echo "  Rode primeiro: ./setup_mac.command"; read -p "  Enter..."; exit 1
fi
source "$SERVER/venv_m4/bin/activate"
cd "$SERVER"
python dashboard.py &
DASH=$!
sleep 6
open "http://localhost:5005"
open "http://localhost:5005/checkin"
python gui.py --camera 0 --device mps --confidence 0.45 --ingest --station-id EST-PRE
kill $DASH 2>/dev/null
