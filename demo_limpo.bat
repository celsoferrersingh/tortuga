@echo off
REM ============================================================
REM  Tortuga - MODO APRESENTACAO LIMPA (NEXT)
REM  Roda o dashboard + webcam sobre um banco NOVO e realista
REM  (data\demo.db), repopulado do zero a cada execucao.
REM  NAO toca no banco real da metaindustria (data\tortuga.db).
REM
REM  Numeros esperados (dados sinteticos realistas):
REM    - lambda0 do grupo ~0,4 ev/turno   (nao 9!)
REM    - Conformidade alta, phi saudavel
REM    - OP-007 (Prensa) e OP-009 (Pintura) como maior risco
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
echo   [1/4] Subindo o dashboard com dados LIMPOS (data\demo.db)...
start "Tortuga Dashboard (DEMO LIMPA)" cmd /k python dashboard.py --db data\demo.db --seed
echo   Aguardando o dashboard subir e repopular...
timeout /t 7 /nobreak >nul

echo.
echo   [2/4] Registrando o cinto ESP32 neste banco demo...
set "ESPIP="
set /p ESPIP=  Digite o IP do ESP (ex.: 192.168.137.2) e Enter [vazio = pular]: 
IF NOT "%ESPIP%"=="" (
    python set_esp.py --belt CINTO-PRE-01 --url %ESPIP% --db data\demo.db
) ELSE (
    echo   [aviso] Sem IP: o cinto nao vai apitar nesta demo.
)

echo.
echo   [3/4] Abrindo o painel e o check-in (QR) no navegador...
start "" http://localhost:5005
start "" http://localhost:5005/checkin

echo   [4/4] Abrindo a WEBCAM com deteccao (EPI + pose) - evento ao vivo em EST-PRE (OP-007)...
echo   (feche a janela do video para encerrar a demo)
echo.
python gui.py --camera 0 --device auto --confidence 0.45 --ingest --station-id EST-PRE

pause
endlocal
