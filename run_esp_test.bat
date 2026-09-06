@echo off
REM Tortuga - Teste DIRETO do cinto ESP32 (isola o hardware). Nao precisa de camera.
set /p ESPIP="Digite o IP do ESP (veja no Serial Monitor, ex.: 192.168.0.42): "
"C:\tortuga\server\venv_win\Scripts\python.exe" "C:\tortuga\server\esp_test.py" --url http://%ESPIP%
pause
