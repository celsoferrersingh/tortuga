@echo off
setlocal
REM ============================================================
REM  Empacota o Tortuga para levar no pen drive (so o necessario).
REM  MANTEM: codigo, modelos (.pt), firmware, .bat, configs, docs.
REM  EXCLUI: venv_win, datasets, runs, _backups, Fotos spi, site, .git, __pycache__.
REM  Saida: tortuga_deploy.zip na sua Area de Trabalho.
REM ============================================================
set SRC=C:\tortuga
set STAGE=%TEMP%\tortuga_pack\tortuga
set OUT=%USERPROFILE%\Desktop\tortuga_deploy.zip

echo.
echo   ============================================
echo   Empacotando o Tortuga para o pen drive
echo   ============================================
echo.

if not exist "%SRC%\server" (
    echo   [ERRO] Nao encontrei C:\tortuga. Rode este .bat de dentro da pasta C:\tortuga.
    pause & exit /b 1
)

echo   [1/3] Copiando so os arquivos necessarios...
if exist "%TEMP%\tortuga_pack" rmdir /s /q "%TEMP%\tortuga_pack"
mkdir "%STAGE%"
robocopy "%SRC%" "%STAGE%" /E /XD "%SRC%\server\venv_win" "%SRC%\server\datasets" "%SRC%\server\runs" "%SRC%\server\runs_oculos" "%SRC%\_backups" "%SRC%\Fotos spi" "%SRC%\site" "%SRC%\.git" __pycache__ /XF *.pyc *.pyo >nul

echo   [2/3] Compactando (pode levar ~1 min)...
if exist "%OUT%" del "%OUT%"
powershell -NoProfile -Command "Compress-Archive -Path '%STAGE%' -DestinationPath '%OUT%' -CompressionLevel Optimal"

echo   [3/3] Limpando temporarios...
rmdir /s /q "%TEMP%\tortuga_pack"

echo.
if exist "%OUT%" (
    for %%A in ("%OUT%") do set SZ=%%~zA
    echo   [OK] Pacote criado:
    echo        %OUT%
    echo.
    echo   PROXIMOS PASSOS:
    echo    1. Copie o tortuga_deploy.zip para o pen drive.
    echo    2. Na maquina da metaindustria, extraia na RAIZ do C:  ^(vai criar C:\tortuga^).
    echo    3. Confira que a pasta ficou exatamente em  C:\tortuga
    echo    4. Rode  setup_gpu.bat   ^(precisa de Python, driver NVIDIA e internet^).
    echo    5. Rode  run_doctor.bat  para conferir GPU e camera.
) else (
    echo   [ERRO] Nao consegui criar o zip. Verifique espaco em disco e permissoes.
)
echo.
pause
endlocal
