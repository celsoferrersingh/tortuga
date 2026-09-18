"""find_cams.py — Varre a sub-rede procurando cameras IP (porta RTSP 554 aberta).

Util quando uma camera muda de IP: descobre quais enderecos respondem em 554.
Uso:  python find_cams.py                 (usa a sub-rede do proprio PC)
      python find_cams.py --net 10.14.22
"""
from __future__ import annotations
import argparse, socket
from concurrent.futures import ThreadPoolExecutor


def meu_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80)); return s.getsockname()[0]
    except Exception:
        return "127.0.0.1"
    finally:
        s.close()


def testa(ip, porta=554, timeout=0.6):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM); s.settimeout(timeout)
    try:
        return ip if s.connect_ex((ip, porta)) == 0 else None
    except Exception:
        return None
    finally:
        s.close()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--net", default=None, help="prefixo /24, ex.: 10.14.22")
    ap.add_argument("--port", type=int, default=554)
    a = ap.parse_args()
    net = a.net or ".".join(meu_ip().split(".")[:3])
    print(f"\n  Varrendo {net}.1-254 na porta {a.port} (RTSP)...\n")
    alvos = [f"{net}.{i}" for i in range(1, 255)]
    achados = []
    with ThreadPoolExecutor(max_workers=128) as ex:
        for r in ex.map(lambda ip: testa(ip, a.port), alvos):
            if r:
                achados.append(r); print(f"    [CAMERA?] {r}:{a.port} respondeu")
    print()
    if achados:
        print(f"  {len(achados)} endereco(s) com a porta {a.port} aberta:")
        for ip in achados:
            print(f"    {ip}")
        print("\n  Teste cada um com:  python diag_rtsp.py --ip <IP> --compare")
    else:
        print("  Nenhum dispositivo respondeu na porta 554 nesta sub-rede.")
    print()


if __name__ == "__main__":
    main()
