"""Flask: dashboard multi-estacao + API REST."""

import time

from flask import Flask, Response, jsonify, render_template, request

from database import Database


def create_app(db: Database, station_manager=None):
    app = Flask(__name__)
    app.db = db

    # --- Dashboard ---

    @app.route("/")
    def dashboard():
        stations = db.get_all_stations()
        available_epis = ["Hardhat", "Mask", "Safety Vest"]
        return render_template(
            "dashboard.html",
            stations=stations,
            available_epis=available_epis,
        )

    # --- API: Status e monitoramento ---

    @app.route("/api/stations", methods=["GET"])
    def list_stations():
        stations = db.get_all_stations()
        if station_manager is not None:
            runtime = {s["id"]: s for s in station_manager.get_all_status()}
            for s in stations:
                s["runtime"] = runtime.get(s["id"], {})
        return jsonify(stations)

    @app.route("/api/stations/<station_id>/status", methods=["GET"])
    def station_status(station_id):
        station = db.get_station(station_id)
        if station is None:
            return jsonify({"error": "Estacao nao encontrada"}), 404
        if station_manager is not None:
            statuses = station_manager.get_all_status()
            for s in statuses:
                if s["id"] == station_id:
                    station["runtime"] = s
                    break
        return jsonify(station)

    @app.route("/api/stations/<station_id>/stream", methods=["GET"])
    def station_stream(station_id):
        if station_manager is None:
            return "Stream nao disponivel", 503

        def generate():
            while True:
                jpeg = station_manager.get_station_frame(station_id)
                if jpeg is not None:
                    yield (
                        b"--frame\r\n"
                        b"Content-Type: image/jpeg\r\n\r\n" + jpeg + b"\r\n"
                    )
                time.sleep(0.066)

        return Response(
            generate(),
            mimetype="multipart/x-mixed-replace; boundary=frame",
        )

    # --- API: Configuracao ---

    @app.route("/api/stations", methods=["POST"])
    def create_station():
        data = request.get_json()
        required = ("id", "name", "camera_url", "esp32_url")
        missing = [k for k in required if k not in data]
        if missing:
            return jsonify({"error": f"Campos obrigatorios: {missing}"}), 400
        if db.get_station(data["id"]) is not None:
            return jsonify({"error": "ID ja existe"}), 400
        station = db.insert_station(
            station_id=data["id"],
            name=data["name"],
            camera_url=data["camera_url"],
            esp32_url=data["esp32_url"],
            required_epis=data.get("required_epis", []),
            confidence=data.get("confidence", 0.4),
            enabled=data.get("enabled", True),
        )
        return jsonify(station), 201

    @app.route("/api/stations/<station_id>", methods=["PUT"])
    def update_station(station_id):
        data = request.get_json()
        station = db.update_station(station_id, **data)
        if station is None:
            return jsonify({"error": "Estacao nao encontrada"}), 404
        return jsonify(station)

    @app.route("/api/stations/<station_id>", methods=["DELETE"])
    def delete_station(station_id):
        deleted = db.delete_station(station_id)
        if not deleted:
            return jsonify({"error": "Estacao nao encontrada"}), 404
        return jsonify({"ok": True})

    @app.route("/api/stations/<station_id>/enable", methods=["POST"])
    def enable_station(station_id):
        station = db.update_station(station_id, enabled=True)
        if station is None:
            return jsonify({"error": "Estacao nao encontrada"}), 404
        return jsonify(station)

    @app.route("/api/stations/<station_id>/disable", methods=["POST"])
    def disable_station(station_id):
        station = db.update_station(station_id, enabled=False)
        if station is None:
            return jsonify({"error": "Estacao nao encontrada"}), 404
        return jsonify(station)

    # --- API: Violacoes ---

    @app.route("/api/violations", methods=["GET"])
    def get_violations():
        station_id = request.args.get("station_id")
        start = request.args.get("start")
        end = request.args.get("end")
        limit = request.args.get("limit", 50, type=int)
        if start and end:
            rows = db.get_violations_by_date(start, end, station_id=station_id)
        else:
            rows = db.get_violations(limit=limit, station_id=station_id)
        return jsonify(rows)

    @app.route("/api/violations/stats", methods=["GET"])
    def violation_stats():
        station_id = request.args.get("station_id")
        total = db.get_violation_count(station_id=station_id)
        return jsonify({"total": total, "station_id": station_id})

    # --- API: Alarme ---

    @app.route("/api/silence", methods=["POST"])
    def silence_alarm():
        if hasattr(app, "detection_status") and app.detection_status is not None:
            app.detection_status.set_silenced(True)
        return jsonify({"silenced": True})

    return app
