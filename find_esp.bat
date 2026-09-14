@echo off
REM Descobre o IP do cinto ESP32 na rede local (sem Arduino IDE).
set VP=%~dp0server\venv_win\Scripts\python.exe
if exist "%VP%" (
    "%VP%" "%~dp0server\find_esp.py"
) else (
    python "%~dp0server\find_esp.py"
)
echo.
pause
