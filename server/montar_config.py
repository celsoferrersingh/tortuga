"""
montar_config.py — Acha as cameras vivas na rede e MONTA a config sozinho.

Por que existe: o endereco das cameras muda entre visitas. Na metaindustria um
IP deixou de existir entre uma visita e outra; no auditorio da FIAP a lousa dizia
.108/.109 e a camera no ar era a .121. Em vez de editar JSON na hora, este script
varre a faixa, testa qual URL entrega frame de verdade e grava a config pronta.

Testa, para cada IP vivo, o stream SECUNDARIO e o PRINCIPAL. Prefere o secundario
quando os dois funcionam: a inferencia reduz para 640 px, entao 1080p so gasta
banda — licao aprendida na metaindustria, onde o principal era instavel no Wi-Fi.

Uso:
    python montar_config.py --rede 192.168.50 --user alunos3EC --pass "FiapSPI@2026"
    python montar_config.py --rede 192.168.50 --user alunos3EC --pass "X" --saida tortuga.config.fiap.json
    python montar_config.py --ips 192.168.50.121,192.168.50.122 --user alunos3EC --pass "X"
"""
from __future__ import annotations
import argparse, json, os, socket, sys, time
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import quote

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

# caminhos por fabricante — Intelbras e Dahua compartilham o mesmo (OEM)
CAMINHOS = [
    ("secundario", "/cam/realmonitor?channel=1&subtype=1"),   # preferido
    ("principal",  "/cam/realmonitor?channel=1&subtype=0"),
    ("hik secund.", "/Streaming/Channels/102"),
    ("hik princ.",  "/Streaming/Channels/101"),
]


def _c(t, cor):
    return f"\033[{ {'v':'92','a':'93','r':'91','c':'96','m':'90'}.get(cor,'0') }m{t}\033[0m"

OK, FALHA, AVISO = _c("  OK  ", "v"), _c(" FALHA", "r"), _c(" AVISO", "a")


def porta_aberta(ip, porta=554, timeout=0.5):
    try:
        with socket.create_connection((ip, porta), timeout=timeout):
            return True
    except Exception:
        return False


