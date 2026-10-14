"""diag_rtsp.py — Descobre a URL RTSP que REALMENTE entrega frame.

Testa combinacoes de (senha codificada x caminho do stream) numa camera e diz
qual funciona. Use quando o check_rtsp acusar "porta abre mas nao entrega frame".

Uso:  python diag_rtsp.py --ip 10.14.22.94
      python diag_rtsp.py --ip 10.14.22.94 --user admin --pass "Metaindustr!@"
"""
from __future__ import annotations
import argparse, os, sys, time
import cv2
from urllib.parse import quote

TIMEOUT_US = 6000000          # 6 s por tentativa (falha rapido)

def try_url(url, label):
    os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = (
        f"rtsp_transport;tcp|stimeout;{TIMEOUT_US}|timeout;{TIMEOUT_US}|max_delay;500000")
    t0 = time.time()
    cap = None
    try:
        cap = cv2.VideoCapture(url, cv2.CAP_FFMPEG)
        ok, frame = (False, None)
        if cap.isOpened():
            ok, frame = cap.read()
        dt = time.time() - t0
        if ok and frame is not None:
            h, w = frame.shape[:2]
            print(f"   [OK]    {label:38} {w}x{h}  ({dt:.1f}s)")
            return url
        print(f"   [falha] {label:38} sem frame ({dt:.1f}s)")
    except Exception as e:
        print(f"   [erro]  {label:38} {e}")
    finally:
        if cap is not None:
            cap.release()
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ip", default=None, help="IP de uma camera (ou use --ips para varias)")
    ap.add_argument("--user", default="admin")
    ap.add_argument("--password", "--pass", dest="password", default="Metaindustr!@")
    ap.add_argument("--port", default="554")
    ap.add_argument("--ips", default=None,
                    help="varios IPs separados por virgula: salva um print de cada camera")
    ap.add_argument("--config", nargs="?", const=True, default=None,
                    metavar="ARQUIVO",
                    help="testa TODAS as cameras do tortuga.config.json, com as URLs reais")
    ap.add_argument("--compare", action="store_true",
                    help="compara stream principal (subtype=0) x secundario (subtype=1)")
    a = ap.parse_args()
    if not a.ip and not a.ips and not a.config:
        ap.error("informe --ip <IP>, --ips <IP1,IP2,...> ou --config")

    pw_full = quote(a.password, safe="")        # tudo codificado: Metaindustr%21%40
    pw_at   = a.password.replace("@", "%40")    # so o @ codificado: Metaindustr!%40
    senhas = [("codificada  (%21%40)", pw_full),
              ("so @ codif. (!%40)  ", pw_at)]
    # Caminhos por fabricante. A metaindustria era Dahua; em local novo (auditorio
    # da FIAP, arena) a marca pode ser outra, por isso a lista e ampla.
    caminhos = [
        ("Dahua/Intelbras secundario", "/cam/realmonitor?channel=1&subtype=1"),
        ("Dahua/Intelbras principal", "/cam/realmonitor?channel=1&subtype=0"),
        ("Hikvision secundario", "/Streaming/Channels/102"),
        ("Hikvision principal", "/Streaming/Channels/101"),
        ("Axis", "/axis-media/media.amp"),
        ("generico /live", "/live"),
        ("generico /stream1", "/stream1"),
        ("generico /h264", "/h264"),
        ("generico /video1", "/video1"),
        ("generico /onvif1", "/onvif1"),
        ("generico /11", "/11"),
        ("raiz /", "/"),
    ]

    print("=" * 70)
    print(f"  DIAGNOSTICO RTSP — {a.ip}:{a.port}  usuario={a.user}")
    print("=" * 70)

    if a.config:
        import json, os, re
        _nome = "tortuga.config.json" if a.config is True else str(a.config)
        _arq = _nome if os.path.isabs(_nome) else os.path.join(
            os.path.dirname(os.path.abspath(__file__)), _nome)
        if not os.path.exists(_arq):
            sys.exit(f"  [ERRO] config nao encontrada: {_arq}")
        print(f"\n  Config: {os.path.basename(_arq)}")
        cfg = json.load(open(_arq, encoding="utf-8"))
        cams = cfg.get("cameras", [])
        print(f"\n  Testando as {len(cams)} cameras da config (URL real de cada uma):\n")
        ok_n = 0
        for cam in cams:
            st = cam.get("station_id", "?"); nome = cam.get("name", "")
            ip = re.search(r"@([\d.]+):", cam["source"])
            ip = ip.group(1) if ip else "?"
            r = try_url(cam["source"], f"{st} ({nome}) {ip}")
            if r: ok_n += 1
        print("\n" + "=" * 70)
        print(f"  {ok_n} de {len(cams)} cameras entregaram frame.")
        if ok_n < len(cams):
            print("  As que falharam: confira IP/senha na tabela, ou remova da config.")
        else:
            print("  Tudo pronto — pode subir o demo_limpo_metaindustria.bat")
        print("=" * 70 + "\n")
        return

    if a.ips:
        import os
        out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cams_preview")
        os.makedirs(out, exist_ok=True)
        print(f"\n  Salvando um print de cada camera em:\n  {out}\n")
        for ip in [x.strip() for x in a.ips.split(",") if x.strip()]:
            url = f"rtsp://{a.user}:{pw_full}@{ip}:{a.port}/cam/realmonitor?channel=1&subtype=1"
            os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = (
                f"rtsp_transport;tcp|stimeout;{TIMEOUT_US}|timeout;{TIMEOUT_US}")
            cap = cv2.VideoCapture(url, cv2.CAP_FFMPEG)
            ok, frame = (False, None)
            if cap.isOpened():
                ok, frame = cap.read()
            cap.release()
            if ok and frame is not None:
                f = os.path.join(out, f"{ip.replace('.','-')}.jpg")
                cv2.imwrite(f, frame)
                h, w = frame.shape[:2]
                print(f"   [OK]    {ip:15} {w}x{h}  -> {os.path.basename(f)}")
            else:
                print(f"   [falha] {ip:15} sem frame")
        print(f"\n  Abra a pasta cams_preview e veja qual imagem e a TENDA.")
        print(f"  Me mande o IP correspondente que eu coloco na config.\n")
        return

    if a.compare:
        print("\n  Comparando PRINCIPAL x SECUNDARIO (o detector reduz p/ 640px):\n")
        for nome, path in [("principal  (subtype=0)", "/cam/realmonitor?channel=1&subtype=0"),
                           ("secundario (subtype=1)", "/cam/realmonitor?channel=1&subtype=1")]:
            try_url(f"rtsp://{a.user}:{pw_full}@{a.ip}:{a.port}{path}", nome)
        print("\n" + "=" * 70)
        print("  Prefira o SECUNDARIO se ele entregar frame mais rapido:")
        print("  menos banda no Wi-Fi, menos erro de decodificacao, e a")
        print("  resolucao extra do principal seria descartada no resize.")
        print("=" * 70)
        return
    achou = None
    for nome_s, pw in senhas:
        print(f"\n  Senha {nome_s}:")
        for nome_c, path in caminhos:
            url = f"rtsp://{a.user}:{pw}@{a.ip}:{a.port}{path}"
            achou = try_url(url, nome_c)
            if achou:
                break
        if achou:
            break

    print("\n" + "=" * 70)
    if achou:
        print("  FUNCIONOU! Use esta URL:\n")
        print("   " + achou)
        print("\n  Me mande esta linha que eu atualizo a config das 3 cameras.")
    else:
        print("  NENHUMA combinacao entregou frame.")
        print("  Proximos passos: confirmar usuario/senha no painel da camera,")
        print("  e o caminho do stream (marca/modelo). Rode com --user/--password")
        print("  se as credenciais forem outras.")
    print("=" * 70)


if __name__ == "__main__":
    main()
