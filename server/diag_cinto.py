"""
diag_cinto.py — Diagnóstico ponta a ponta do cinto ESP32 · Projeto Tortuga

Responde "por que o cinto não apitou?" percorrendo a MESMA cadeia que o
dashboard usa, mostrando onde ela quebra:

    1. O cinto está registrado no banco? Com qual IP?
    2. Esse IP responde? (GET /  ->  "Tortuga ESP32 OK")
    3. Se não responde: VARRE a rede do hotspot e ACHA o ESP de verdade.
    4. Envia o alerta real (POST /status) e confirma que ele reagiu.
    5. Se o IP registrado estiver errado, corrige com --corrigir.

Por que isso existe: o push do dashboard é "à prova de falha" — ele engole
qualquer erro para nunca travar a detecção. Ótimo em produção, péssimo para
depurar: o sistema parece funcionando e o cinto fica mudo. Aqui o erro aparece.

Uso:
    python diag_cinto.py --db data/demo.db
    python diag_cinto.py --db data/demo.db --corrigir      # registra o IP achado
    python diag_cinto.py --db data/demo.db --rede 192.168.137   # varre outra faixa
"""
from __future__ import annotations
import argparse, json, os, socket, sys, time, urllib.error, urllib.request
from concurrent.futures import ThreadPoolExecutor

HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
from events_store import EventStore

ASSINATURA = "Tortuga ESP32"          # o que o GET / do firmware responde
# IP FIXO do cinto quando ele e o ponto de acesso (firmware em modo AP).
# E o caminho preferido desde o auditorio da FIAP: a rede de la e cabeada e sem
# internet, e o Windows se recusa a ligar o Ponto de acesso movel nessa condicao.
# Com o cinto sendo a rede, o endereco e sempre este — sem DHCP, sem descoberta.
IP_CINTO_AP = "192.168.4.1"
FAIXAS_PADRAO = ["192.168.4", "192.168.137"]   # AP do cinto; hotspot do Windows


# ── cores no terminal do Windows (sem dependencia externa) ──
def _c(txt, cor):
    cods = {"v": "92", "a": "93", "r": "91", "c": "96", "m": "90"}
    return f"\033[{cods.get(cor,'0')}m{txt}\033[0m"

OK, FALHA, AVISO = _c("  OK  ", "v"), _c(" FALHA", "r"), _c(" AVISO", "a")


def _ip_local():
    """IP do PC na rede do hotspot (o que o ESP enxerga)."""
    ips = []
    try:
        for inf in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ip = inf[4][0]
            if ip not in ips and not ip.startswith("127."):
                ips.append(ip)
    except Exception:
        pass
    return ips


def sonda(ip, timeout=0.6):
    """GET http://ip/ — devolve o texto se for um ESP Tortuga, senão None."""
    try:
        with urllib.request.urlopen(f"http://{ip}/", timeout=timeout) as r:
            txt = r.read(120).decode("utf-8", "ignore")
            return txt if ASSINATURA.lower() in txt.lower() else None
    except Exception:
        return None


def varre(faixa, timeout=0.6):
    """Procura o ESP em faixa.1 .. faixa.254 (em paralelo)."""
    achados = []
    alvos = [f"{faixa}.{i}" for i in range(1, 255)]
    with ThreadPoolExecutor(max_workers=120) as ex:
        for ip, txt in zip(alvos, ex.map(lambda i: sonda(i, timeout), alvos)):
            if txt:
                achados.append(ip)
    return achados


