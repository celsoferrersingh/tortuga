@echo off
REM ============================================================
REM  VALVULA DE ESCAPE: troca o Tortuga para o MODO LEVE.
REM  Use SO se algo travar ao vivo (GPU sobrecarregada).
REM  Modo leve = headless (sem janela): so Fase 1 (EPI) + Fase 3.
REM  A Fase 2 (pose) fica pausada. Para voltar: modo_completo.bat
REM ============================================================
set VP=%~dp0server\venv_win\Scripts\python.exe
if exist "%VP%" (
    "%VP%" "%~dp0server\set_mode.py" leve
) else (
    python "%~dp0server\set_mode.py" leve
)
echo.
echo   Agora feche as janelas de camera abertas e rode: run_metaindustria.bat
pause
