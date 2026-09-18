@echo off
REM Tortuga - Descobre qual URL RTSP realmente entrega frame.
REM Use quando o check_rtsp disser "porta abre mas nao entrega frame".
setlocal
cd /d "%~dp0server"
call "%~dp0server\venv_win\Scripts\activate.bat"
set /p IPCAM=  IP da camera (Enter = 10.14.22.94): 
if "%IPCAM%"=="" set IPCAM=10.14.22.94
echo.
python diag_rtsp.py --ip %IPCAM%
echo.
pause
endlocal
