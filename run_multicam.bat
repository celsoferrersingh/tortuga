@echo off
REM Tortuga Fase 4 - Multiplos pontos de visao (varias cameras) usando o venv com CUDA
call "C:\tortuga\server\venv_win\Scripts\activate.bat"
cd /d "C:\tortuga\server"
REM Edite tortuga.config.json (copie de tortuga.config.example.json) com suas cameras
python run_multicam.py
pause