def alerta(ip, timeout=3.0):
    """Manda o MESMO POST que o dashboard manda numa violação real."""
    payload = {"status": "VIOLACAO", "severity": "critica",
               "message": "Teste Tortuga", "epi": "Capacete"}
    req = urllib.request.Request(f"http://{ip}/status",
                                 data=json.dumps(payload).encode("utf-8"),
                                 method="POST",
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.status, r.read(80).decode("utf-8", "ignore")


def faixas_para_varrer(store, extras=None):
    """Hotspot do Windows + faixas dos IPs ja registrados + faixas deste PC."""
    f = list(extras or []) or list(FAIXAS_PADRAO)
    for b in store.list_belts():
        u = b.get("esp32_url")
        if u:
            r = ".".join(u.split("://")[-1].rstrip("/").split(".")[:3])
            if r and r not in f:
                f.append(r)
    for ip in _ip_local():
        r = ".".join(ip.split(".")[:3])
        if r not in f:
            f.append(r)
    return f


def modo_auto(a):
    """Modo arena: achar o ESP, registrar e sair. Sem perguntas, sem painel do Windows."""
    print()
    print(_c("  Procurando o cinto ESP32 na rede...", "c"))
    store = EventStore(a.db)
    faixas = faixas_para_varrer(store, a.rede)

    # 0) atalho mais rapido: o cinto em MODO AP esta sempre em 192.168.4.1
    txt = sonda(IP_CINTO_AP, timeout=1.5)
    if txt:
        print(f"  {OK}  Cinto em MODO AP, no endereco fixo {_c('http://'+IP_CINTO_AP,'v')}")
        print(_c("      (o cinto e o ponto de acesso — sem DHCP, sem varredura)", "m"))
        _confirmar(store, IP_CINTO_AP, registrar=True,
                   config=a.registrar_config, area=a.area)
        return 0

    # 1) atalho: o IP ja registrado ainda responde? (caso comum, evita a varredura)
    for b in store.list_belts():
        u = b.get("esp32_url")
        if u:
            ip = u.split("://")[-1].rstrip("/")
            if sonda(ip, timeout=1.5):
                print(f"  {OK}  Cinto ja registrado e respondendo em {_c('http://'+ip,'v')}")
                _confirmar(store, ip, registrar=False,
                           config=a.registrar_config, area=a.area)
                return 0

    # 2) varredura, com reespera (o ESP leva alguns segundos para entrar no hotspot)
    limite = time.time() + max(0, a.esperar)
    tentativa = 0
    while True:
        tentativa += 1
        for f in faixas:
            achados = varre(f, a.timeout)
            if achados:
                ip = achados[0]
                print(f"  {OK}  ESP encontrado em {_c('http://'+ip,'v')}")
                _confirmar(store, ip, registrar=True,
                           config=a.registrar_config, area=a.area)
                return 0
        if time.time() >= limite:
            break
        resta = int(limite - time.time())
        print(_c(f"      ainda nao apareceu; tentando de novo ({resta}s restantes)...", "m"))
        time.sleep(3)

    print()
    print(f"  {FALHA}  Nao achei o cinto em: {', '.join(f+'.x' for f in faixas)}")
    print()
    print(_c("      Checagem rapida (10 segundos):", "a"))
    print("      1. O cinto esta no POWER BANK e saiu da tela 'TORTUGA'?")
    print("         Tem que mostrar 'CONFORME / Pode trabalhar'.")
    print()
    print(_c("      2. MODO AP (recomendado em rede cabeada sem internet):", "a"))
    print("         No boot o OLED deve mostrar 'CINTO = PONTO ACESSO'.")
    print("         Conecte o Wi-Fi do NOTEBOOK na rede 'Tortuga-Cinto'")
    print("         (senha tortuga2026). O cabo de rede segue nas cameras.")
    print("         Para alternar o modo: segure BOOT e aperte RST.")
    print()
    print("      3. MODO STA (so se houver hotspot): o Ponto de acesso movel")
    print("         esta LIGADO, em 2,4 GHz, e o cinto aparece em")
    print("         'Dispositivos conectados'?")
    print()
    print(_c("      A apresentacao RODA sem o cinto — so o alerta no corpo fica mudo.", "a"))
    return 1


def _criar_cintos_da_config(store, arquivo, url, area=None):
    """Cria um cinto por estacao da config e aponta todos para o ESP achado.

    Usado quando a demo roda com uma config propria (auditorio da FIAP, arena):
    as estacoes nao existem no banco demo, entao e preciso cria-las antes de o
    alerta ter para onde ir.
    """
    import json
    caminho = arquivo if os.path.isabs(arquivo) else os.path.join(HERE, arquivo)
    if not os.path.exists(caminho):
        print(f"  {AVISO}  Config nao encontrada: {caminho}")
        return 0
    cfg = json.load(open(caminho, encoding="utf-8"))
    store.upsert_worker("OP-DEMO", "Operador Demo", area or "Demonstracao", "A", 0,
                        required_epis=["Hardhat"], confidence=0.45)
    n = 0
    for cam in cfg.get("cameras", []):
        st = cam.get("station_id")
        if not st:
            continue
        dev = "CINTO-" + st
        store.upsert_belt(dev, "Cinto " + str(cam.get("name", st)), st)
        store.assign(dev, "OP-DEMO")
        store.set_belt_esp(dev, url)
        n += 1
    return n


def _confirmar(store, ip, registrar, config=None, area=None):
    """Registra o IP nos cintos e dispara o alerta de confirmacao."""
    url = "http://" + ip
    if registrar:
        for b in store.list_belts():
            store.set_belt_esp(b["device_id"], url)
        print(f"  {OK}  Registrado em {len(store.list_belts())} cinto(s) — nenhum IP digitado a mao")
    if config:
        n = _criar_cintos_da_config(store, config, url, area)
        if n:
            print(f"  {OK}  {n} estacao(oes) de {os.path.basename(config)} prontas para alertar")
    try:
        cod, _ = alerta(ip)
        print(f"  {OK}  Alerta de confirmacao enviado (HTTP {cod})")
        print(_c("      >>> O cinto deve ficar VERMELHO, apitar e vibrar por ~7 s.", "v"))
    except Exception as e:
        print(f"  {AVISO}  Achei o cinto, mas o alerta falhou: {type(e).__name__}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=os.path.join(HERE, "data", "tortuga.db"))
    ap.add_argument("--belt", default=None, help="device_id (padrão: todos os cintos com IP)")
    ap.add_argument("--rede", action="append", default=None,
                    help="faixa /24 a varrer, ex.: 192.168.137 (pode repetir)")
    ap.add_argument("--corrigir", action="store_true",
                    help="regrava no banco o IP realmente encontrado")
    ap.add_argument("--auto", action="store_true",
                    help="modo arena: acha o ESP, registra em todos os cintos e sai. "
                         "Codigo de saida 0 = cinto pronto, 1 = nao achou.")
    ap.add_argument("--registrar-config", dest="registrar_config", default=None,
                    help="apos achar o ESP, cria um cinto por estacao desta config "
                         "(ex.: tortuga.config.fiap.json)")
    ap.add_argument("--area", default=None, help="rotulo da area do operador demo")
    ap.add_argument("--esperar", type=int, default=0,
                    help="com --auto: reprocura por ate N segundos (o ESP leva alguns "
                         "segundos para entrar no hotspot recem-ligado)")
    ap.add_argument("--timeout", type=float, default=0.6)
    a = ap.parse_args()

    if a.auto:
        return modo_auto(a)

    print()
    print(_c("  ===== DIAGNOSTICO DO CINTO ESP32 =====", "c"))
    print(_c(f"  banco: {a.db}", "m"))
    print()

    store = EventStore(a.db)
    cintos = [b for b in store.list_belts() if (not a.belt or b["device_id"] == a.belt)]
    if not cintos:
        print(f"{FALHA}  Nenhum cinto no banco. Rode o seed ou o set_esp.py.")
        return 1

    # ── 1. o que esta registrado ──
    print(_c("  [1] Registro no banco", "c"))
    registrados = []
    for b in cintos:
        url = b.get("esp32_url")
        marca = OK if url else AVISO
        print(f"  {marca}  {b['device_id']:<18} estacao={str(b.get('station_id')):<12} "
              f"url={url or _c('(nao registrado)','a')}")
        if url:
            registrados.append((b["device_id"], url.split("://")[-1].rstrip("/")))
    if not registrados:
        print(f"\n{AVISO}  Nenhum cinto tem IP. O dashboard nao tem para onde mandar o alerta.")
    print()

    # ── 2. o IP registrado responde? ──
    print(_c("  [2] O IP registrado responde?", "c"))
    vivos, mortos = [], []
    for dev, ip in registrados:
        txt = sonda(ip, timeout=2.0)
        if txt:
            print(f"  {OK}  {dev:<18} http://{ip}  ->  {txt.strip()[:40]}")
            vivos.append((dev, ip))
        else:
            print(f"  {FALHA}  {dev:<18} http://{ip}  ->  sem resposta")
            mortos.append((dev, ip))
    print()

    # ── 3. varredura: onde o ESP esta DE VERDADE ──
    achados = []
    if mortos or not registrados:
        faixas = a.rede or []
        if not faixas:
            faixas = list(FAIXAS_PADRAO)
            for _, ip in registrados:                 # tambem a faixa do IP registrado
                f = ".".join(ip.split(".")[:3])
                if f not in faixas:
                    faixas.append(f)
            for ip in _ip_local():                    # e as faixas do proprio PC
                f = ".".join(ip.split(".")[:3])
                if f not in faixas:
                    faixas.append(f)
        print(_c("  [3] Procurando o ESP na rede", "c"))
        print(_c(f"      IPs deste PC: {', '.join(_ip_local()) or '-'}", "m"))
        for f in faixas:
            print(f"      varrendo {f}.1-254 ...", end="", flush=True)
            t0 = time.time()
            r = varre(f, a.timeout)
            print(f" {time.time()-t0:.1f}s  ->  {len(r)} ESP(s)")
            achados += r
        print()
        if achados:
            for ip in achados:
                print(f"  {OK}  ESP Tortuga encontrado em {_c('http://'+ip,'v')}")
        else:
            print(f"  {FALHA}  Nenhum ESP respondeu em nenhuma faixa.")
            print()
            print(_c("      O cinto nao esta alcancavel. As causas, em ordem:", "a"))
            print("      a) O ESP esta REINICIANDO em loop (tela 'TORTUGA' piscando).")
            print("         A tela 'TORTUGA' sozinha e o splash de boot: aparece ~2 s e")
            print("         deve virar 'CONFORME / Pode trabalhar'. Se fica piscando, ele")
            print("         reinicia antes de terminar o setup. Quase sempre e ENERGIA:")
            print("         o ESP32 puxa ~250-300 mA no pico do Wi-Fi e pilha fraca")
            print("         afunda a tensao (brownout). TESTE: ligue o cinto no cabo USB.")
            print("      b) O Ponto de acesso movel do Windows esta desligado, ou em 5 GHz")
            print("         (o ESP32 so enxerga 2,4 GHz).")
            print("      c) O ESP esta noutra rede (Wi-Fi da empresa, com isolamento de")
            print("         clientes). Segure BOOT + aperte RST e refaca o portal.")
        print()

    # ── 4. teste real: o cinto reage? ──
    alvos = vivos + [(f"(achado) {ip}", ip) for ip in achados if ip not in [v[1] for v in vivos]]
    if alvos:
        print(_c("  [4] Enviando o alerta REAL (POST /status)", "c"))
        for dev, ip in alvos:
            try:
                cod, corpo = alerta(ip)
                print(f"  {OK}  {dev:<18} {ip} -> HTTP {cod} {corpo.strip()[:30]}")
                print(_c("      >>> OLHE O CINTO AGORA: vermelho + apito + vibracao (~7 s).", "v"))
            except Exception as e:
                print(f"  {FALHA}  {dev:<18} {ip} -> {type(e).__name__}: {e}")
        print()

    # ── 5. corrigir o registro ──
    if achados:
        certo = achados[0]
        desatualizados = [(d, ip) for d, ip in registrados if ip != certo]
        if desatualizados or not registrados:
            print(_c("  [5] Registro desatualizado", "c"))
            for d, ip in desatualizados:
                print(f"  {AVISO}  {d}: banco diz {ip}, mas o ESP esta em {_c(certo,'v')}")
            if a.corrigir:
                for b in cintos:
                    store.set_belt_esp(b["device_id"], "http://" + certo)
                print(f"  {OK}  Regravado: todos os cintos agora apontam para http://{certo}")
            else:
                print()
                print(_c(f"      Para corrigir:  python diag_cinto.py --db {a.db} --corrigir", "a"))
            print()

    # ── resumo ──
    print(_c("  ===== RESUMO =====", "c"))
    if alvos:
        print(f"  {OK}  O caminho PC -> cinto FUNCIONA. Se mesmo assim o cinto nao apita")
        print("        durante a deteccao, confira se a camera esta na estacao do cinto")
        print("        (gui.py --station-id EST-PRE  <->  cinto da EST-PRE).")
    else:
        print(f"  {FALHA}  O PC nao alcanca o cinto. Resolva isso antes de testar o resto:")
        print("        o dashboard engole o erro do push para nunca travar a deteccao,")
        print("        por isso tudo parece certo na tela enquanto o cinto fica mudo.")
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
