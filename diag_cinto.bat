@echo off
REM ============================================================
REM  Tortuga - DIAGNOSTICO DO CINTO ESP32
REM  Responde "por que o cinto nao apitou?" percorrendo a mesma
REM  cadeia do dashboard: registro -> IP responde -> varredura
REM  da rede -> alerta real -> correcao do registro.
REM  Nao altera a deteccao nem as cameras.
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
echo   Qual banco voce esta usando agora?
echo     [1] demo.db      (demo_limpo.bat - apresentacao)
echo     [2] tortuga.db   (run.bat / metaindustria)
set "ESC=1"
set /p ESC=  Escolha [1]:
if "%ESC%"=="2" (set DB=data\tortuga.db) else (set DB=data\demo.db)

echo.
python diag_cinto.py --db %DB%

echo.
echo   Se o diagnostico achou o ESP num IP diferente do registrado,
echo   rode a correcao abaixo e teste de novo.
echo.
set "FIX="
set /p FIX=  Corrigir o IP registrado agora? [s/N]:
if /i "%FIX%"=="s" (
    echo.
    python diag_cinto.py --db %DB% --corrigir
)

echo.
pause
endlocal
