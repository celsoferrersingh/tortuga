@echo off
REM setup_gpu.bat - Tortuga PPE Monitor
REM Configura ambiente com suporte a GPU NVIDIA (CUDA 12.4)
REM Compativel com RTX 4050 / 4060 / 4070 / 3xxx / 2xxx

echo.
echo   ==========================================
echo   Tortuga PPE Monitor - Setup GPU
echo   RTX 4050 + CUDA 12.4
echo   ==========================================
echo.

SET SCRIPT_DIR=%~dp0
SET SERVER_DIR=%SCRIPT_DIR%server
SET VENV_DIR=%SERVER_DIR%\venv_win

REM -- 1. Verifica Python ----------------------------------------
python --version >nul 2>&1
IF ERRORLEVEL 1 (
    echo   [ERRO] Python nao encontrado.
    echo   Instale em: https://www.python.org/downloads/
    echo   Marque "Add Python to PATH" durante a instalacao!
    pause & exit /b 1
)
echo   [OK] Python encontrado:
python --version
echo.

REM -- 2. Cria venv ----------------------------------------------
IF NOT EXIST "%VENV_DIR%\Scripts\activate.bat" (
    echo   Criando ambiente virtual em server\venv_win ...
    python -m venv "%VENV_DIR%"
    echo   [OK] venv criado
) ELSE (
    echo   [OK] venv ja existe
)
echo.

REM -- 3. Ativa venv ---------------------------------------------
call "%VENV_DIR%\Scripts\activate.bat"
echo   [OK] venv ativado
echo.

REM -- 4. Atualiza pip -------------------------------------------
echo   Atualizando pip...
python -m pip install --upgrade pip --quiet
echo   [OK] pip atualizado
echo.

REM -- 5. Instala PyTorch com CUDA 12.4 --------------------------
echo   Instalando PyTorch com suporte CUDA 12.4 (Python 3.13)...
echo   (Pode demorar alguns minutos - cerca de 2.5 GB de download)
echo.
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu124
IF ERRORLEVEL 1 (
    echo.
    echo   [ERRO] Falha ao instalar PyTorch CUDA.
    echo   Verifique sua conexao com a internet e tente novamente.
    pause & exit /b 1
)
echo.
echo   [OK] PyTorch CUDA instalado
echo.

REM -- 6. Instala demais dependencias ----------------------------
echo   Instalando ultralytics, opencv, numpy...
pip install ultralytics opencv-python numpy --quiet
IF ERRORLEVEL 1 (
    echo   [ERRO] Falha ao instalar dependencias.
    pause & exit /b 1
)
echo   [OK] Dependencias instaladas
echo.

REM -- 7. Verifica modelo ----------------------------------------
IF NOT EXIST "%SERVER_DIR%\models\best.pt" (
    echo   [ATENCAO] Modelo nao encontrado!
    echo   Copie o arquivo best.pt para:
    echo   C:\tortuga\server\models\best.pt
    echo   Depois rode: run_gpu.bat
) ELSE (
    echo   [OK] Modelo encontrado: server\models\best.pt
)
echo.

REM -- 8. Verifica GPU via Python --------------------------------
echo   Verificando GPU detectada pelo PyTorch...
echo.
python -c "import torch; gpu=torch.cuda.is_available(); name=torch.cuda.get_device_name(0) if gpu else 'N/A'; print('  CUDA disponivel : ' + str(gpu)); print('  GPU detectada   : ' + name); print('  CUDA version    : ' + str(torch.version.cuda))"
echo.

REM -- 9. Cria atalho de execucao --------------------------------
echo   Criando run_gpu.bat...
(
echo @echo off
echo call "%VENV_DIR%\Scripts\activate.bat"
echo cd "%SERVER_DIR%"
echo python gui.py --confidence 0.4
echo pause
) > "%SCRIPT_DIR%run_gpu.bat"
echo   [OK] run_gpu.bat criado na raiz do projeto
echo.

echo   ==========================================
echo   Setup concluido!
echo   Proximo passo: execute run_gpu.bat
echo   ==========================================
echo.
pause
