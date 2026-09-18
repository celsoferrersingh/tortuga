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
import argparse, base64, json, os, sys, time
import cv2

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from detector import PPEDetector
from dashboard_client import DashboardClient


def _open(src):
    # RTSP (camera IP): FFMPEG com transporte TCP (mais estavel que UDP) e baixa latencia.
    is_url = isinstance(src, str) and "://" in src
    if is_url:
        os.environ.setdefault("OPENCV_FFMPEG_CAPTURE_OPTIONS",
                              "rtsp_transport;tcp|max_delay;500000|stimeout;15000000|timeout;15000000")
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
    p.add_argument("--ignore", default=None,
                   help='JSON [[x1,y1,x2,y2],...] normalizado: zonas de exclusao de maquina')
    a = p.parse_args()

    src = int(a.camera) if str(a.camera).isdigit() else a.camera
    pre = json.loads(a.preprocess_opts) if a.preprocess_opts else ({"adaptive": True} if a.preprocess else False)
    print(f"  [headless] estacao {a.station_id} · fonte {a.camera}" + (" · FUSAO" if a.fusion else ""))
    det = PPEDetector(a.model, confidence=a.confidence, device=a.device, preprocess=pre)
    dash = DashboardClient(a.dashboard, station_id=a.station_id, camera_id=a.camera_id)

    # ── Zonas de exclusao de maquina (ex.: braco robotico fixo no quadro) ──
    # Vem do arquivo de config (--ignore) MAIS as que o gestor desenhou no /config.
    # Descartam deteccoes cujo CENTRO cai na regiao: a maquina deixa de virar "pessoa".
    ignore_file = []
    if a.ignore:
        try:
            ignore_file = json.loads(a.ignore)
        except Exception:
            print("  [headless] --ignore invalido; seguindo sem zona de arquivo")
    ignore_dash = dash.exclusions()
    ignore = list(ignore_file) + list(ignore_dash)
    if ignore:
        print(f"  [headless] zonas de exclusao: {len(ignore)} "
              f"({len(ignore_file)} da config + {len(ignore_dash)} do dashboard)")

    def _ignored(bbox, W, H):
        if not bbox:
            return False
        cx = (bbox[0] + bbox[2]) / 2.0; cy = (bbox[1] + bbox[3]) / 2.0
        return any(x1 * W <= cx <= x2 * W and y1 * H <= cy <= y2 * H
                   for (x1, y1, x2, y2) in ignore)

    prof = dash.active_profile() or {}
    required = prof.get("required_epis", [])
    # limiar = calibracao da ESTACAO (nao do operador); se nao houver, usa o --confidence
    station_conf = dash.station_confidence()
    if station_conf is not None:
        det.confidence = float(station_conf)
        print(f"  [headless] calibracao da estacao {a.station_id}: confianca {station_conf:.0%}")
    dash.set_confidence(det.confidence)
    print(f"  [headless] operador ativo: {prof.get('worker_id','-')} | EPIs={required} | conf={det.confidence}")

    cap = _open(src)
    last_prof = time.time(); last_log = 0.0; last_snap = 0.0; fails = 0; n = 0
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
            if ignore:                      # filtra maquinas fixas antes de qualquer decisao
                _h, _w = frame.shape[:2]
                dets = [d for d in dets if not _ignored(d.get("bbox"), _w, _h)]
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
            # print periodico da camera -> fundo real para desenhar zonas no /config
            if now - last_snap >= 5.0:
                last_snap = now
                try:
                    _ok, _buf = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 60])
                    if _ok:
                        dash.snapshot(base64.b64encode(_buf.tobytes()).decode())
                except Exception:
                    pass
            if now - last_prof >= a.profile_refresh:
                last_prof = now
                _ex = dash.exclusions()          # o gestor pode desenhar durante a operacao
                if _ex != ignore_dash:
                    ignore_dash = _ex
                    ignore = list(ignore_file) + list(ignore_dash)
                    print(f"  [headless] zonas de exclusao atualizadas: {len(ignore)}")
                np_ = dash.active_profile()
                if np_ and np_.get("worker_id") != prof.get("worker_id"):
                    prof = np_; required = prof.get("required_epis", [])
                    print(f"  [headless] novo operador ativo: {prof.get('worker_id')} | EPIs={required}")
                _sc = dash.station_confidence()
                if _sc is not None and _sc != station_conf:
                    station_conf = _sc; det.confidence = float(_sc)
                    print(f"  [headless] calibracao da estacao atualizada: confianca {_sc:.0%}")
                dash.set_confidence(det.confidence)
            if now - last_log >= 15.0:
                last_log = now
                print(f"  [headless] {a.station_id}: {n} frames, {len(dets)} det no ultimo, pessoa={person}")
    except KeyboardInterrupt:
        print("\n  [headless] encerrando.")
    finally:
        cap.release()


if __name__ == "__main__":
    main()
