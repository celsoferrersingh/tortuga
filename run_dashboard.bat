@echo off
REM Tortuga Fase 3 - Dashboard (usa o venv com CUDA)
call "C:\tortuga\server\venv_win\Scripts\activate.bat"
cd /d "C:\tortuga\server"
echo   Instalando dependencias do dashboard (rapido se ja instalado)...
python -m pip install flask "qrcode[pil]" --quiet
echo.
python dashboard.py
pause
