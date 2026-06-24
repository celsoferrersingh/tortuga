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

    # libs do dashboard (opcionais p/ detecção, necessárias p/ Fase 3)
    for name in ("flask", "requests"):
        try:
            importlib.import_module(name); print(OK, f"{name} (dashboard/ingestão)")
        except Exception:
            print(WARN, f"{name} ausente — necessário só p/ dashboard/ingestão (pip install {name})")

    # câmera (opcional)
    if a.camera is not None:
        try:
            import cv2
            src = int(a.camera) if str(a.camera).isdigit() else a.camera
            cap = cv2.VideoCapture(src)
            ok, frame = (cap.isOpened(), None)
            if ok: ok, frame = cap.read()
            cap.release()
            if ok and frame is not None:
                print(OK, f"Câmera '{a.camera}' abriu e entregou frame {frame.shape[1]}x{frame.shape[0]}")
            else:
                print(FAIL, f"Câmera '{a.camera}' não entregou frame")
        except Exception as e:
            print(FAIL, f"Câmera '{a.camera}':", e)

    print("=" * 60)
    if essentials_ok:
        print("  RESULTADO: ambiente PRONTO para rodar o Tortuga. ✔")
    else:
        print("  RESULTADO: faltam dependências essenciais (veja [FALHA] acima).")
    print("=" * 60 + "\n")
    return 0 if essentials_ok else 1


if __name__ == "__main__":
    sys.exit(main())
