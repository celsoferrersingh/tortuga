#!/bin/bash
# ╔══════════════════════════════════════════════════════════╗
# ║  build_mac.sh — Build Tortuga para macOS ARM (Apple M*)  ║
# ║  Pré-requisito: Python ARM64, venv_m4 ativado            ║
# ╚══════════════════════════════════════════════════════════╝
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SERVER_DIR="$SCRIPT_DIR/server"
VENV="$SERVER_DIR/venv_m4"

echo ""
echo "  🔵 Tortuga — Build macOS ARM"
echo "  ────────────────────────────"

# Ativa venv
if [ -f "$VENV/bin/activate" ]; then
    source "$VENV/bin/activate"
    echo "  ✅ venv_m4 ativado"
else
    echo "  ❌ venv_m4 não encontrado em $VENV"
    echo "     Execute primeiro: cd server && python3 -m venv venv_m4"
    exit 1
fi

# Instala PyInstaller se necessário
if ! python -c "import PyInstaller" &>/dev/null; then
    echo "  📦 Instalando PyInstaller..."
    pip install pyinstaller --break-system-packages 2>/dev/null || pip install pyinstaller
fi

# Verifica modelo
if [ ! -f "$SERVER_DIR/models/best.pt" ]; then
    echo "  ❌ Modelo não encontrado: server/models/best.pt"
    exit 1
fi

echo "  🔨 Iniciando build..."
cd "$SCRIPT_DIR"

# Limpa builds anteriores
rm -rf build dist

# Build
python -m PyInstaller tortuga.spec \
    --clean \
    --noconfirm \
    --log-level WARN

# Verifica resultado
if [ -d "dist/Tortuga.app" ]; then
    SIZE=$(du -sh dist/Tortuga.app | cut -f1)
    echo ""
    echo "  ✅ Build concluído!"
    echo "  📦 Arquivo: dist/Tortuga.app  ($SIZE)"
    echo ""
    echo "  Para instalar: arraste dist/Tortuga.app para /Applications"
    echo "  Para testar : open dist/Tortuga.app"
    echo ""
    # Cria DMG simples
    if command -v hdiutil &>/dev/null; then
        echo "  📀 Criando Tortuga.dmg..."
        hdiutil create -volname "Tortuga PPE Monitor" \
            -srcfolder dist/Tortuga.app \
            -ov -format UDZO \
            dist/Tortuga_macOS_ARM.dmg 2>/dev/null && \
            echo "  ✅ DMG: dist/Tortuga_macOS_ARM.dmg" || \
            echo "  ⚠  DMG falhou — use o .app diretamente"
    fi
else
    echo "  ❌ Build falhou. Verifique os erros acima."
    exit 1
fi
