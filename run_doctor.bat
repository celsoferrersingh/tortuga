@echo off
REM Tortuga - Diagnostico de ambiente (Fase 4). Usa o venv com CUDA.
call "C:\tortuga\server\venv_win\Scripts\activate.bat"
cd /d "C:\tortuga\server"
REM Sem --camera: o doctor le tortuga.config.json e testa a CAMERA REAL (RTSP).
REM Fora da rede da metaindustria ele avisa que o RTSP esta inacessivel (normal).
REM Para testar a webcam local (0), rode: python tortuga_doctor.py --camera 0
python tortuga_doctor.py
pause
