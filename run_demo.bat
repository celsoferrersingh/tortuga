@echo off
REM ============================================================
REM  Tortuga - MODO CASA (demonstracao com a WEBCAM)
REM  Espelho do run_metaindustria.bat, mas apontando para a
REM  webcam (indice 0) em vez das cameras RTSP.
REM  Sobe o dashboard + a deteccao ao vivo (EPI + pose).
REM  Pre-requisito: rode setup_gpu.bat uma vez.
REM ============================================================
setlocal
set ROOT=%~dp0
set SERVER=%ROOT%server
set VENV=%SERVER%\venv_win\Scripts\activate.bat

IF NOT EXIST "%VENV%" (
    echo   [ERRO] Ambiente nao encontrado. Rode primeiro:  setup_gpu.bat
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

echo   [3/3] Abrindo a WEBCAM com deteccao de EPI + pose (Fase 1 + 2 + 3)...
echo   (feche a janela do video para encerrar a demo)
echo.
python gui.py --camera 0 --device auto --confidence 0.45 --ingest --station-id EST-PRE

pause
endlocal
