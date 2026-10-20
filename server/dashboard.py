"""
dashboard.py — Dashboard SSMA preditivo + gestão (Fase 3) · Projeto Tortuga
Flask: motor preditivo (Poisson/TLC/teste de hipóteses), perfis de operador
com EPIs por perfil, atribuição de cinto via QR e zonas de risco.

USO:  pip install flask qrcode[pil]
      python dashboard.py            # popula sintético se vazio e sobe
      http://localhost:5005          (gestor)   ·   /config  ·  /checkin
"""
from __future__ import annotations
import argparse, base64, json, os, threading, time, urllib.request
from datetime import datetime
from flask import Flask, jsonify, render_template, request, Response
from events_store import EventStore
from risk_engine import rank_workers, rank_areas, dispersion_report
import severity as sev_policy
import engagement, audit
from fusion import FusionCoordinator

BASE = os.path.dirname(os.path.abspath(__file__))


# Contador do push: a entrega ao cinto NUNCA pode derrubar a detecção, então a
# falha é engolida — mas engolir em silêncio fazia o sistema parecer saudável com
# o cinto mudo. Agora o erro aparece no console (1x por minuto, sem poluir) e em
# /api/belt-health, que diz na hora se o último alerta chegou ao cinto.
_PUSH = {"ok": 0, "fail": 0, "last_url": None, "last_error": None,
         "last_ok_at": None, "last_fail_at": None, "_logged_at": 0.0}


def _push_esp(esp_url, payload):
    """Push HTTP não-bloqueante pro cinto ESP32 (POST {esp_url}/status). À prova de falha."""
    if not esp_url:
        _PUSH["fail"] += 1
        _PUSH["last_error"] = "cinto sem IP registrado (use set_esp.py ou diag_cinto.bat)"
        _PUSH["last_fail_at"] = datetime.now().isoformat(timespec="seconds")
        return
    def _go():
        _PUSH["last_url"] = esp_url
        try:
            data = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(esp_url.rstrip("/") + "/status", data=data,
                                         method="POST", headers={"Content-Type": "application/json"})
            urllib.request.urlopen(req, timeout=1.0).read()
            _PUSH["ok"] += 1
            _PUSH["last_error"] = None
            _PUSH["last_ok_at"] = datetime.now().isoformat(timespec="seconds")
        except Exception as e:
            _PUSH["fail"] += 1
            _PUSH["last_error"] = f"{type(e).__name__}: {e}"
            _PUSH["last_fail_at"] = datetime.now().isoformat(timespec="seconds")
            agora = time.time()
            if agora - _PUSH["_logged_at"] > 60:      # no máximo 1 aviso por minuto
                _PUSH["_logged_at"] = agora
                print(f"  [CINTO] alerta NAO entregue em {esp_url} -> {_PUSH['last_error']}"
                      f"  ({_PUSH['fail']} falhas)  rode: diag_cinto.bat", flush=True)
    threading.Thread(target=_go, daemon=True).start()


