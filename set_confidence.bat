@echo off
REM Tortuga - Ajusta a confianca minima do YOLO (padrao 45%). Depois reinicie o run_demo.
cd /d "C:\tortuga\server"
set /p CONF="Confianca em %% (Enter = 45): "
if "%CONF%"=="" set CONF=45
"C:\tortuga\server\venv_win\Scripts\python.exe" set_confidence.py --value 0.%CONF%
pause
