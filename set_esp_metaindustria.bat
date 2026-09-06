@echo off
REM ============================================================
REM  Tortuga - Registra o IP do ESP32 para TODAS as cameras da
REM  metaindustria (tortuga.config.json). O mesmo cinto passa a
REM  disparar em QUALQUER uma das 4 cameras.
REM  Pegue o IP no Serial Monitor do Arduino (linha IP: ...).
REM ============================================================
set /p ESPIP="Digite o IP do ESP (ex.: 192.168.0.42): "
"C:\tortuga\server\venv_win\Scripts\python.exe" "C:\tortuga\server\set_esp.py" --metaindustria --url http://%ESPIP%
pause