def _esp_msg(event_type, epi):
    """Mensagem educativa (não punitiva) para o OLED do cinto."""
    return {"EPI_AUSENTE": (epi or "EPI") + " necessario nesta area",
            "POSTURA_RISCO": "Postura de risco detectada",
            "ZONA_CRITICA": "Aproximacao de zona restrita",
            "QUEDA": "Queda detectada - verificar",
            "FADIGA": "Sinais de fadiga - pausa"}.get(event_type, "Atencao a seguranca")


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
        summaries = store.worker_summaries()
        lam0, ranking = rank_workers(summaries, horizon=h)
        disp = dispersion_report(summaries, lam0)   # diagnóstico Poisson × BN (superdispersão)
        return jsonify({"lambda0": round(lam0, 3), "horizon": h,
                        "dispersion": disp,
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

    # ── zonas de EXCLUSÃO de máquina: filtram detecções (não geram alerta) ──
    @app.route("/api/exclusions", methods=["GET", "POST"])
    def api_exclusions():
        if request.method == "POST":
            d = request.get_json(force=True)
            rect = d.get("rect") or []
            if len(rect) != 4:
                return jsonify({"ok": False, "error": "rect deve ser [x1,y1,x2,y2] normalizado"}), 400
            try:
                x1, y1, x2, y2 = [max(0.0, min(1.0, float(v))) for v in rect]
            except (TypeError, ValueError):
                return jsonify({"ok": False, "error": "valores invalidos"}), 400
            rect = [min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2)]
            if rect[2] - rect[0] < 0.01 or rect[3] - rect[1] < 0.01:
                return jsonify({"ok": False, "error": "area muito pequena"}), 400
            eid = store.add_exclusion(d.get("name"), rect, station_id=d.get("station_id") or None)
            return jsonify({"ok": True, "id": eid, "rect": rect})
        return jsonify(store.list_exclusions(request.args.get("station_id")))

    @app.route("/api/exclusions/<int:eid>", methods=["PUT", "DELETE"])
    def api_exclusion_edit(eid):
        if request.method == "DELETE":
            store.delete_exclusion(eid); return jsonify({"ok": True})
        store.update_exclusion(eid, **request.get_json(force=True)); return jsonify({"ok": True})

    # ── AREA UTIL: delimita o que o sistema PODE analisar ──
    # Inverso da exclusao: mantem somente o que esta DENTRO do poligono.
    # Na Arena, a plateia fica fora — logo, fora da analise, por construcao.
    @app.route("/api/roi", methods=["GET", "POST"])
    def api_roi():
        if request.method == "POST":
            d = request.get_json(force=True)
            pts = d.get("points") or []
            if len(pts) < 3:
                return jsonify({"ok": False, "error": "a area util precisa de ao menos 3 pontos"}), 400
            rid = store.add_roi(d.get("name", "Area util"), pts, d.get("station_id"))
            return jsonify({"ok": True, "id": rid})
        return jsonify(store.list_roi(request.args.get("station_id")))

    @app.route("/api/roi/<int:rid>", methods=["PUT", "DELETE"])
    def api_roi_edit(rid):
        if request.method == "DELETE":
            store.delete_roi(rid); return jsonify({"ok": True})
        d = request.get_json(force=True)
        if "points" in d and len(d["points"]) < 3:
            return jsonify({"ok": False, "error": "a area util precisa de ao menos 3 pontos"}), 400
        store.update_roi(rid, **d); return jsonify({"ok": True})

    # ── calibração do detector POR ESTAÇÃO (limiar do YOLO) ──
    # Fica na estação (arranjo óptico), não no operador: assim todos que passam
    # pela mesma câmera são medidos com o mesmo instrumento.
    @app.route("/api/stations", methods=["GET", "POST"])
    def api_stations():
        if request.method == "POST":
            d = request.get_json(force=True)
            st = d.get("station_id")
            if not st:
                return jsonify({"ok": False, "error": "station_id obrigatorio"}), 400
            try:
                c = store.set_station_confidence(st, d.get("confidence"))
            except (TypeError, ValueError):
                return jsonify({"ok": False, "error": "confidence invalida"}), 400
            return jsonify({"ok": True, "station_id": st, "confidence": c})
        return jsonify(store.list_stations())

    @app.route("/api/station-confidence")
    def api_station_confidence():
        st = request.args.get("station_id")
        return jsonify({"station_id": st, "confidence": store.get_station_confidence(st)})

    # ── snapshots das cameras: o fundo REAL para desenhar as zonas no /config ──
    # Cada detector manda um JPEG pequeno a cada poucos segundos. Guardamos so o
    # ultimo de cada estacao, em memoria (efemero, nao vai para o banco).
    _snaps = {}

    @app.route("/api/snapshot", methods=["POST"])
    def api_snapshot_post():
        d = request.get_json(force=True)
        st = d.get("station_id"); b64 = d.get("jpg")
        if not st or not b64:
            return jsonify({"ok": False, "error": "station_id e jpg obrigatorios"}), 400
        try:
            _snaps[st] = {"jpg": base64.b64decode(b64), "ts": time.time()}
        except Exception:
            return jsonify({"ok": False, "error": "jpg invalido"}), 400
        return jsonify({"ok": True})

    @app.route("/api/snapshot/<station_id>")
    def api_snapshot_get(station_id):
        s = _snaps.get(station_id)
        if not s:
            return ("", 404)
        return Response(s["jpg"], mimetype="image/jpeg",
                        headers={"Cache-Control": "no-store"})

    @app.route("/api/snapshots")
    def api_snapshots():
        now = time.time()
        return jsonify([{"station_id": k, "age": round(now - v["ts"], 1)}
                        for k, v in sorted(_snaps.items())])

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
                                store.worker_type_breakdown(),
                                shifts_with_events=store.shifts_with_events_per_worker())
        data["team"] = {"streak_critical_days": store.days_since_last_critical(),
                        "conformity": store.conformity_rate()}
        return jsonify(data)

    # ── conformidade NR-7 (PCMSO): painel do GESTOR ──
    # Agendar o exame é responsabilidade da empresa, então o vencimento é
    # cobrado de quem pode agir (o gestor) — no placar do operador o ASO
    # só rende bônus. Expõe apenas validade e contagens; nada de dado clínico.
    @app.route("/api/aso")
    def api_aso():
        dias = max(1, min(int(request.args.get("alerta_dias", 30)), 365))
        return jsonify(store.aso_report(alerta_dias=dias))

    @app.route("/api/aso/<worker_id>", methods=["PUT"])
    def api_aso_set(worker_id):
        d = request.get_json(force=True)
        v = (d.get("aso_validade") or "").strip() or None
        if v:
            try:
                datetime.fromisoformat(v[:10])
            except Exception:
                return jsonify({"ok": False, "error": "data inválida (use AAAA-MM-DD)"}), 400
        store.update_profile(worker_id, aso_validade=v)
        return jsonify({"ok": True, "worker_id": worker_id, "aso_validade": v})

    # ── auditabilidade: verificação de integridade + exportação assinada ──
    @app.route("/api/audit/verify")
    def api_audit_verify():
        rows = store.audit_rows()
        v = audit.verify(rows)
        # assinatura HMAC do hash-cabeca: prova de que a cadeia nao foi trocada inteira
        v["signature"] = audit.sign(audit.head(rows))
        return jsonify(v)

    @app.route("/api/audit/recent")
    def api_audit_recent():
        """Ultimos registros da trilha, ja legiveis (para o painel do gestor)."""
        n = max(1, min(int(request.args.get("limit", 8)), 100))
        filt = {k: request.args.get(k) for k in ("worker_id", "station_id", "turno", "area")
                if request.args.get(k)}
        linhas = audit.flatten(store.audit_rows(), filt or None)
        return jsonify(linhas[-n:][::-1])

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
                        turno=d.get("turno") or prof.get("turno"), station_id=d.get("station_id"),
                        confidence=d.get("confidence"))
        # estado pendente do cinto (modelo PULL): alerta de campo fica disponível
        # para o ESP consultar via /api/belt-status (expira sozinho por TTL).
        if sev_policy.is_field(sev) and d.get("station_id"):
            dev = store.belt_for_station(d["station_id"])
            if dev:
                msg = d.get("message") or _esp_msg(d["type"], d.get("epi"))
                store.set_belt_status(dev, severity=sev, message=msg, epi=d.get("epi"))
                _push_esp(store.esp_for_station(d["station_id"]),
                          {"status": "VIOLACAO", "severity": sev, "message": msg,
                           "epi": d.get("epi"), "worker_id": wid})
        return jsonify({"ok": True, "worker_id": wid, "severity": sev})

    # ── saúde da entrega ao cinto: o alerta está realmente chegando? ──
    @app.route("/api/belt-health")
    def api_belt_health():
        tot = _PUSH["ok"] + _PUSH["fail"]
        return jsonify({**{k: v for k, v in _PUSH.items() if not k.startswith("_")},
                        "total": tot,
                        "taxa_entrega": round(100.0 * _PUSH["ok"] / tot, 1) if tot else None,
                        "cintos": [{"device_id": b["device_id"], "station_id": b.get("station_id"),
                                    "esp32_url": b.get("esp32_url")} for b in store.list_belts()]})

    # ── status pendente do cinto (modelo PULL ultra-baixo-consumo do ESP32) ──
    @app.route("/api/belt-status")
    def api_belt_status():
        dev = request.args.get("device_id")
        if not dev:
            return jsonify({"status": "CONFORME"})
        return jsonify(store.get_belt_status(dev))

    # ── volta imediata ao verde: o campo avisa que a estação ficou CONFORME ──
    @app.route("/api/belt-clear", methods=["POST"])
    def api_belt_clear():
        d = request.get_json(force=True)
        station = d.get("station_id")
        dev = store.belt_for_station(station) if station else None
        if dev:
            store.clear_belt_status(dev)
            _push_esp(store.esp_for_station(station),
                      {"status": "CONFORME", "severity": "ok", "message": "Tudo certo", "epi": ""})
        return jsonify({"ok": True})

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
                                area=prof.get("area"), turno=prof.get("turno"), station_id=station,
                                confidence=d.get("confidence"))
                dev = store.belt_for_station(station)
                if dev and sev_policy.is_field(s):
                    msg = _esp_msg("EPI_AUSENTE", epi)
                    store.set_belt_status(dev, severity=s, message=msg, epi=epi)
                    _push_esp(store.esp_for_station(station),
                              {"status": "VIOLACAO", "severity": s, "message": msg,
                               "epi": epi, "worker_id": wid})
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
