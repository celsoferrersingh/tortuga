@echo off
REM ============================================================
REM  Tortuga - ARENA NEXT 2026  (um clique, zero digitacao)
REM
REM  A UNICA coisa que voce faz antes: ligar o Ponto de acesso
REM  movel do Windows (2,4 GHz) e por o cinto no POWER BANK.
REM
REM  Daqui pra frente o .bat faz tudo:
REM    1. confere se o hotspot esta ligado
REM    2. sobe o dashboard com dados LIMPOS (data\demo.db)
REM    3. ACHA o IP do cinto na rede sozinho e registra
REM       (sem abrir painel de rede, sem copiar e colar IP)
REM    4. abre o painel e o check-in no navegador
REM    5. sobe a camera com deteccao
REM
REM  Nunca toca no banco real da metaindustria (data\tortuga.db).
REM ============================================================
setlocal
set ROOT=%~dp0
set SERVER=%ROOT%server
set VENV=%SERVER%\venv_win\Scripts\activate.bat
set DB=data\demo.db

IF NOT EXIST "%VENV%" (
    echo   [ERRO] Ambiente nao encontrado. Rode primeiro:  setup_gpu.bat
    pause & exit /b 1
)
call "%VENV%"
cd /d "%SERVER%"

cls
echo.
echo   ============================================================
echo      TORTUGA - ARENA NEXT 2026
echo   ============================================================
echo.

REM ---- [1/5] hotspot ligado? (o Mobile Hotspot do Windows e sempre 192.168.137.1)
echo   [1/5] Conferindo o Ponto de acesso movel...
call :VER_HOTSPOT
if not errorlevel 1 goto HOTSPOT_OK

echo.
echo      [!] O Ponto de acesso movel parece DESLIGADO.
echo          Ligue em: Configuracoes ^> Rede ^> Ponto de acesso movel
echo          Banda: 2,4 GHz   ^(o ESP32 nao enxerga 5 GHz^)
echo.
echo          Sem ele o sistema roda igual - so o cinto fica mudo.
echo.
set "SEGUIR="
set /p SEGUIR=     Ligou? Enter para conferir de novo ^(ou N para seguir sem cinto^):
if /i "%SEGUIR%"=="N" goto HOTSPOT_PULADO
call :VER_HOTSPOT
if not errorlevel 1 goto HOTSPOT_OK
echo      [!] Ainda nao vejo o hotspot - seguindo assim mesmo.
goto HOTSPOT_PULADO

:HOTSPOT_OK
echo      OK, hotspot no ar ^(192.168.137.1^).
goto FIM_HOTSPOT

:HOTSPOT_PULADO
echo      Seguindo sem o cinto.

:FIM_HOTSPOT

REM ---- [2/5] dashboard com banco limpo
echo.
echo   [2/5] Subindo o dashboard com dados LIMPOS...
start "Tortuga Dashboard (ARENA NEXT)" cmd /k python dashboard.py --db %DB% --seed
echo      aguardando o servidor repopular...
timeout /t 8 /nobreak >nul

REM ---- [3/5] descoberta automatica do cinto  <<< o que economiza seu tempo
echo.
echo   [3/5] Procurando o cinto ESP32 na rede ^(automatico^)...
python diag_cinto.py --db %DB% --auto --esperar 25
if errorlevel 1 (
    echo.
    echo      [!] Cinto nao encontrado. A apresentacao SEGUE normalmente -
    echo          a deteccao, o dashboard e a predicao funcionam sem ele.
    echo          Para tentar de novo depois, sem parar nada:  diag_cinto.bat
    echo.
    timeout /t 4 /nobreak >nul
)

REM ---- [4/5] navegador
echo.
echo   [4/5] Abrindo o painel do gestor e o check-in...
start "" http://localhost:5005
timeout /t 1 /nobreak >nul
start "" http://localhost:5005/checkin

REM ---- [5/5] camera
echo.
echo   [5/5] Subindo a camera com deteccao ^(EPI + pose^) na EST-PRE...
echo.
echo   ============================================================
echo      TUDO PRONTO. Feche a janela do video para encerrar.
echo   ============================================================
echo.
python gui.py --camera 0 --device auto --confidence 0.45 --ingest --station-id EST-PRE

pause
endlocal
exit /b 0

REM ── sub-rotina: hotspot do Windows no ar? (errorlevel 0 = sim) ──
:VER_HOTSPOT
powershell -NoProfile -Command "if(Get-NetIPAddress -IPAddress 192.168.137.1 -ErrorAction SilentlyContinue){exit 0}else{exit 1}" >nul 2>&1
exit /b %errorlevel%
