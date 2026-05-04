#!/bin/bash
# ─────────────────────────────────────────────────────────
#  run.sh — Inicia o Tortuga / SPI SafeGuard
#  Uso: ./run.sh [opções]
# ─────────────────────────────────────────────────────────

set -e
cd "$(dirname "$0")"

# ─── Verifica ambiente virtual ───────────────────────────
if [ ! -d "venv" ]; then
    echo "Ambiente virtual nao encontrado. Execute ./setup.sh primeiro."
    exit 1
fi

source venv/bin/activate

# ─── Parâmetros ──────────────────────────────────────────
CAMERA="${CAMERA:-0}"          # 0 = USB padrão
PORT="${PORT:-5000}"
FPS_SKIP="${FPS_SKIP:-2}"      # Detecta a cada 2 frames (melhora FPS)

# Detecta WiFi Intelbras iM3 automaticamente se IP passado
if [ ! -z "$INTELBRAS_IP" ]; then
    INTELBRAS_PASS="${INTELBRAS_PASS:-}"
    CAMERA="rtsp://admin:${INTELBRAS_PASS}@${INTELBRAS_IP}/cam/realmonitor?channel=1&subtype=0"
    echo "Usando camera Intelbras iM3 WiFi: $INTELBRAS_IP"
fi

echo "======================================================"
echo "  Tortuga / SPI SafeGuard"
echo "======================================================"
echo "  Camera : $CAMERA"
echo "  Porta  : $PORT"
echo "  FPS Skip: $FPS_SKIP"
echo "  Dashboard: http://localhost:$PORT"
echo "======================================================"
echo ""

cd server
python main.py \
    --camera "$CAMERA" \
    --port "$PORT" \
    --fps-skip "$FPS_SKIP" \
    "$@"
