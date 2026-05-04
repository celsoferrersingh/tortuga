@echo off
REM ╔══════════════════════════════════════════════════════════╗
REM ║  build_windows.bat — Build Tortuga para Windows x86_64   ║
REM ║  Execute este arquivo em um PC Windows com Python 3.9+   ║
REM ╚══════════════════════════════════════════════════════════╝

echo.
echo   Tortuga ^— Build Windows x86_64
echo   ──────────────────────────────────
echo.

SET SCRIPT_DIR=%~dp0
SET SERVER_DIR=%SCRIPT_DIR%server

REM Verifica Python
python --version >nul 2>&1
IF ERRORLEVEL 1 (
    echo   ERRO: Python nao encontrado.
    echo   Instale em: https://www.python.org/downloads/
    pause & exit /b 1
)

REM Cria venv se nao existir
IF NOT EXIST "%SERVER_DIR%\venv_win\Scripts\activate.bat" (
    echo   Criando ambiente virtual...
    python -m venv "%SERVER_DIR%\venv_win"
)

REM Ativa venv
call "%SERVER_DIR%\venv_win\Scripts\activate.bat"
echo   venv ativado

REM Instala dependencias
echo   Instalando dependencias...
pip install --upgrade pip --quiet
pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu --quiet
pip install ultralytics opencv-python-headless numpy pyinstaller --quiet

REM Verifica modelo
IF NOT EXIST "%SERVER_DIR%\models\best.pt" (
    echo   ERRO: Modelo nao encontrado: server\models\best.pt
    echo   Copie o arquivo best.pt para server\models\
    pause & exit /b 1
)

REM Limpa builds anteriores
IF EXIST "%SCRIPT_DIR%build" rmdir /s /q "%SCRIPT_DIR%build"
IF EXIST "%SCRIPT_DIR%dist"  rmdir /s /q "%SCRIPT_DIR%dist"

echo   Iniciando build ^(pode demorar 5-10 min^)...
cd "%SCRIPT_DIR%"

python -m PyInstaller tortuga.spec --clean --noconfirm --log-level WARN

REM Verifica resultado
IF EXIST "%SCRIPT_DIR%dist\Tortuga.exe" (
    echo.
    echo   Build concluido!
    echo   Executavel: dist\Tortuga.exe
    echo.
    echo   Compacte a pasta dist\ e distribua.
) ELSE (
    echo   Build falhou. Verifique os erros acima.
    pause & exit /b 1
)

pause
