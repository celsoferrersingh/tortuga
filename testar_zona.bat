@echo off
REM ============================================================
REM  PRE-VOO da ZONA DE EXCLUSAO (com a webcam)
REM  Teste rapido em casa, sem precisar das cameras da industria.
REM  Abre a webcam com uma zona "IGNORADA" no canto direito:
REM   - se o app abrir sem erro, o codigo esta ok;
REM   - nada deve ser detectado DENTRO da caixa cinza "IGNORADA"
REM     (ponha a mao/cabeca la dentro e confira que nao acusa).
REM ============================================================
set VENV=%~dp0server\venv_win\Scripts\activate.bat
IF NOT EXIST "%VENV%" (
    echo   [ERRO] Ambiente nao encontrado. Rode primeiro: setup_gpu.bat
    pause & exit /b 1
)
call "%VENV%"
cd /d "%~dp0server"
echo.
echo   Abrindo a webcam com a zona de exclusao no canto direito...
echo   (feche a janela do video para encerrar)
echo.
python gui.py --camera 0 --confidence 0.45 --ignore "[[0.6,0.4,1.0,1.0]]"
pause
