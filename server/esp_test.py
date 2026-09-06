"""
esp_test.py — Teste DIRETO do cinto ESP32 (isola o hardware do resto) · Tortuga

Manda comandos HTTP direto pro ESP, sem passar pelo dashboard nem pela câmera.
Serve pra confirmar, em 20 segundos, que OLED + LED + buzzer + vibração reagem.

Uso:
    python esp_test.py --url http://192.168.0.42
    python esp_test.py --url http://192.168.0.42 --hold 4
"""
from __future__ import annotations
import argparse, json, time, urllib.request


def post(base, payload, timeout=2.0):
    url = base.rstrip("/") + "/status"
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST", headers={"Content-Type": "application/json"})
    t0 = time.time()
    try:
        r = urllib.request.urlopen(req, timeout=timeout).read()
        return True, time.time() - t0, r
    except Exception as e:
        return False, time.time() - t0, str(e)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", required=True, help="URL base do ESP, ex.: http://192.168.0.42")
    ap.add_argument("--hold", type=float, default=4.0, help="segundos em cada estado")
    a = ap.parse_args()
    u = a.url.strip().rstrip("/")
    while u.lower().startswith(("http://", "https://")):   # remove esquema duplicado
        u = u.split("://", 1)[1]
    b = "http://" + u

    print(f"  Testando cinto em {b}\n")
    seq = [
        ("VIOLACAO", "alta",    "TESTE - Capacete necessario", "Capacete", "LED vermelho fixo + bip espacado + vibracao curta"),
        ("VIOLACAO", "critica", "TESTE - Queda detectada",     None,       "LED vermelho rapido + bip agudo + vibracao forte"),
        ("CONFORME", "ok",      "Tudo certo",                  None,       "LED verde, sem alarme"),
    ]
    ok_any = False
    for status, sev, msg, epi, esperado in seq:
        ok, lat, resp = post(b, {"status": status, "severity": sev, "message": msg, "epi": epi})
        ok_any = ok_any or ok
        flag = "OK " if ok else "FALHOU"
        print(f"  [{flag}] {status}/{sev:8} {lat*1000:5.0f} ms  -> esperado no cinto: {esperado}")
        if not ok:
            print(f"          erro: {resp}")
        time.sleep(a.hold)

    print()
    if ok_any:
        print("  Cinto respondeu. Se a tela/LED/buzzer/vibração acompanharam, o hardware está OK.")
    else:
        print("  Nao consegui falar com o ESP. Cheque: IP certo, mesmo Wi-Fi, e o Serial Monitor mostrando o IP.")
        print("  Teste tambem no navegador do PC:  " + b + "  (deve responder 'Tortuga ESP32 OK. POST /status').")


if __name__ == "__main__":
    main()
