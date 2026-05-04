@echo off
echo.
echo   Tortuga - Treino do modelo de oculos
echo   RTX 4050 + CUDA
echo   ======================================
echo.

SET SCRIPT_DIR=%~dp0
SET SERVER_DIR=%SCRIPT_DIR%server
SET VENV_DIR=%SERVER_DIR%\venv_win

REM Instala pyyaml se necessario
call "%VENV_DIR%\Scripts\activate.bat"
pip install pyyaml --quiet

echo   Iniciando treino (~10-15 min na RTX 4050)...
echo.

cd "%SERVER_DIR%"
python train_oculos.py

echo.
pause
