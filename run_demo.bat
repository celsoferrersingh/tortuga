@echo off
REM Tortuga Fase 3 - Camera + deteccao ao vivo com ingestao (usa o venv com CUDA)
call "C:\tortuga\server\venv_win\Scripts\activate.bat"
cd /d "C:\tortuga\server"
REM Troque --det-size 960 por 640 se travar; EST-PRE = estacao da demo
python gui.py --ingest --station-id EST-PRE --det-size 960
pause
