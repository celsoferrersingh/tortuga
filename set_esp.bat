@echo off
REM Tortuga - Registra o IP do ESP32 do cinto (para o dashboard mandar o alerta).
set /p ESPIP="Digite o IP do ESP (Serial Monitor, ex.: 192.168.0.42): "
"C:\tortuga\server\venv_win\Scripts\python.exe" "C:\tortuga\server\set_esp.py" --url http://%ESPIP%
pause
