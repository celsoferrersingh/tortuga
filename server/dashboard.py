"""
dashboard.py — Dashboard SSMA preditivo + gestão (Fase 3) · Projeto Tortuga
Flask: motor preditivo (Poisson/TLC/teste de hipóteses), perfis de operador
com EPIs por perfil, atribuição de cinto via QR e zonas de risco.

USO:  pip install flask qrcode[pil]
      python dashboard.py            # popula sintético se vazio e sobe
      http://localhost:5005          (gestor)   ·   /config  ·  /checkin
"""
from __future__ import annotations
import argparse, os
from flask import Flask, jsonify, render_template, request, Response
from events_store import EventStore
from risk_engine import rank_workers, rank_areas
import severity as sev_policy
import engagement, audit
from fusion import FusionCoordinator

BASE = os.path.dirname(os.path.abspath(__file__))


def create_app(db_path="data/tortuga.db"):
    store = EventStore(db_path)
    fusion_coord = FusionCoordinator()
    app = Flask(__name__, template_folder=os.path.join(BASE, "templates"),
                static_folder=os.path.join(BASE, "static"))

    @app.route("/")
    def home(): return render_template("dashboard.html")

    @app.route("/config")
    def config(): return render_template("config.html")

    @app.route("/checkin")
    def checkin(): return render_template("checkin.html")

    # ── analítico ──
    @app.route("/api/risk")
    def api_risk():
        h = int(request.args.get("horizon", 1))
        lam0, ranking = rank_workers(store.worker_summaries(), horizon=h)
        return jsonify({"lambda0": round(lam0, 3), "horizon": h,
                        "workers": [r.to_dict() for r in ranking],
                        "n_significant": sum(1 for r in ranking if r.significant)})

    @app.route("/api/stats")
    def api_stats():
        by = store.count_by_severity()
        return jsonify({"total": store.total_events(), "by_severity": by,
                        "by_type": store.count_by_type(), "conformity": store.conformity_rate(),
                        "criticas": by.get("critica", 0),
                        "severity_meta": {k: {"label": v["label"], "color": v["color"]}
                                          for k, v in sev_policy.POLICY.items()}})

    @app.route("/api/timeseries")
    def api_ts(): return jsonify(store.daily_counts(int(request.args.get("days", 14))))

    @app.route("/api/events")
    def api_events(): return jsonify(store.recent_events(int(request.args.get("limit", 30))))

    # ── perfis ──
    @app.route("/api/profiles", methods=["GET", "POST"])
    def api_profiles():
        if request.method == "POST":
            d = request.get_json(force=True)
            store.upsert_worker(d["worker_id"], d.get("name", d["worker_id"]),
                                d.get("area", ""), d.get("turno", "A"), int(d.get("shifts", 0)),
                                required_epis=d.get("required_epis"), confidence=float(d.get("confidence", 0.4)))
            return jsonify({"ok": True})
        return jsonify(store.get_roster())

    @app.route("/api/profiles/<worker_id>", methods=["PUT"])
    def api_profile_update(worker_id):
        store.update_profile(worker_id, **request.get_json(force=True))
        return jsonify({"ok": True})

    # ── cintos + QR ──
    @app.route("/api/belts")
    def api_belts(): return jsonify(store.list_belts())

    @app.route("/api/assign", methods=["POST"])
    def api_assign():
        d = request.get_json(force=True)
        belt = store.assign(d["device_id"], d["worker_id"])
        if belt is None:
            return jsonify({"ok": False, "error": "cinto não encontrado"}), 404
        prof = store.get_profile(d["worker_id"])
        return jsonify({"ok": True, "belt": belt, "profile": prof})

    # ── zonas ──
    @app.route("/api/zones", methods=["GET", "POST"])
    def api_zones():
        if request.method == "POST":
            d = request.get_json(force=True)
            zid = store.add_zone(d["name"], d.get("level", "alta"), d.get("points", []),
                                 station_id=d.get("station_id"), required_epis=d.get("required_epis"))
            return jsonify({"ok": True, "id": zid})
        return jsonify(store.list_zones(request.args.get("station_id")))

    @app.route("/api/zones/<int:zid>", methods=["PUT", "DELETE"])
    def api_zone_edit(zid):
        if request.method == "DELETE":
            store.delete_zone(zid); return jsonify({"ok": True})
        store.update_zone(zid, **request.get_json(force=True)); return jsonify({"ok": True})

    # ── risco por ÁREA: sugestão da IA + classificação manual do gestor ──
    @app.route("/api/area-risk", methods=["GET", "POST"])
    def api_area_risk():
        if request.method == "POST":
            d = request.get_json(force=True)
            store.set_area_level(d["area"], d.get("level") or None)
            return jsonify({"ok": True})
        lam0, areas = rank_areas(store.worker_summaries())
        manual = store.get_area_levels()
        out = []
        for a in areas:
            row = a.to_dict()
            m = manual.get(a.area)
            row["manual_level"] = m                       # None = usando a sugestão
            row["effective_level"] = m or a.suggested_level
            out.append(row)
        return jsonify({"lambda0": round(lam0, 3), "areas": out})

    # ── engajamento: gamificação positiva + feedback educativo ──
    @app.route("/api/engagement")
    def api_engagement():
        data = engagement.build(store.worker_summaries(),
                                store.last_event_per_worker(),
                                store.worker_type_breakdown())
        data["team"] = {"streak_critical_days": store.days_since_last_critical(),
                        "conformity": store.conformity_rate()}
        return jsonify(data)

    # ── auditabilidade: verificação de integridade + exportação assinada ──
    @app.route("/api/audit/verify")
    def api_audit_verify():
        return jsonify(audit.verify(store.audit_rows()))

    @app.route("/api/audit/export")
    def api_audit_export():
        filt = {k: request.args.get(k) for k in ("worker_id", "station_id", "turno", "area")
                if request.args.get(k)}
        fmt = request.args.get("format", "csv")
        rows = store.audit_rows()
        if fmt == "html":
            return Response(audit.export_html(rows, filt or None), mimetype="text/html")
        return Response(audit.export_csv(rows, filt or None), mimetype="text/csv",
                        headers={"Content-Disposition": "attachment; filename=tortuga_auditoria.csv"})

    # ── ingestão de evento REAL (do sistema de visão) ──
    @app.route("/api/ingest", methods=["POST"])
    def api_ingest():
        d = request.get_json(force=True)
        wid = d.get("worker_id")
        if not wid and d.get("station_id"):
            wid = store.active_worker(station_id=d["station_id"]) or "OP-000"
        wid = wid or "OP-000"
        prof = store.get_profile(wid) or {}
        sev = d.get("severity") or sev_policy.classify(d["type"], altura=d.get("altura", False))
        store.add_event(worker_id=wid, type=d["type"], severity=sev, epi=d.get("epi"),
                        area=d.get("area") or prof.get("area"),
                        turno=d.get("turno") or prof.get("turno"), station_id=d.get("station_id"))
        # estado pendente do cinto (modelo PULL): alerta de campo fica disponível
        # para o ESP consultar via /api/belt-status (expira sozinho por TTL).
        if sev_policy.is_field(sev) and d.get("station_id"):
            dev = store.belt_for_station(d["station_id"])
            if dev:
                store.set_belt_status(dev, severity=sev,
                                      message=d.get("message") or d["type"], epi=d.get("epi"))
        return jsonify({"ok": True, "worker_id": wid, "severity": sev})

    # ── status pendente do cinto (modelo PULL ultra-baixo-consumo do ESP32) ──
    @app.route("/api/belt-status")
    def api_belt_status():
        dev = request.args.get("device_id")
        if not dev:
            return jsonify({"status": "CONFORME"})
        return jsonify(store.get_belt_status(dev))

    # ── fusão multi-câmera: cada câmera REPORTA o que vê; o servidor decide ──
    @app.route("/api/observe", methods=["POST"])
    def api_observe():
        d = request.get_json(force=True)
        station = d.get("station_id"); camera = d.get("camera_id") or station
        fusion_coord.observe(station, camera, d.get("present", []), d.get("person", False))
        wid = store.active_worker(station_id=station) or "OP-000"
        prof = store.get_profile(wid) or {}
        required = prof.get("required_epis", [])
        fused = fusion_coord.fused(station, required)
        created = []
        for epi in fused["missing"]:
            if fusion_coord.alertable(station, epi):
                s = sev_policy.classify("EPI_AUSENTE")
                store.add_event(worker_id=wid, type="EPI_AUSENTE", severity=s, epi=epi,
                                area=prof.get("area"), turno=prof.get("turno"), station_id=station)
                dev = store.belt_for_station(station)
                if dev and sev_policy.is_field(s):
                    store.set_belt_status(dev, severity=s, message="EPI_AUSENTE", epi=epi)
                created.append(epi)
        return jsonify({"ok": True, "worker_id": wid, "fused": fused, "events_created": created})

    @app.route("/api/fusion/<station_id>")
    def api_fusion(station_id):
        wid = store.active_worker(station_id=station_id) or "OP-000"
        prof = store.get_profile(wid) or {}
        return jsonify(fusion_coord.fused(station_id, prof.get("required_epis", [])))

    app._store = store
    return app


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=os.path.join(BASE, "data", "tortuga.db"))
    ap.add_argument("--port", type=int, default=5005)
    ap.add_argument("--seed", action="store_true")
    a = ap.parse_args()
    app = create_app(a.db); store = app._store
    if store.total_events() == 0 or a.seed:
        from seed_events import seed; seed(store, force=a.seed)
    print("\n  Dashboard:  http://localhost:%d   |  /config  |  /checkin\n" % a.port)
    app.run(host="0.0.0.0", port=a.port, debug=False)


if __name__ == "__main__":
    main()
