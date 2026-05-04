#!/bin/bash
# ─────────────────────────────────────────────────────────
#  setup.sh — Instala dependências do Tortuga no Mac
# ─────────────────────────────────────────────────────────

set -e
cd "$(dirname "$0")/server"

echo "======================================================"
echo "  Tortuga — Setup de dependências"
echo "======================================================"

# Verifica Python
python3 --version || { echo "Python3 nao encontrado!"; exit 1; }

# Cria venv se não existir
if [ ! -d "venv" ]; then
    echo "Criando ambiente virtual..."
    python3 -m venv venv
fi

source venv/bin/activate
echo "Ambiente virtual: $(which python)"

# Instala dependências
echo ""
echo "Instalando dependências..."
pip install --upgrade pip -q
pip install -r requirements.txt

# Verifica modelo
if [ ! -f "models/best.pt" ]; then
    echo ""
    echo "AVISO: models/best.pt nao encontrado!"
    echo "O modelo YOLOv8 pre-treinado deve estar em server/models/best.pt"
    echo "Verifique se o arquivo foi incluido no repositorio."
fi

# Cria diretórios necessários
mkdir -p data logs screenshots

echo ""
echo "======================================================"
echo "  Setup concluído!"
echo "  Para executar: cd .. && ./run.sh"
echo ""
echo "  Câmera USB:  ./run.sh"
echo "  Câmera WiFi: INTELBRAS_IP=192.168.1.100 INTELBRAS_PASS=senha ./run.sh"
echo "======================================================"