def entrega_frame(url, timeout_s=7):
    """Abre a URL e tenta ler um quadro. Devolve (ok, largura, altura)."""
    import cv2
    os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = (
        f"rtsp_transport;tcp|stimeout;{timeout_s*1000000}|timeout;{timeout_s*1000000}|max_delay;500000")
    cap = None
    try:
        cap = cv2.VideoCapture(url, cv2.CAP_FFMPEG)
        if not cap.isOpened():
            return False, 0, 0
        ok, frame = cap.read()
        if ok and frame is not None:
            h, w = frame.shape[:2]
            return True, w, h
        return False, 0, 0
    except Exception:
        return False, 0, 0
    finally:
        if cap is not None:
            cap.release()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rede", default=None, help="prefixo /24, ex.: 192.168.50")
    ap.add_argument("--ips", default=None, help="lista de IPs separados por virgula")
    ap.add_argument("--user", default="admin")
    ap.add_argument("--password", "--pass", dest="password", required=True)
    ap.add_argument("--porta", default="554")
    ap.add_argument("--saida", default="tortuga.config.fiap.json")
    ap.add_argument("--prefixo-estacao", dest="prefixo", default="EST-PALCO")
    ap.add_argument("--nome", default="Palco")
    ap.add_argument("--principal", action="store_true",
                    help="prefere o stream PRINCIPAL (padrao: prefere o secundario)")
    a = ap.parse_args()

    if not a.rede and not a.ips:
        ap.error("informe --rede 192.168.50  ou  --ips 192.168.50.121,...")

    pw = quote(a.password, safe="")
    print()
    print(_c("  ===== MONTAGEM AUTOMATICA DA CONFIG =====", "c"))

    # ── 1. quem responde na porta RTSP ──
    if a.ips:
        alvos = [s.strip() for s in a.ips.split(",") if s.strip()]
        print(f"  [1] Testando {len(alvos)} IP(s) informado(s)...")
        vivos = [ip for ip in alvos if porta_aberta(ip, int(a.porta))]
    else:
        alvos = [f"{a.rede}.{i}" for i in range(1, 255)]
        print(f"  [1] Varrendo {a.rede}.1-254 na porta {a.porta}...", end="", flush=True)
        t0 = time.time()
        with ThreadPoolExecutor(max_workers=120) as ex:
            res = list(ex.map(lambda ip: porta_aberta(ip, int(a.porta)), alvos))
        vivos = [ip for ip, v in zip(alvos, res) if v]
        print(f" {time.time()-t0:.1f}s")

    if not vivos:
        print(f"\n{FALHA}  Nenhum dispositivo respondeu na porta {a.porta}.")
        print("        Confira se o PC esta na rede certa (ipconfig).")
        return 1
    print(f"  {OK}  {len(vivos)} dispositivo(s) com a porta {a.porta} aberta: {', '.join(vivos)}")

    # ── 2. qual URL entrega frame ──
    print(f"\n  [2] Testando qual URL entrega video (usuario={a.user})...")
    ordem = list(CAMINHOS)
    if a.principal:                       # inverte a preferencia se pedido
        ordem[0], ordem[1] = ordem[1], ordem[0]

    achadas = []
    for ip in vivos:
        print(f"\n      {ip}")
        escolhida = None
        for rotulo, path in ordem:
            url = f"rtsp://{a.user}:{pw}@{ip}:{a.porta}{path}"
            ok, w, h = entrega_frame(url)
            if ok:
                print(f"        {OK}  {rotulo:<12} {w}x{h}")
                if escolhida is None:
                    escolhida = (url, rotulo, w, h)
            else:
                print(f"        {FALHA}  {rotulo:<12} sem frame")
        if escolhida:
            achadas.append((ip, *escolhida))
        else:
            print(f"        {AVISO}  nenhum caminho funcionou — confira usuario/senha")

    if not achadas:
        print(f"\n{FALHA}  Nenhuma camera entregou video.")
        print("        Se a porta abre mas nao vem frame, quase sempre e senha errada.")
        return 1

    # ── 3. gravar a config ──
    caminho = a.saida if os.path.isabs(a.saida) else os.path.join(HERE, a.saida)
    base = {}
    if os.path.exists(caminho):
        try:
            base = json.load(open(caminho, encoding="utf-8"))
        except Exception:
            base = {}
    base.setdefault("dashboard", "http://localhost:5005")
    base.setdefault("device", "cuda")
    base.setdefault("model", "models/best.pt")
    base.setdefault("defaults", {"det_size": 640, "confidence": 0.45, "preprocess": True,
                                 "ingest": True, "pose": True, "headless": False})
    base["_gerado_em"] = time.strftime("%d/%m/%Y %H:%M")
    base["_gerado_por"] = "montar_config.py (descoberta automatica)"
    base["cameras"] = []
    for i, (ip, url, rotulo, w, h) in enumerate(achadas, 1):
        base["cameras"].append({
            "station_id": f"{a.prefixo}{i}",
            "name": f"{a.nome} {i}",
            "_ip": ip, "_stream": rotulo, "_resolucao": f"{w}x{h}",
            "source": url,
            "headless": False,
        })
    json.dump(base, open(caminho, "w", encoding="utf-8"), ensure_ascii=False, indent=2)

    print()
    print(_c("  ===== RESULTADO =====", "c"))
    print(f"  {OK}  {len(achadas)} camera(s) gravada(s) em {os.path.basename(caminho)}:")
    for cam in base["cameras"]:
        print(f"        {cam['station_id']:<12} {cam['_ip']:<16} {cam['_stream']:<12} {cam['_resolucao']}")
    print()
    print(_c("      Senha nao aparece aqui, mas ESTA na config (como sempre esteve).", "m"))
    print()
    print("  Proximo passo:  demo_auditorio.bat")
    return 0


if __name__ == "__main__":
    sys.exit(main())
