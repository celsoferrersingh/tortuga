#!/bin/bash
# Tortuga (macOS) — diagnostico do ambiente
cd "$(dirname "$0")"; ROOT="$(pwd)"
if [ ! -f "$ROOT/server/venv_m4/bin/activate" ]; then
  echo "  Rode primeiro: ./setup_mac.command"; read -p "  Enter..."; exit 1
fi
source "$ROOT/server/venv_m4/bin/activate"
cd "$ROOT/server"
python tortuga_doctor.py
read -p "  Enter para fechar..."
