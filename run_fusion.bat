@echo off
REM Tortuga (Passo 8) - Fusao multi-camera: 2 angulos no MESMO posto (EST-PRE)
REM PRE-REQUISITO: o dashboard precisa estar rodando antes (run_dashboard.bat)
REM Precisa de 2 cameras (indices 0 e 1). Veja a fusao em /api/fusion/EST-PRE
cd /d "C:\tortuga\server"
set PY=C:\tortuga\server\venv_win\Scripts\python.exe
start "Tortuga Fusao A (cam 0)" "%PY%" headless.py --camera 0 --station-id EST-PRE --fusion --camera-id CAM-A
start "Tortuga Fusao B (cam 1)" "%PY%" headless.py --camera 1 --station-id EST-PRE --fusion --camera-id CAM-B
echo.
echo Estado fundido ao vivo:  http://localhost:5005/api/fusion/EST-PRE
echo Feche as duas janelas para encerrar.
pause
