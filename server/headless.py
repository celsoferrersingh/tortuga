"""
headless.py — Deteccao sem janela para camera IP (Fase 4) · Projeto Tortuga

Reaproveita o detector das Fases 1-2 sem GUI: le o stream, detecta EPIs, infere
ausencia por estacao e envia eventos reais ao dashboard (ingest throttled) ou
reporta presenca para a FUSAO multi-camera (--fusion). Reconecta sozinho.

Uso:
    python headless.py --camera rtsp://user:senha@10.0.0.21/stream1 --station-id EST-PRE --preprocess
    python headless.py --camera rtsp://...A --station-id EST-PRE --fusion   # angulo A
    python headless.py --camera rtsp://...B --station-id EST-PRE --fusion   # angulo B
"""
from __future__ import annotations
import argparse, json, os, sys, time
import cv2

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from detector import PPEDetector
from dashboard_client import DashboardClient


def _open(src):
    # RTSP (camera IP): FFMPEG com transporte TCP (mais estavel que UDP) e baixa latencia.
    is_url = isinstance(src, str) and "://" in src
    if is_url:
        os.environ.setdefault("OPENCV_FFMPEG_CAPTURE_OPTIONS",
                              "rtsp_transport;tcp|max_delay;500000|stimeout;5000000")
        cap = cv2.VideoCapture(src, cv2.CAP_FFMPEG)
    else:
        cap = cv2.VideoCapture(src)
    try: cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
    except Exception: pass
    return cap


def main():
    p = argparse.ArgumentParser(description="Tortuga — deteccao headless (camera IP)")
    p.add_argument("--camera", default="0")
    p.add_argument("--model", default=os.path.join(os.path.dirname(__file__), "models", "best.pt"))
    p.add_argument("--confidence", type=float, default=0.4)
    p.add_argument("--det-size", type=int, default=640)
    p.add_argument("--dashboard", default="http://localhost:5005")
    p.add_argument("--station-id", default=None)
    p.add_argument("--device", default=None)
    p.add_argument("--preprocess", action="store_true")
    p.add_argument("--preprocess-opts", default=None, help="JSON de opcoes de pre-processamento por camera")
    p.add_argument("--profile-refresh", type=float, default=10.0, help="seg p/ reler o operador ativo (QR)")
    p.add_argument("--fusion", action="store_true", help="Modo fusao: reporta presenca; o servidor funde varios angulos")
    p.add_argument("--camera-id", default=None, help="ID unico desta camera (p/ fusao na mesma estacao)")
    a = p.parse_args()

    src = int(a.camera) if str(a.camera).isdigit() else a.camera
    pre = json.loads(a.preprocess_opts) if a.preprocess_opts else ({"adaptive": True} if a.preprocess else False)
    print(f"  [headless] estacao {a.station_id} · fonte {a.camera}" + (" · FUSAO" if a.fusion else ""))
    det = PPEDetector(a.model, confidence=a.confidence, device=a.device, preprocess=pre)
    dash = DashboardClient(a.dashboard, station_id=a.station_id, camera_id=a.camera_id)

    prof = dash.active_profile() or {}
    required = prof.get("required_epis", [])
    if prof.get("confidence"):
        det.confidence = float(prof["confidence"])
    print(f"  [headless] operador ativo: {prof.get('worker_id','-')} | EPIs={required} | conf={det.confidence}")

    cap = _open(src)
    last_prof = time.time(); last_log = 0.0; fails = 0; n = 0
    try:
        while True:
            ok, frame = cap.read()
            if not ok or frame is None:
                fails += 1
                if fails % 10 == 1:
                    print(f"  [headless] sem frame ({a.camera}); reconectando...")
                cap.release(); time.sleep(min(5.0, 0.5 * fails)); cap = _open(src)
                continue
            fails = 0; n += 1

            h, w = frame.shape[:2]
            if max(h, w) > a.det_size:
                s = a.det_size / max(h, w)
                frame = cv2.resize(frame, (int(w * s), int(h * s)))

            dets = det.detect(frame)
            person = any("person" in d["class_name"].lower() for d in dets)
            missing = PPEDetector.missing_required(dets, required, person)

            if a.fusion:
                present = [e for e in required if e not in missing]
                dash.observe(present=present, person=person)
            else:
                for d in dets:
                    if d.get("is_violation"):
                        dash.ingest(type="EPI_AUSENTE", epi=d["class_name"], severity=None)
                for epi in missing:
                    dash.ingest(type="EPI_AUSENTE", epi=epi, severity=None)

            now = time.time()
            if now - last_prof >= a.profile_refresh:
                last_prof = now
                np_ = dash.active_profile()
                if np_ and np_.get("worker_id") != prof.get("worker_id"):
                    prof = np_; required = prof.get("required_epis", [])
                    if prof.get("confidence"): det.confidence = float(prof["confidence"])
                    print(f"  [headless] novo operador ativo: {prof.get('worker_id')} | EPIs={required}")
            if now - last_log >= 15.0:
                last_log = now
                print(f"  [headless] {a.station_id}: {n} frames, {len(dets)} det no ultimo, pessoa={person}")
    except KeyboardInterrupt:
        print("\n  [headless] encerrando.")
    finally:
        cap.release()


if __name__ == "__main__":
    main()
