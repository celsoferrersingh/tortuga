"""
audit_export.py — Exporta a trilha de auditoria assinada (Fase 4) · Tortuga

Gera um CSV e um relatório HTML (imprimível como PDF), ambos com o selo de
integridade da cadeia + assinatura HMAC. Filtros opcionais por operador,
estação(câmera), turno e área.

Uso:
    python audit_export.py
    python audit_export.py --worker OP-007 --out rel_op007
    python audit_export.py --station EST-PRE --turno A
Segredo da assinatura: variável de ambiente TORTUGA_AUDIT_SECRET.
"""
from __future__ import annotations
import argparse, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from events_store import EventStore
import audit


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=os.path.join(HERE, "data", "tortuga.db"))
    ap.add_argument("--worker", default=None)
    ap.add_argument("--station", default=None)
    ap.add_argument("--turno", default=None)
    ap.add_argument("--area", default=None)
    ap.add_argument("--out", default="tortuga_auditoria")
    a = ap.parse_args()

    store = EventStore(a.db)
    rows = store.audit_rows()
    store.close()

    filt = {k: v for k, v in (("worker_id", a.worker), ("station_id", a.station),
                              ("turno", a.turno), ("area", a.area)) if v} or None
    v = audit.verify(rows)
    csv_path = a.out + ".csv"; html_path = a.out + ".html"
    with open(csv_path, "w", encoding="utf-8", newline="") as f:
        f.write(audit.export_csv(rows, filt))
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(audit.export_html(rows, filt))

    print("  Trilha de auditoria:")
    print("   integridade : %s" % ("ÍNTEGRA" if v["ok"] else "VIOLADA na seq %s" % v["broken_at"]))
    print("   registros   : %d" % v["count"])
    print("   hash-cabeça : %s" % v["head"])
    print("   assinatura  : %s" % audit.sign(v["head"]))
    print("   CSV  -> %s" % csv_path)
    print("   HTML -> %s  (imprima como PDF para arquivar)" % html_path)


if __name__ == "__main__":
    main()
