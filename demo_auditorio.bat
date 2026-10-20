@echo off
REM ============================================================
REM  Tortuga - ENSAIO DA ARENA  ^|  Auditorio/Teatro da FIAP
REM
REM  Cameras: Intelbras VIPC-1230-B-G2 (OEM Dahua)
REM  Credencial do ensaio: alunos3EC / FiapSPI@2026
REM  Rede: 192.168.50.x    CAM01 confirmada: 192.168.50.121
REM
REM  IMPORTANTE: o IP das cameras MUDA entre visitas (a lousa
REM  dizia .108/.109 e a que estava no ar era a .121). Por isso
REM  o passo [2] VARRE a rede e monta a config sozinho - funciona
REM  igual se no sabado forem 5 cameras em enderecos novos.
REM
REM  Banco: data\demo.db (limpo). O banco real NAO e tocado.
REM  Config: server\tortuga.config.fiap.json
REM  A config da METAINDUSTRIA nao e tocada.
REM ============================================================
setlocal
set ROOT=%~dp0
set SERVER=%ROOT%server
set VENV=%SERVER%\venv_win\Scripts\activate.bat
set CFG=tortuga.config.fiap.json
set DB=data\demo.db
set REDE=192.168.50
set CUSER=alunos3EC
set CPASS=FiapSPI@2026
REM IP fixo para a placa CABEADA (as cameras). Mude o ultimo numero se der conflito.
set MEUIP=192.168.50.200
set MASCARA=255.255.255.0
set PLACA=Ethernet

IF NOT EXIST "%VENV%" (
    echo   [ERRO] Ambiente nao encontrado. Rode primeiro:  setup_gpu.bat
    pause & exit /b 1
)
call "%VENV%"
cd /d "%SERVER%"

cls
echo.
echo   ============================================================
echo      TORTUGA - ENSAIO DA ARENA  ^|  Auditorio da FIAP
echo      Intelbras VIPC-1230-B-G2  ^|  rede %REDE%.x
echo   ============================================================
echo.

REM ---- [1/6] rede das cameras: IP fixo na placa cabeada
REM  Por que fixar: a rede do auditorio e cabeada e sem DHCP util, e o Windows
REM  volta sozinho para "obter automaticamente" quando configurado pela tela de
REM  Rede. Pelo netsh fica gravado no adaptador e da para CONFERIR que aplicou.
echo   [1/6] Conferindo a rede das cameras...
ipconfig | findstr /C:"%REDE%." >nul 2>&1
if not errorlevel 1 goto REDE_OK

echo      [!] Nao vejo endereco %REDE%.x neste PC.
echo.
echo      Posso FIXAR o IP da placa cabeada agora:
echo          placa    : %PLACA%
echo          endereco : %MEUIP%   mascara %MASCARA%
echo      Precisa de janela como ADMINISTRADOR. No fim eu ofereco voltar p/ DHCP.
echo.
set "R1="
set /p R1=     Fixar o IP agora? [S/n]: 
if /i "%R1%"=="N" goto REDE_PULA

net session >nul 2>&1
if errorlevel 1 goto SEM_ADMIN
echo      Fixando...
netsh interface ip set address name="%PLACA%" static %MEUIP% %MASCARA%
timeout /t 3 /nobreak >nul
ipconfig | findstr /C:"%MEUIP%" >nul 2>&1
if errorlevel 1 goto FIXOU_NAO
echo      OK, %MEUIP% aplicado e CONFIRMADO no adaptador.
set IPFIXADO=1
goto REDE_OK

:FIXOU_NAO
echo      [!] O comando rodou mas o IP nao aparece. Veja o nome exato da placa:
echo            netsh interface show interface
echo          e corrija a variavel PLACA no topo deste .bat.
goto REDE_PULA

:SEM_ADMIN
echo      [!] Esta janela NAO e de administrador - o netsh nao vai conseguir.
echo          Feche, clique com o botao direito no .bat e escolha
echo          "Executar como administrador".

:REDE_PULA
echo.
set "R1B="
set /p R1B=     Continuar assim mesmo? [s/N]: 
if /i not "%R1B%"=="S" ( echo      Cancelado. & pause & exit /b 1 )

:REDE_OK

