"""
tortuga_doctor.py — Checagem de compatibilidade de ambiente (Fase 4) · Tortuga

"Na minha máquina roda; e no hardware da metaindústria?" Este script responde
isso ANTES de a banca/cliente tentar subir o sistema. Verifica device, libs,
modelos e câmera, imprime um relatório e devolve exit-code (0 = pronto).

Uso:
    python tortuga_doctor.py                # checagem completa
    python tortuga_doctor.py --camera 0     # também testa abrir a câmera 0
"""
from __future__ import annotations
import argparse, importlib, os, platform, sys

OK, WARN, FAIL = "  [OK]   ", "  [AVISO]", "  [FALHA]"


def _v(mod):
    return getattr(mod, "__version__", "?")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--camera", default=None, help="Testa abrir esta câmera (0, rtsp://..., arquivo)")
    a = ap.parse_args()

    here = os.path.dirname(os.path.abspath(__file__))
    print("\n" + "=" * 60)
    print("  TORTUGA · Diagnóstico de ambiente (Fase 4)")
    print("=" * 60)
    print(f"  SO        : {platform.system()} {platform.release()} ({platform.machine()})")
    print(f"  Python    : {sys.version.split()[0]}  [{sys.executable}]")

    essentials_ok = True

    # numpy / opencv
    try:
        import numpy as np; print(OK, "numpy", _v(np))
    except Exception as e:
        print(FAIL, "numpy:", e); essentials_ok = False
    try:
        import cv2; print(OK, "OpenCV (cv2)", _v(cv2))
    except Exception as e:
        print(FAIL, "OpenCV (cv2):", e); essentials_ok = False

    # torch + device
    device = "cpu"
    try:
        import torch
        cuda = torch.cuda.is_available()
        try: mps = torch.backends.mps.is_available()
        except Exception: mps = False
        print(OK, "torch", _v(torch), f"| CUDA={cuda} | MPS(Metal)={mps}")
        if cuda:
            try:
                print(OK, f"GPU: {torch.cuda.get_device_name(0)} | CUDA runtime {torch.version.cuda}")
            except Exception:
                pass
        env = (os.environ.get("TORTUGA_DEVICE") or "auto").lower()
        device = ("cuda" if (env in ("auto","cuda") and cuda)
                  else "mps" if (env in ("auto","mps") and mps)
                  else "cpu")
        if device == "cpu":
            print(WARN, "Inferência em CPU — funciona, mas reduza --det-size (480) p/ FPS")
        else:
            print(OK, f"Device de inferência escolhido: {device.upper()}")
        if env == "cuda" and not cuda:
            print(WARN, "TORTUGA_DEVICE=cuda mas CUDA indisponível → cairá p/ CPU. "
                        "(No Windows, use o venv com torch CUDA, não o Python da Store.)")
    except Exception as e:
        print(FAIL, "torch:", e); essentials_ok = False

    # ultralytics
    try:
        import ultralytics; print(OK, "ultralytics", _v(ultralytics))
    except Exception as e:
        print(FAIL, "ultralytics:", e); essentials_ok = False

    # preprocess (robustez)
    try:
        sys.path.insert(0, here)
        import preprocess, numpy as np
        f = (np.ones((64, 64, 3), dtype="uint8") * 20)
        _ = preprocess.enhance(f)
        print(OK, "preprocess (CLAHE+gama) operacional")
    except Exception as e:
        print(WARN, "preprocess:", e)

    # modelos
    models = os.path.join(here, "models")
    best = os.path.join(models, "best.pt")
    if os.path.exists(best):
        mb = os.path.getsize(best) / 1e6
        print(OK, f"models/best.pt presente ({mb:.1f} MB)")
    else:
        print(FAIL, "models/best.pt NÃO encontrado"); essentials_ok = False
    print((OK if os.path.exists(os.path.join(models, "best.old.pt")) else WARN),
          "models/best.old.pt", "presente (modo DUAL)" if os.path.exists(os.path.join(models, "best.old.pt")) else "ausente (modo SINGLE — ok)")

    # libs do dashboard (necessárias p/ Fase 3: flask serve o painel, qrcode gera o QR do cinto)
    for name in ("flask", "qrcode"):
        try:
            importlib.import_module(name); print(OK, f"{name} (dashboard Fase 3)")
        except Exception:
            print(WARN, f"{name} ausente — necessário p/ o dashboard (pip install \"{name}[pil]\" )"
                        if name == "qrcode" else
                        f"{name} ausente — necessário p/ o dashboard (pip install {name})")

    # câmera / RTSP — usa o MESMO backend do runtime (FFMPEG+TCP p/ RTSP).
    # Se --camera não for passado, testa automaticamente a 1ª câmera de tortuga.config.json.
    cam_to_test = a.camera
    if cam_to_test is None:
        cfg = os.path.join(here, "tortuga.config.json")
        if os.path.exists(cfg):
            try:
                import json
                c = json.load(open(cfg, encoding="utf-8"))
                cams = c.get("cameras", [])
                if cams:
                    cam_to_test = str(cams[0].get("source"))
                    print(OK, f"Config: testando a 1ª câmera '{cams[0].get('station_id','?')}' → {cam_to_test}")
            except Exception as e:
                print(WARN, "tortuga.config.json ilegível:", e)
    if cam_to_test is not None:
        s = str(cam_to_test)
        is_url = "://" in s
        if is_url and ("USUARIO" in s or "IP_DA_CAMERA" in s or "SENHA" in s):
            print(WARN, "RTSP ainda é o placeholder — edite server/tortuga.config.json com IP/usuário/senha reais.")
        elif is_url:
            # RTSP: primeiro uma checagem de REDE pura (a camera responde DAQUI?).
            # Isso evita falso positivo (ex.: OpenCV cair numa webcam local e reportar
            # "camera OK"). So tenta abrir o stream se a porta estiver acessivel.
            import re, socket
            m = re.search(r"@([^/:]+):?(\d+)?", s) or re.search(r"://([^/:]+):?(\d+)?", s)
            host = m.group(1) if m else None
            port = int(m.group(2)) if (m and m.group(2)) else 554
            reachable = False
            if host:
                try:
                    sk = socket.create_connection((host, port), timeout=4); sk.close(); reachable = True
                except Exception:
                    reachable = False
            if not reachable:
                print(WARN, f"Câmera RTSP {host}:{port} inacessível desta rede — NORMAL fora da "
                            f"rede da metaindústria. Rode o doctor lá para validar o stream real.")
            else:
                try:
                    import cv2
                    os.environ.setdefault("OPENCV_FFMPEG_CAPTURE_OPTIONS",
                                          "rtsp_transport;tcp|max_delay;500000|stimeout;5000000")
                    cap = cv2.VideoCapture(s, cv2.CAP_FFMPEG)
                    try: cap.set(cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, 5000)
                    except Exception: pass
                    ok = cap.isOpened(); frame = None
                    if ok: ok, frame = cap.read()
                    cap.release()
                    if ok and frame is not None:
                        print(OK, f"Câmera RTSP abriu e entregou frame {frame.shape[1]}x{frame.shape[0]}")
                    else:
                        print(FAIL, "Câmera RTSP alcançável, mas sem frame (confira usuário/senha/caminho).")
                except Exception as e:
                    print(FAIL, "Câmera RTSP:", e)
        else:
            # indice de webcam (0,1) ou arquivo de video
            try:
                import cv2
                src = int(s) if s.isdigit() else s
                cap = cv2.VideoCapture(src)
                ok = cap.isOpened(); frame = None
                if ok: ok, frame = cap.read()
                cap.release()
                if ok and frame is not None:
                    print(OK, f"Fonte '{s}' abriu e entregou frame {frame.shape[1]}x{frame.shape[0]}")
                else:
                    print(FAIL, f"Fonte '{s}' não entregou frame")
            except Exception as e:
                print(FAIL, f"Fonte '{s}':", e)

    print("=" * 60)
    if essentials_ok:
        print("  RESULTADO: ambiente PRONTO para rodar o Tortuga. ✔")
    else:
        print("  RESULTADO: faltam dependências essenciais (veja [FALHA] acima).")
    print("=" * 60 + "\n")
    return 0 if essentials_ok else 1


if __name__ == "__main__":
    sys.exit(main())
