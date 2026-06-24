@echo off
REM Tortuga - Diagnostico de ambiente (Fase 4). Usa o venv com CUDA.
call "C:\tortuga\server\venv_win\Scripts\activate.bat"
cd /d "C:\tortuga\server"
python tortuga_doctor.py --camera 0
pause
