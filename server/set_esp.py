"""
set_esp.py — Registra o IP/URL do ESP32 de um cinto (modelo PUSH) · Tortuga

O servidor manda o alerta pro IP do cinto na rede. Descubra o IP no Serial
Monitor do Arduino (linha "IP do ESP32: ...") e registre aqui.

Uso:
    python set_esp.py --url http://192.168.0.42            # cinto da demo (EST-PRE)
    python set_esp.py --metaindustria --url http://IP       # todas as cameras da config
    python set_esp.py --list                                 # so mostra os cintos e seus IPs
"""
from __future__ import annotations
import argparse, os, sys
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
from events_store import EventStore


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=os.path.join(HERE, "data", "tortuga.db"))
    ap.add_argument("--belt", default="CINTO-PRE-01", help="device_id do cinto (padrão: o da estação da demo)")
    ap.add_argument("--url", default=None, help="URL base do ESP, ex.: http://192.168.0.42")
    ap.add_argument("--metaindustria", action="store_true",
                    help="Registra o ESP para TODAS as cameras do tortuga.config.json (um cinto que dispara em qualquer camera)")
    ap.add_argument("--config", default=None,
                    help="Igual ao --metaindustria, mas usando OUTRA config "
                         "(ex.: tortuga.config.fiap.json para o auditorio da FIAP)")
    ap.add_argument("--area", default=None,
                    help="Rotulo da area do operador demo (padrao: deduzido da config)")
    ap.add_argument("--list", action="store_true")
    a = ap.parse_args()
    store = EventStore(a.db)

    u = None
    if a.url:
        u = a.url.strip().rstrip("/")
        while u.lower().startswith(("http://", "https://")):
            u = u.split("://", 1)[1]
        u = "http://" + u

    if a.metaindustria or a.config:
        arquivo = a.config or "tortuga.config.json"
        if not os.path.isabs(arquivo):
            arquivo = os.path.join(HERE, arquivo)
        if not os.path.exists(arquivo):
            print(f"  [ERRO] config nao encontrada: {arquivo}")
        elif not u:
            print("  [ERRO] informe o IP: python set_esp.py --url http://<IP-DO-ESP> "
                  + (f"--config {a.config}" if a.config else "--metaindustria"))
        else:
            import json
            cfg = json.load(open(arquivo, encoding="utf-8"))
            area = a.area or ("Metaindustria" if arquivo.endswith("tortuga.config.json")
                              else "Demonstracao")
            # perfil generico com EPI obrigatorio, pra o alerta ter o que cobrar
            store.upsert_worker("OP-DEMO", "Operador Demo", area, "A", 0,
                                required_epis=["Hardhat"], confidence=0.45)
            n = 0
            for cam in cfg.get("cameras", []):
                st = cam.get("station_id")
                if not st:
                    continue
                dev = "CINTO-" + st
                store.upsert_belt(dev, "Cinto " + str(cam.get("name", st)), st)
                store.assign(dev, "OP-DEMO")
                store.set_belt_esp(dev, u)
                n += 1
            print(f"  OK: ESP {u} registrado para {n} camera(s) de {os.path.basename(arquivo)} "
                  f"(dispara em qualquer uma).")
    elif u:
        store.set_belt_esp(a.belt, u)
        print(f"  OK: {a.belt} -> {u}")

    print("\n  Cintos cadastrados:")
    for b in store.list_belts():
        print("   %-14s estação %-8s ESP=%s" % (b["device_id"], b.get("station_id") or "-", b.get("esp32_url") or "(não definido)"))
    store.close()
    if not a.url and not a.list and not a.metaindustria:
        print("\n  Dica: python set_esp.py --url http://<IP-DO-ESP>")


if __name__ == "__main__":
    main()
