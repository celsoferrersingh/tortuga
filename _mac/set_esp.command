#!/bin/bash
# Tortuga (macOS) — registra o IP do cinto ESP32 (demo em casa · EST-PRE)
cd "$(dirname "$0")"; ROOT="$(pwd)"
source "$ROOT/server/venv_m4/bin/activate" 2>/dev/null || { echo "Rode ./setup_mac.command"; read -p "Enter..."; exit 1; }
read -p "  Digite o IP do ESP (ex.: 10.14.22.10): " ESPIP
python "$ROOT/server/set_esp.py" --url "http://$ESPIP"
read -p "  Enter para fechar..."
