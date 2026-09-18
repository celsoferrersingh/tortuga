@echo off
REM Tortuga - Procura cameras IP na rede (porta RTSP 554 aberta).
setlocal
cd /d "%~dp0server"
call "%~dp0server\venv_win\Scripts\activate.bat"
python find_cams.py
pause
endlocal
