@echo off
REM Tortuga - Auto-teste do backend (Fases 3-4). Nao precisa de camera nem GPU.
call "C:\tortuga\server\venv_win\Scripts\activate.bat"
cd /d "C:\tortuga\server"
python selftest.py
pause
