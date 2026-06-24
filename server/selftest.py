"""
selftest.py — Auto-teste do backend Tortuga (Fases 3–4) · sem câmera, sem GPU

Sobe o app Flask em memória (banco temporário, dados sintéticos) e exercita
TODOS os endpoints novos, imprimindo PASS/FAIL por verificação. Use antes de
qualquer demo para garantir que o servidor está íntegro.

Uso:  python selftest.py
"""
from __future__ import annotations
import os, sys, tempfile, traceback

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

OK = "  \033[92mPASS\033[0m"
NO = "  \033[91mFALHA\033[0m"
_passed = 0; _failed = 0


def check(name, cond, extra=""):
    global _passed, _failed
    if cond:
        _passed += 1; print(f"{OK}  {name}  {extra}")
    else:
        _failed += 1; print(f"{NO}  {name}  {extra}")


def main():
    from dashboard import create_app
    from seed_events import seed
    db = os.path.join(tempfile.mkdtemp(), "selftest.db")
    app = create_app(db); seed(app._store, force=True)
    c = app.test_client()

    print("\n== Páginas ==")
    for url in ("/", "/config", "/checkin"):
        check(f"GET {url}", c.get(url).status_code == 200)

    print("\n== Risco preditivo (Poisson/TLC/teste) ==")
    r = c.get("/api/risk").get_json()
    check("/api/risk tem ranking", len(r["workers"]) == 10, f"λ0={r['lambda0']}")
    check("OP-007 é significativo", any(w["worker_id"] == "OP-007" and w["significant"] for w in r["workers"]))

    print("\n== Risco por área (IA + manual) ==")
    a = c.get("/api/area-risk").get_json()
    top = a["areas"][0]
    check("Prensa no topo, sugestão Alto", top["area"] == "Prensa" and top["suggested_level"] == "Alto", f"ratio={top['ratio']}")
    c.post("/api/area-risk", json={"area": "Solda", "level": "Alto"})
    solda = [x for x in c.get("/api/area-risk").get_json()["areas"] if x["area"] == "Solda"][0]
    check("override do gestor aplica", solda["manual_level"] == "Alto" and solda["effective_level"] == "Alto")
    c.post("/api/area-risk", json={"area": "Solda", "level": ""})
    solda = [x for x in c.get("/api/area-risk").get_json()["areas"] if x["area"] == "Solda"][0]
    check("limpar volta p/ sugestão IA", solda["manual_level"] is None)

    print("\n== Engajamento (gamificação + feedback) ==")
    e = c.get("/api/engagement").get_json()
    check("placar com 10 operadores", len(e["leaderboard"]) == 10)
    check("coaching personalizado", len(e["coaching"]) > 0, f"{e['coaching'][0]['focus']}")

    print("\n== Auditabilidade ==")
    v = c.get("/api/audit/verify").get_json()
    check("cadeia íntegra", v["ok"] and v["count"] > 0, f"{v['count']} registros")
    csv = c.get("/api/audit/export?worker_id=OP-007").get_data(as_text=True)
    check("export CSV assinado", "assinatura_hmac" in csv and "OP-007" in csv)

    print("\n== Cinto (pull) + ingestão ==")
    c.post("/api/assign", json={"device_id": "CINTO-PRE-01", "worker_id": "OP-007"})
    c.post("/api/ingest", json={"type": "EPI_AUSENTE", "epi": "Hardhat", "severity": "alta", "station_id": "EST-PRE"})
    bs = c.get("/api/belt-status?device_id=CINTO-PRE-01").get_json()
    check("belt-status acende em violação de campo", bs["status"] == "VIOLACAO", f"{bs.get('severity')}")

    print("\n== Fusão multi-câmera ==")
    # câmera A não vê capacete; câmera B vê -> união cobre -> sem alerta
    c.post("/api/observe", json={"station_id": "EST-PRE", "camera_id": "A", "present": ["Safety Vest"], "person": True})
    fjson = c.post("/api/observe", json={"station_id": "EST-PRE", "camera_id": "B",
                                         "present": ["Hardhat", "Safety Vest", "Safety Glasses", "Ear Protection"], "person": True}).get_json()
    check("oclusão resolvida (2 ângulos, sem faltas)", fjson["fused"]["cameras"] == 2 and fjson["fused"]["missing"] == [],
          f"present={fjson['fused']['present']}")
    fz = c.get("/api/fusion/EST-PRE").get_json()
    check("/api/fusion reflete estado", fz["cameras"] >= 1)

    print("\n" + "=" * 48)
    print(f"  RESULTADO: {_passed} PASS · {_failed} FALHA")
    print("=" * 48 + "\n")
    return 1 if _failed else 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        traceback.print_exc(); sys.exit(2)
