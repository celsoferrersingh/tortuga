@echo off
REM Tortuga - Remove as zonas de risco (a ZONA RESTRITA vermelha da demo).
REM Depois FECHE e REABRA o run_demo.bat para o app recarregar sem zonas.
cd /d "C:\tortuga\server"
"C:\tortuga\server\venv_win\Scripts\python.exe" clear_zones.py
pause
