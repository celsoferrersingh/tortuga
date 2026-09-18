@echo off
REM Tortuga - Salva um print de cada camera encontrada na rede, para
REM identificar visualmente qual e a TENDA (ou qualquer outra).
setlocal
cd /d "%~dp0server"
call "%~dp0server\venv_win\Scripts\activate.bat"
set "IPS=10.14.22.30,10.14.22.31,10.14.22.32,10.14.22.97,10.14.22.98"
echo.
echo   IPs a testar: %IPS%
set /p CUSTOM=  Enter para usar estes, ou cole outra lista: 
if not "%CUSTOM%"=="" set IPS=%CUSTOM%
echo.
echo   Senha (Enter = a nova; digite SIDI2023 para a antiga):
set "PW=Metaindustr!@"
set /p PWIN=  Senha: 
if not "%PWIN%"=="" set "PW=%PWIN%"
echo.
python diag_rtsp.py --ips %IPS% --password "%PW%"
echo.
echo   Abrindo a pasta com os prints...
start "" "%~dp0server\cams_preview"
pause
endlocal
