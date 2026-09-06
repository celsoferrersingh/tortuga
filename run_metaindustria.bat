@echo off
REM ============================================================
REM  Tortuga — Lancador unico da METAINDUSTRIA
REM  Sobe o dashboard (Fase 3) e depois as cameras da config.
REM  Pre-requisitos: rode setup_gpu.bat uma vez e edite
REM  server\tortuga.config.json com o RTSP da camera IP.
REM ============================================================
setlocal
set ROOT=%~dp0
set SERVER=%ROOT%server
set VENV=%SERVER%\venv_win\Scripts\activate.bat

IF NOT EXIST "%VENV%" (
    echo   [ERRO] Ambiente nao encontrado. Rode primeiro:  setup_gpu.bat
    pause & exit /b 1
)
IF NOT EXIST "%SERVER%\tortuga.config.json" (
    echo   [ATENCAO] server\tortuga.config.json nao existe.
    echo   Copie de tortuga.config.example.json e ajuste o RTSP da camera.
    pause & exit /b 1
)

call "%VENV%"
cd /d "%SERVER%"

echo.
echo   [1/3] Iniciando o dashboard em uma janela separada...
start "Tortuga Dashboard" cmd /k python dashboard.py
echo   Aguardando o dashboard subir...
timeout /t 6 /nobreak >nul

echo   [2/3] Abrindo o painel e o check-in (QR) no navegador...
start "" http://localhost:5005
start "" http://localhost:5005/checkin

echo   [3/3] Iniciando as cameras (server\tortuga.config.json)...
echo   (Feche esta janela ou Ctrl+C para encerrar as cameras)
echo.
python run_multicam.py

pause
endlocal
