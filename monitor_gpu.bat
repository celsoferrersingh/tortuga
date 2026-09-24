@echo off
REM Tortuga - Monitor termico da GPU (somente leitura, nao altera nada).
REM Deixe rodando numa janela enquanto o Tortuga opera.
setlocal
cd /d "%~dp0server"
call "%~dp0server\venv_win\Scripts\activate.bat" 2>nul
python monitor_gpu.py
pause
endlocal