REM ---- [2/6] achar as cameras e montar a config  <<< o que resolve o IP que muda
echo.
echo   [2/6] Procurando as cameras e montando a config...
echo        (varre %REDE%.1-254 e testa qual URL entrega video)
echo.
python montar_config.py --rede %REDE% --user %CUSER% --pass "%CPASS%" --saida %CFG%
if errorlevel 1 goto SEM_CAM
goto COM_CAM
:SEM_CAM
echo.
echo      [!] Nenhuma camera respondeu na varredura.
echo          Plano B - usar o IP que o professor passou:
echo            python montar_config.py --ips %REDE%.121 --user %CUSER% --pass "%CPASS%" --saida %CFG%
echo          Se a porta abrir e nao vier frame, quase sempre e senha.
echo.
set "R2="
set /p R2=     Seguir assim mesmo (usa a config que ja esta gravada)? [s/N]:
if /i not "%R2%"=="S" ( echo      Cancelado. & pause & exit /b 1 )
:COM_CAM

REM ---- [3/6] confirmar que as cameras da config entregam frame
echo.
echo   [3/6] Confirmando o video de cada camera da config...
python diag_rtsp.py --config %CFG%
echo.
set "R3="
set /p R3=     Seguir para a demo? [S/n]:
if /i "%R3%"=="N" ( echo      Cancelado. & pause & exit /b 1 )

REM ---- [4/6] dashboard com banco limpo
echo.
echo   [4/6] Subindo o dashboard com dados LIMPOS (%DB%)...
start "Tortuga Dashboard (ENSAIO FIAP)" cmd /k python dashboard.py --db %DB% --seed
echo      aguardando o servidor repopular...
timeout /t 8 /nobreak >nul

REM ---- [5/6] cinto: descoberta automatica + vinculo as estacoes do palco
echo.
echo   [5/6] Procurando o cinto ESP32 e ligando-o as estacoes do palco...
python diag_cinto.py --db %DB% --auto --esperar 25 --registrar-config %CFG% --area "Palco FIAP"
if errorlevel 1 goto SEM_CINTO
goto CINTO_FIM
:SEM_CINTO
echo.
echo      [!] Cinto nao encontrado. O ensaio SEGUE normalmente -
echo          cameras, deteccao, dashboard e predicao funcionam sem ele.
echo          Conferir: hotspot 2,4 GHz ligado e cinto no power bank.
echo          Tentar de novo depois, sem parar nada:  diag_cinto.bat
timeout /t 4 /nobreak >nul
:CINTO_FIM

REM ---- [6/6] navegador + cameras
echo.
echo   [6/6] Abrindo o painel e o check-in, e subindo as cameras...
start "" http://localhost:5005
timeout /t 1 /nobreak >nul
start "" http://localhost:5005/checkin
echo.
echo   ============================================================
echo      TUDO PRONTO.  Feche esta janela ou Ctrl+C para encerrar.
echo.
echo      ANTES DE APRESENTAR:
echo.
echo       1. AREA UTIL - abra http://localhost:5005/config e trace o
echo          poligono sobre a demarcacao do chao. So o que estiver
echo          DENTRO e analisado; a plateia fica fora por construcao.
echo          No video, o que ficar de fora aparece ESCURECIDO.
echo          Dica: o que vale e o PE da pessoa, nao o centro - inclua
echo          a faixa do chao onde os atores vao pisar, com folga.
echo.
echo       2. CINTO - o OLED deve mostrar "CINTO = PONTO ACESSO".
echo          Conecte o Wi-Fi do NOTEBOOK na rede "Tortuga-Cinto"
echo          (senha tortuga2026). O cabo segue nas cameras.
echo          Para alternar o modo: segure BOOT e aperte RST.
echo.
echo       3. ATOR - nao deixe ele na frente da tela de projecao:
echo          o fundo claro vira contraluz e o EPI some. Posicione
echo          onde o refletor bate nele.
echo.
echo       4. MAQUINA - superficie rigida, base de refrigeracao ligada,
echo          e minimize as janelas que nao for mostrar (a pose pausa
echo          e libera GPU - foi assim que rodou a 30 FPS).
echo.
echo   ============================================================
echo.
python run_multicam.py --config %CFG%

REM ---- encerramento: devolve a placa ao DHCP, se fomos nos que fixamos ----
if not "%IPFIXADO%"=="1" goto FIM
echo.
set "RV="
set /p RV=  Devolver a placa "%PLACA%" para IP automatico (DHCP)? [S/n]: 
if /i "%RV%"=="N" goto FIM
netsh interface ip set address name="%PLACA%" dhcp
netsh interface ip set dns    name="%PLACA%" dhcp
echo   Placa devolvida ao DHCP.
:FIM

pause
endlocal
