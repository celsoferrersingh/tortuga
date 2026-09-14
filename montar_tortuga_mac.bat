@echo off
setlocal
REM ============================================================
REM  Monta C:\tortuga_mac com o codigo + os scripts macOS.
REM  Roda no Windows. Depois copie C:\tortuga_mac para o Mac.
REM ============================================================
set SRC=%~dp0
set DST=C:\tortuga_mac

echo.
echo   Montando %DST%  (codigo + scripts macOS)...
if not exist "%DST%" mkdir "%DST%"

echo   [1/3] Copiando server (sem venvs/datasets)...
robocopy "%SRC%server" "%DST%\server" /E /XD "%SRC%server\venv_win" "%SRC%server\venv_m4" "%SRC%server\datasets" "%SRC%server\runs" "%SRC%server\runs_oculos" __pycache__ /XF *.pyc >nul

echo   [2/3] Copiando firmware...
robocopy "%SRC%firmware" "%DST%\firmware" /E /XD __pycache__ /XF *.pyc >nul

echo   [3/3] Copiando os scripts macOS...
robocopy "%SRC%_mac" "%DST%" /E >nul

echo.
echo   ============================================
echo   Pronto! C:\tortuga_mac montada.
echo   1. Copie a pasta C:\tortuga_mac inteira para o Mac.
echo   2. No Mac, siga o LEIA-ME_MAC.md (chmod +x, setup_mac.command).
echo   ============================================
echo.
pause
endlocal
