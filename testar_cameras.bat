@echo off
REM Tortuga - Testa TODAS as cameras da config, com as URLs reais de cada uma.
setlocal
cd /d "%~dp0server"
call "%~dp0server\venv_win\Scripts\activate.bat"
python diag_rtsp.py --config
pause
endlocal
