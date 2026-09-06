"""
prelabel_spi.py — Pré-rotulagem automática das fotos reais da SPI (bootstrap).

O que faz: roda o modelo de 12 classes nas imagens de datasets/spi_real e gera
rótulos YOLO CANDIDATOS (.txt) + prévias anotadas (preview/) para REVISÃO humana.
NÃO produz rótulo final — é só um ponto de partida pra acelerar a rotulagem.

Rodar na máquina com GPU (onde o ultralytics está instalado):
    python prelabel_spi.py                         # usa models/best_merged12.pt
    python prelabel_spi.py --model models/best_spi.pt --conf 0.20 --device 0

Depois: revise os .txt (Roboflow ou LabelImg) e só então rode o finetune_spi.py.
As fotos da SPI são close-ups dos EPIs; algumas classes podem sair fracas — por
isso a revisão é obrigatória. Consulte GUIA_ROTULAGEM_SPI.md.
"""
from __future__ import annotations
import argparse, glob, os

BASE = os.path.dirname(os.path.abspath(__file__))
DS = os.path.join(BASE, "datasets", "spi_real")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default=os.path.join(BASE, "models", "best_merged12.pt"),
                    help="modelo de 12 classes para gerar rótulos candidatos")
    ap.add_argument("--conf", type=float, default=0.20, help="confiança mínima (baixa p/ pegar mais candidatos)")
    ap.add_argument("--device", default="0", help="'0' p/ GPU, 'cpu' p/ CPU")
    a = ap.parse_args()

    try:
        from ultralytics import YOLO
    except ImportError:
        raise SystemExit("ultralytics não instalado. Rode isto na máquina com GPU (ver run_setup.bat).")

    if not os.path.exists(a.model):
        raise SystemExit(f"modelo não encontrado: {a.model}")

    model = YOLO(a.model)
    names = model.names
    print(f"Modelo: {a.model}  |  classes: {list(names.values())}")

    total = 0
    per = {}
    empty = []
    for split in ("train", "valid"):
        img_dir = os.path.join(DS, split, "images")
        lbl_dir = os.path.join(DS, split, "labels")
        prev_dir = os.path.join(DS, split, "preview")
        os.makedirs(lbl_dir, exist_ok=True)
        os.makedirs(prev_dir, exist_ok=True)
        imgs = sorted(glob.glob(os.path.join(img_dir, "*.jpg")))
        for ip in imgs:
            r = model.predict(ip, conf=a.conf, device=a.device, verbose=False)[0]
            stem = os.path.splitext(os.path.basename(ip))[0]
            lines = []
            for b in r.boxes:
                cls = int(b.cls)
                x, y, w, h = b.xywhn[0].tolist()
                lines.append(f"{cls} {x:.6f} {y:.6f} {w:.6f} {h:.6f}")
                per[names[cls]] = per.get(names[cls], 0) + 1
                total += 1
            with open(os.path.join(lbl_dir, stem + ".txt"), "w") as f:
                f.write("\n".join(lines))
            if not lines:
                empty.append(os.path.basename(ip))
            try:
                r.save(filename=os.path.join(prev_dir, os.path.basename(ip)))
            except Exception:
                pass

    print("\n─── Resumo da pré-rotulagem ───")
    for k in sorted(per, key=lambda k: -per[k]):
        print(f"  {k:18} {per[k]}")
    print(f"  TOTAL de caixas candidatas: {total}")
    print(f"  Imagens sem nenhuma detecção: {len(empty)} (precisam de rótulo manual)")
    if empty:
        print("   ex.:", ", ".join(empty[:8]) + (" ..." if len(empty) > 8 else ""))
    print("\nPrévias anotadas em: datasets/spi_real/<train|valid>/preview/")
    print("REVISE os .txt antes de treinar. Guia: GUIA_ROTULAGEM_SPI.md")


if __name__ == "__main__":
    main()
