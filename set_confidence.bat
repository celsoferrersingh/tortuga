@echo off
REM Tortuga - Calibra a confianca minima do YOLO POR ESTACAO (camera).
REM Aplica em ~4s, sem reiniciar. Subir o limiar tende a AUMENTAR as violacoes.
cd /d "C:\tortuga\server"
set /p CONF="Confianca em %% (Enter = 45): "
if "%CONF%"=="" set CONF=45
"C:\tortuga\server\venv_win\Scripts\python.exe" set_confidence.py --value 0.%CONF%
pause
