"""
tune_preprocess.py — Ajuste fino de robustez em filmagem REAL (Fase 4) · Tortuga

A iluminação de cada câmera é diferente. Em vez de chutar parâmetros, rode esta
ferramenta na SUA filmagem (vídeo, imagem ou pasta) e ela compara presets de
pré-processamento, medindo qual recupera mais detecções de EPI sob a luz daquela
câmera. O resultado é o `preprocess` que você cola na `tortuga.config.json`.

Uso:
    python tune_preprocess.py --source corredor_escuro.mp4
    python tune_preprocess.py --source frame.jpg --save out_compare
    python tune_preprocess.py --source pasta_de_frames --frames 60

Sem ultralytics/torch instalados, roda em modo "só iluminação" (brilho/contraste);
com o detector disponível, acrescenta detecções/confiança por preset (recomendado).
"""
from __future__ import annotations
import argparse, glob, os, sys
import cv2

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import preprocess as pp

PRESETS = {
    "off":        None,
    "adaptive":   {"adaptive": True},
    "clahe-2":    {"adaptive": False, "gamma": "auto", "clip": 2.0, "tile": 8},
    "clahe-4":    {"adaptive": False, "gamma": "auto", "clip": 4.0, "tile": 8},
    "gamma-only": {"adaptive": False, "gamma": "auto", "clahe": False},
}


def sample_frames(source, n):
    if os.path.isdir(source):
        files = sorted(sum([glob.glob(os.path.join(source, "*." + e))
                            for e in ("jpg", "jpeg", "png", "bmp")], []))
        frames = [cv2.imread(f) for f in files[:n]]
        return [f for f in frames if f is not None]
    if str(source).split(".")[-1].lower() in ("jpg", "jpeg", "png", "bmp"):
        img = cv2.imread(source); return [img] if img is not None else []
    cap = cv2.VideoCapture(int(source) if str(source).isdigit() else source)
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) or 0
    out = []
    if total > 1:
        idxs = [int(i * total / n) for i in range(n)]
        for i in idxs:
            cap.set(cv2.CAP_PROP_POS_FRAMES, i)
            ok, f = cap.read()
            if ok and f is not None: out.append(f)
    else:                                   # stream ao vivo: lê n quadros
        for _ in range(n):
            ok, f = cap.read()
            if ok and f is not None: out.append(f)
    cap.release()
    return out


def _make_detector(model, device):
    try:
        from detector import PPEDetector
        return PPEDetector(model, confidence=0.4, device=device, preprocess=False)
    except Exception as e:
        print("  [info] detector indisponível (%s) — modo só-iluminação." % e)
        return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", required=True, help="vídeo, imagem, pasta ou índice de webcam")
    ap.add_argument("--model", default=os.path.join(os.path.dirname(__file__), "models", "best.pt"))
    ap.add_argument("--frames", type=int, default=40)
    ap.add_argument("--device", default=None)
    ap.add_argument("--save", default=None, help="prefixo p/ salvar 1 frame antes/depois por preset")
    a = ap.parse_args()

    frames = sample_frames(a.source, a.frames)
    if not frames:
        sys.exit("Nenhum frame lido de: %s" % a.source)
    print("  Amostrados %d frames de %s" % (len(frames), a.source))
    print("  Iluminação original: brilho méd %.2f · contraste méd %.2f" % (
        sum(pp.brightness(f) for f in frames) / len(frames),
        sum(pp.contrast(f) for f in frames) / len(frames)))

    det = _make_detector(a.model, a.device)
    rows = []
    for name, kw in PRESETS.items():
        nd = nc = nb = ncon = 0.0
        for f in frames:
            e = f if kw is None else pp.enhance(f, **kw)
            nb += pp.brightness(e); ncon += pp.contrast(e)
            if det is not None:
                dets = det.detect(e)
                nd += len(dets)
                safe = [d for d in dets if not d.get("is_violation")]
                nc += len(safe)
                if dets:
                    ncon_local = sum(d["confidence"] for d in dets) / len(dets)
                    ncon += ncon_local
        k = len(frames)
        rows.append({"preset": name, "bright": nb / k, "contrast": ncon / k if det else ncon,
                     "dets": nd / k, "safe": nc / k, "conf": (ncon / k) if det else None,
                     "contraste": ncon / k})
        if a.save:
            f0 = frames[0]; e0 = f0 if kw is None else pp.enhance(f0, **kw)
            cv2.imwrite("%s_%s.png" % (a.save, name), e0)

    print("\n  %-11s %8s %9s %9s %9s" % ("preset", "brilho", "contraste", "detec/f", "EPIs/f"))
    for r in rows:
        print("  %-11s %8.2f %9.2f %9.2f %9.2f" % (
            r["preset"], r["bright"], r["contraste"], r["dets"], r["safe"]))

    if det is not None:
        best = max(rows, key=lambda r: (round(r["safe"], 2), round(r["dets"], 2)))
        print("\n  >> Recomendado p/ esta câmera: '%s' (mais EPIs detectados/frame)." % best["preset"])
        if best["preset"] != "off":
            kw = PRESETS[best["preset"]]
            print("     Cole na câmera da config:  \"preprocess\": %s" % _json(kw))
    else:
        worst = min(rows, key=lambda r: abs(r["bright"] - pp.TARGET_MEAN))
        print("\n  >> Sem detector: pelo brilho, '%s' aproxima melhor do alvo 0,50." % worst["preset"])
        print("     Instale ultralytics+torch p/ a recomendação por detecções.")


def _json(kw):
    import json
    return json.dumps(kw, ensure_ascii=False)


if __name__ == "__main__":
    main()
