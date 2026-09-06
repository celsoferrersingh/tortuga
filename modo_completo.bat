@echo off
REM ============================================================
REM  Volta o Tortuga para o MODO COMPLETO (PADRAO).
REM  Janela + Fase 1 (EPI) + Fase 2 (pose) + Fase 3 em todas as cameras.
REM  Use para reverter depois de ter usado o modo_leve.bat.
REM ============================================================
set VP=%~dp0server\venv_win\Scripts\python.exe
if exist "%VP%" (
    "%VP%" "%~dp0server\set_mode.py" completo
) else (
    python "%~dp0server\set_mode.py" completo
)
echo.
echo   Agora rode: run_metaindustria.bat
pause
