@echo off
REM ============================================================
REM  Tortuga - APRESENTACAO LIMPA na METAINDUSTRIA (cameras RTSP)
REM  Roda o dashboard + as cameras da config sobre um banco NOVO
REM  e realista (data\demo.db), repopulado do zero a cada execucao,
REM  e re-registra o cinto ESP real NESSE banco demo.
REM  NAO toca no banco real (data\tortuga.db).
REM
REM  Numeros esperados (baseline sintetico realista):
REM    - lambda0 do grupo ~0,4 ev/turno   (nao 9!)
REM    - Conformidade alta, phi saudavel
REM    - a violacao AO VIVO nas cameras cai em OP-DEMO e sobe o risco
REM  Pre-requisitos: setup_gpu.bat rodado uma vez + server\tortuga.config.json
REM  com o RTSP das cameras. Tenha o IP do ESP em maos (Serial Monitor).
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
    echo   Copie de tortuga.config.example.json e ajuste o RTSP das cameras.
    pause & exit /b 1
)

call "%VENV%"
cd /d "%SERVER%"

echo.
echo   [1/4] Subindo o dashboard com dados LIMPOS (data\demo.db)...
start "Tortuga Dashboard (DEMO LIMPA)" cmd /k python dashboard.py --db data\demo.db --seed
echo   Aguardando o dashboard subir e repopular...
timeout /t 8 /nobreak >nul

echo.
echo   [2/4] Registrando o cinto ESP real neste banco demo...
set "ESPIP="
set /p ESPIP=  Digite o IP do ESP (ex.: 10.14.22.10) e Enter [vazio = pular]:
IF NOT "%ESPIP%"=="" (
    python set_esp.py --metaindustria --url %ESPIP% --db data\demo.db
) ELSE (
    echo   [aviso] Sem IP: o cinto nao vai apitar e os eventos ao vivo cairao em OP-000.
)

echo.
echo   [3/4] Abrindo o painel e o check-in (QR) no navegador...
start "" http://localhost:5005
start "" http://localhost:5005/checkin

echo.
echo   [4/4] Iniciando as cameras RTSP (server\tortuga.config.json)...
echo   (Feche esta janela ou Ctrl+C para encerrar as cameras)
echo.
python run_multicam.py

pause
endlocal
