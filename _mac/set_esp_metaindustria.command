#!/bin/bash
# Tortuga (macOS) — registra o cinto ESP32 para as 4 cameras da config
cd "$(dirname "$0")"; ROOT="$(pwd)"
source "$ROOT/server/venv_m4/bin/activate" 2>/dev/null || { echo "Rode ./setup_mac.command"; read -p "Enter..."; exit 1; }
read -p "  Digite o IP do ESP (ex.: 10.14.22.10): " ESPIP
python "$ROOT/server/set_esp.py" --metaindustria --url "http://$ESPIP"
read -p "  Enter para fechar..."
