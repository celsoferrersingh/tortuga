#!/bin/bash
# Tortuga (macOS) — descobre o IP do cinto ESP32 na rede
cd "$(dirname "$0")"; ROOT="$(pwd)"
source "$ROOT/server/venv_m4/bin/activate" 2>/dev/null || { echo "Rode ./setup_mac.command"; read -p "Enter..."; exit 1; }
python "$ROOT/server/find_esp.py"
read -p "  Enter para fechar..."
