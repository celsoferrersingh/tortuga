"""set_confidence.py — Ajusta a confiança mínima do YOLO nos perfis.
O app aplica a confiança do perfil ativo ao iniciar (run_demo). Padrão: 0.45."""
from __future__ import annotations
import argparse, os, sys
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
from events_store import EventStore


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--value", type=float, default=0.45, help="0.0–1.0 (ex.: 0.45 = 45%)")
    ap.add_argument("--db", default=os.path.join(HERE, "data", "tortuga.db"))
    a = ap.parse_args()
    v = min(max(a.value, 0.1), 0.9)
    s = EventStore(a.db)
    n = 0
    for w in s.get_roster():
        s.update_profile(w["worker_id"], confidence=v); n += 1
    s.close()
    print("Confianca ajustada para %d%% em %d perfis." % (round(v * 100), n))
    print("Feche e reabra o run_demo.bat para aplicar.")


if __name__ == "__main__":
    main()
