"""
gen_qr.py — Gera os QR codes dos cintos (check-in por turno) · Fase 3
Cada QR aponta para  <BASE>/checkin?belt=<DEVICE_ID>. O operador escaneia com
o celular no início do turno, confirma quem é, e o servidor amarra operador↔cinto.

USO:
  pip install "qrcode[pil]"
  python gen_qr.py --base http://192.168.0.50:5005      # IP do servidor na rede
Saída: pasta qr_cintos/ com um PNG por cinto + folha imprimível (sheet.html).
"""
from __future__ import annotations
import argparse, os, socket
import qrcode

# device_id -> rótulo legível (espelha BELTS do seed_events)
BELTS = [
    ("CINTO-PRE-01", "Prensa 1"),
    ("CINTO-PIN-01", "Pintura 1"),
    ("CINTO-SOL-01", "Solda 1"),
    ("CINTO-EXP-01", "Expedição 1"),
]
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "qr_cintos")


def lan_ip() -> str:
    """IP da interface de saída (a real da rede), ignorando adaptadores virtuais."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))      # não envia nada; só escolhe a rota
        return s.getsockname()[0]
    except Exception:
        return "127.0.0.1"
    finally:
        s.close()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default=None,
                    help="URL base do dashboard (se omitido, detecta o IP da rede automaticamente)")
    ap.add_argument("--port", type=int, default=5005)
    a = ap.parse_args()
    base = a.base or f"http://{lan_ip()}:{a.port}"
    os.makedirs(OUT, exist_ok=True)
    print("=" * 56)
    print("  Abra esta URL no CELULAR (mesmo Wi-Fi do PC):")
    print("   ", base + "/checkin")
    print("  Ou escaneie um QR da folha que vai abrir.")
    print("=" * 56)

    cards = []
    for dev, label in BELTS:
        url = f"{base}/checkin?belt={dev}"
        img = qrcode.make(url)
        path = os.path.join(OUT, f"{dev}.png")
        img.save(path)
        cards.append((dev, label, url, f"{dev}.png"))
        print("QR:", path, "->", url)

    # folha imprimível
    style = ("body{font-family:Arial;background:#fff;color:#111;margin:24px}"
             ".g{display:grid;grid-template-columns:repeat(2,1fr);gap:18px}"
             ".c{border:2px solid #111;border-radius:12px;padding:16px;text-align:center;break-inside:avoid}"
             ".c img{width:230px;height:230px}.c b{display:block;font-size:20px;margin-top:8px}"
             ".c span{color:#555;font-size:13px;word-break:break-all}"
             "h1{color:#FF8A00}.t{color:#888;font-size:12px}")
    cells = "".join(
        f'<div class="c"><img src="{png}"><b>{dev}</b><div>{label}</div>'
        f'<span class="t">{url}</span></div>' for dev, label, url, png in cards)
    html = (f"<!doctype html><meta charset=utf-8><title>QR dos cintos Tortuga</title>"
            f"<style>{style}</style><h1>TORTUGA — QR dos cintos</h1>"
            f"<p class=t>Cole cada QR no cinto correspondente. O operador escaneia no início do turno.</p>"
            f'<div class="g">{cells}</div>')
    with open(os.path.join(OUT, "sheet.html"), "w", encoding="utf-8") as f:
        f.write(html)
    print("\nFolha imprimível:", os.path.join(OUT, "sheet.html"))


if __name__ == "__main__":
    main()
