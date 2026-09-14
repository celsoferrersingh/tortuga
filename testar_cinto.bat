@echo off
REM ============================================================
REM  Tortuga - TESTE RAPIDO DO CINTO ESP32
REM  Manda um alerta direto pro cinto (mesmo caminho que o
REM  dashboard usa) pra confirmar que ele reage: vermelho +
REM  buzzer + vibracao. Volta ao verde sozinho em ~7 s.
REM  Nao depende das cameras nem do dashboard.
REM ============================================================
setlocal
echo.
set "ESPIP="
set /p ESPIP=  Digite o IP do ESP (ex.: 192.168.137.2):
if "%ESPIP%"=="" ( echo   Sem IP informado. & pause & exit /b 1 )

echo.
echo   Enviando alerta de teste para http://%ESPIP%/status ...
powershell -NoProfile -Command "try{ Invoke-RestMethod -Uri 'http://%ESPIP%/status' -Method Post -ContentType 'application/json' -Body '{\"status\":\"VIOLACAO\",\"severity\":\"critica\",\"message\":\"Teste Tortuga\",\"epi\":\"Capacete\"}' -TimeoutSec 3 | Out-Null; Write-Host '   OK! O cinto deve estar VERMELHO, apitando e vibrando (volta ao verde em ~7s).' -ForegroundColor Green }catch{ Write-Host '   [FALHA] Nao alcancou o ESP. Confira o IP e se ele esta no hotspot do PC (GALAXYBOOK4).' -ForegroundColor Red }"
echo.
pause
endlocal
