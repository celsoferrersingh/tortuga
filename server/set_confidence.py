"""set_confidence.py — Ajusta a confianca minima do YOLO por ESTACAO (calibracao).

O limiar e propriedade do ARRANJO OPTICO (camera, iluminacao, distancia), nao do
operador: todos os operadores que passam pela mesma estacao sao medidos com o
MESMO limiar — condicao para a comparacao estatistica entre eles ser valida.

ATENCAO ao sentido do ajuste: o modelo e so-positivos (EPI nao detectado = ausente),
entao SUBIR a confianca tende a AUMENTAR as violacoes registradas, e BAIXAR tende a
mascarar violacoes reais. Mudar o limiar altera a taxa observada (lambda0).

O detector aplica a mudanca em ~4 s, sem reiniciar.

Uso:
    python set_confidence.py --value 0.45                 # todas as estacoes
    python set_confidence.py --value 0.55 --station EST-FRESA1
    python set_confidence.py --list
"""
from __future__ import annotations
import argparse, json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
from events_store import EventStore


def _stations_from_config():
    """Estacoes declaradas no tortuga.config.json (para bancos ainda sem eventos)."""
    p = os.path.join(HERE, "tortuga.config.json")
    if not os.path.exists(p):
        return []
    try:
        cfg = json.load(open(p, encoding="utf-8"))
        return [c["station_id"] for c in cfg.get("cameras", []) if c.get("station_id")]
    except Exception:
        return []


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--value", type=float, default=0.45, help="0.1-0.9 (ex.: 0.45 = 45%%)")
    ap.add_argument("--station", default=None, help="calibrar so esta estacao (padrao: todas)")
    ap.add_argument("--list", action="store_true", help="so mostra a calibracao atual")
    ap.add_argument("--db", default=os.path.join(HERE, "data", "tortuga.db"))
    a = ap.parse_args()
    s = EventStore(a.db)

    if a.list:
        rows = s.list_stations()
        print("\n  Calibracao por estacao:")
        for r in rows or []:
            c = r["confidence"]
            print("   %-14s %s" % (r["station_id"],
                                   ("%d%%" % round(c * 100)) if c is not None else "(padrao do detector)"))
        if not rows:
            print("   (nenhuma estacao registrada ainda)")
        s.close(); return

    v = min(max(a.value, 0.1), 0.9)
    if a.station:
        alvos = [a.station]
    else:
        alvos = sorted({r["station_id"] for r in s.list_stations()} | set(_stations_from_config()))
        if not alvos:
            alvos = ["EST-PRE"]        # estacao da demo com webcam
    for st in alvos:
        s.set_station_confidence(st, v)
    s.close()
    print("Confianca ajustada para %d%% em %d estacao(oes): %s"
          % (round(v * 100), len(alvos), ", ".join(alvos)))
    print("O detector aplica em ~4 s (nao precisa reiniciar).")
    print("Lembre: subir o limiar tende a AUMENTAR as violacoes registradas.")


if __name__ == "__main__":
    main()
