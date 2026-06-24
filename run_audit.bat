@echo off
REM Tortuga (Passo 6) - Exporta a trilha de auditoria ASSINADA (CSV + HTML)
cd /d "C:\tortuga\server"
"C:\tortuga\server\venv_win\Scripts\python.exe" audit_export.py --out "C:\tortuga\tortuga_auditoria"
echo.
echo Abrindo o relatorio assinado no navegador...
start "" "C:\tortuga\tortuga_auditoria.html"
pause
