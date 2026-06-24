@echo off
REM Tortuga (Passo 5) - QR de check-in apontando para o IP do PC nesta rede.
REM Pre-requisito: o dashboard rodando (run_dashboard.bat) e o celular no mesmo Wi-Fi.
cd /d "C:\tortuga\server"
set PY=C:\tortuga\server\venv_win\Scripts\python.exe
REM garante a lib de QR (rapido se ja estiver instalada)
"%PY%" -m pip install "qrcode[pil]" -q
"%PY%" gen_qr.py
echo.
echo Abrindo a folha de QR codes (escaneie com o celular)...
start "" "C:\tortuga\server\qr_cintos\sheet.html"
pause
