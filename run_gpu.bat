@echo off
call "C:\tortuga\server\venv_win\Scripts\activate.bat"
cd "C:\tortuga\server"
python gui.py --confidence 0.4
pause
