@echo off
REM ============================================================
REM  Tortuga - ENSAIO DA ARENA no AUDITORIO/TEATRO da FIAP
REM
REM  Mesma estrutura do demo_limpo_metaindustria.bat, com as
REM  2 cameras do palco (lousa: 192.168.50.108 e .109) e com
REM  a descoberta automatica do cinto que criamos depois.
REM
REM  Config: server\tortuga.config.fiap.json
REM  A config da METAINDUSTRIA (tortuga.config.json) NAO e tocada.
REM  Banco: data\demo.db (limpo). O banco real NAO e tocado.
REM
REM  Antes de rodar:
REM    1. PC conectado na rede do auditorio (192.168.50.x)
REM    2. Ponto de acesso movel ligado em 2,4 GHz (para o cinto)
REM    3. Cinto no POWER BANK, mostrando CONFORME
REM ============================================================
setlocal
set ROOT=%~dp0
set SERVER=%ROOT%server
set VENV=%SERVER%\venv_win\Scripts\activate.bat
set CFG=tortuga.config.fiap.json
set DB=data\demo.db

IF NOT EXIST "%VENV%" (
    echo   [ERRO] Ambiente nao encontrado. Rode primeiro:  setup_gpu.bat
    pause & exit /b 1
)
IF NOT EXIST "%SERVER%\%CFG%" (
    echo   [ERRO] server\%CFG% nao encontrada.
    pause & exit /b 1
)
call "%VENV%"
cd /d "%SERVER%"

cls
echo.
echo   ============================================================
echo      TORTUGA - ENSAIO DA ARENA  ^|  Auditorio da FIAP
echo      2 cameras no palco: 192.168.50.108 e 192.168.50.109
echo   ============================================================
echo.

REM ---- [1/6] a rede do auditorio esta alcancavel?
echo   [1/6] Conferindo a rede do auditorio...
ping -n 1 -w 1200 192.168.50.108 >nul 2>&1
if errorlevel 1 goto REDE_RUIM
echo      OK, 192.168.50.108 responde.
goto REDE_OK
:REDE_RUIM
echo      [!] 192.168.50.108 nao respondeu ao ping.
echo          Confira se o PC esta na rede do auditorio (192.168.50.x).
echo          Obs.: algumas cameras bloqueiam ping e mesmo assim entregam video.
echo.
set "SEGUIR="
set /p SEGUIR=     Continuar mesmo assim? [S/n]:
if /i "%SEGUIR%"=="N" ( echo      Cancelado. & pause & exit /b 1 )
:REDE_OK

REM ---- [2/6] credenciais das cameras (mudam de local para local)
echo.
echo   [2/6] Credenciais das cameras do palco
echo        (Enter em branco mantem o que ja esta gravado na config)
set "CUSER="
set "CPASS="
set /p CUSER=     Usuario [admin]:
set /p CPASS=     Senha:
if "%CUSER%"=="" set CUSER=admin
if not "%CPASS%"=="" (
    python set_cams.py --config %CFG% --user %CUSER% --pass "%CPASS%"
) else (
    echo      [aviso] Senha nao informada - usando a que ja esta na config.
)

REM ---- [3/6] as cameras entregam frame?
echo.
echo   [3/6] Testando se as cameras entregam video...
python diag_rtsp.py --config %CFG%
echo.
echo        Se alguma falhou, abra OUTRA janela e descubra o caminho certo:
echo          python diag_rtsp.py --ip 192.168.50.108 --user %CUSER% --pass "SENHA"
echo        Depois grave o caminho que funcionou:
echo          python set_cams.py --config %CFG% --user %CUSER% --pass "SENHA" --path "/CAMINHO"
echo.
set "SEGUIR2="
set /p SEGUIR2=     Seguir para a demo? [S/n]:
if /i "%SEGUIR2%"=="N" ( echo      Cancelado. & pause & exit /b 1 )

REM ---- [4/6] dashboard com banco limpo
echo.
echo   [4/6] Subindo o dashboard com dados LIMPOS (%DB%)...
start "Tortuga Dashboard (ENSAIO FIAP)" cmd /k python dashboard.py --db %DB% --seed
echo      aguardando o servidor repopular...
timeout /t 8 /nobreak >nul

REM ---- [5/6] cinto: descoberta automatica (sem digitar IP)
echo.
echo   [5/6] Procurando o cinto ESP32 e ligando-o as estacoes do palco...
python diag_cinto.py --db %DB% --auto --esperar 25 --registrar-config %CFG% --area "Palco FIAP"
if errorlevel 1 goto SEM_CINTO
goto CINTO_FIM
:SEM_CINTO
echo.
echo      [!] Cinto nao encontrado. O ensaio SEGUE normalmente -
echo          cameras, deteccao, dashboard e predicao funcionam sem ele.
echo          Para tentar de novo depois, sem parar nada:  diag_cinto.bat
timeout /t 4 /nobreak >nul
:CINTO_FIM

REM ---- [6/6] navegador + cameras
echo.
echo   [6/6] Abrindo o painel e o check-in, e subindo as cameras...
start "" http://localhost:5005
timeout /t 1 /nobreak >nul
start "" http://localhost:5005/checkin
echo.
echo   ============================================================
echo      TUDO PRONTO.  Feche esta janela ou Ctrl+C para encerrar.
echo
echo      Lembretes do palco:
echo        - minimize as janelas de video que nao for mostrar
echo          ^(a pose pausa e libera GPU - foi assim que rodou a 30 FPS^)
echo        - desenhe a zona de risco em /config sobre a imagem real
echo        - notebook em superficie rigida, base de refrigeracao ligada
echo   ============================================================
echo.
python run_multicam.py --config %CFG%

pause
endlocal
