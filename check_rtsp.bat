@echo off
REM Teste decisivo de RTSP: confirma se a maquina alcanca a camera de verdade.
set VP=%~dp0server\venv_win\Scripts\python.exe
if exist "%VP%" (
    "%VP%" "%~dp0server\check_rtsp.py"
) else (
    python "%~dp0server\check_rtsp.py"
)
echo.
pause
