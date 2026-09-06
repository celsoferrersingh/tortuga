"""
finetune_spi.py — Fine-tune ADITIVO do detector com os dados reais da SPI.

Filosofia (à prova de regressão):
  • Parte do modelo atual (best_merged12.pt), NÃO treina do zero.
  • Treina com merged (Roboflow) + spi_real JUNTOS (data_spi_plus.yaml) —
    o dataset base NÃO é substituído.
  • Congela o backbone (freeze) e usa learning-rate baixo p/ não "esquecer" o base.
  • Gera um arquivo NOVO: models/best_spi.pt. O modelo em produção fica intacto.
  • Valida SÓ nas fotos da SPI e escreve um relatório (models/validacao_spi.txt).

Rodar na máquina com GPU:
    python finetune_spi.py                    # 40 épocas, imgsz 640, GPU 0
    python finetune_spi.py --epochs 60 --imgsz 800 --device 0

Promova para produção só depois de conferir o relatório de validação.
"""
from __future__ import annotations
import argparse, os, shutil, datetime

BASE = os.path.dirname(os.path.abspath(__file__))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default=os.path.join(BASE, "models", "best_merged12.pt"),
                    help="modelo de partida (fine-tune a partir dele)")
    ap.add_argument("--data", default=os.path.join(BASE, "datasets", "data_spi_plus.yaml"),
                    help="dataset COMBINADO (merged + spi_real)")
    ap.add_argument("--epochs", type=int, default=40)
    ap.add_argument("--imgsz", type=int, default=640)
    ap.add_argument("--device", default="0")
    ap.add_argument("--freeze", type=int, default=10, help="camadas congeladas (preserva o base)")
    ap.add_argument("--lr0", type=float, default=0.005, help="lr baixo p/ fine-tune")
    ap.add_argument("--name", default="tortuga_spi")
    ap.add_argument("--out", default=os.path.join(BASE, "models", "best_spi.pt"))
    a = ap.parse_args()

    try:
        from ultralytics import YOLO
    except ImportError:
        raise SystemExit("ultralytics não instalado. Rode na máquina com GPU (ver run_setup.bat).")

    for p in (a.base, a.data):
        if not os.path.exists(p):
            raise SystemExit(f"não encontrado: {p}")

    print(f"Base:   {a.base}")
    print(f"Dados:  {a.data}  (merged + spi_real — ADITIVO)")
    print(f"Fine-tune: epochs={a.epochs} imgsz={a.imgsz} freeze={a.freeze} lr0={a.lr0} device={a.device}\n")

    model = YOLO(a.base)
    model.train(data=a.data, epochs=a.epochs, imgsz=a.imgsz, device=a.device,
                freeze=a.freeze, lr0=a.lr0, patience=15, name=a.name,
                project=os.path.join(BASE, "runs", "train"), exist_ok=True)

    run_dir = os.path.join(BASE, "runs", "train", a.name)
    run_best = os.path.join(run_dir, "weights", "best.pt")
    if not os.path.exists(run_best):
        raise SystemExit(f"treino terminou mas não achei {run_best}")

    # backup do modelo de produção antes de qualquer coisa, e escrita do NOVO arquivo
    shutil.copy(run_best, a.out)
    print(f"\n✔ Novo modelo salvo (SEM substituir produção): {a.out}")

    # ─── validação SÓ nas fotos reais da SPI ───
    print("\n─── Validação nas fotos reais da SPI ───")
    spi_yaml = os.path.join(BASE, "datasets", "spi_real", "data.yaml")
    m = YOLO(a.out)
    metrics = m.val(data=spi_yaml, device=a.device, split="val", verbose=False)
    try:
        mp, mr = float(metrics.box.mp), float(metrics.box.mr)
        map50, map5095 = float(metrics.box.map50), float(metrics.box.map)
    except Exception:
        mp = mr = map50 = map5095 = float("nan")

    report = os.path.join(BASE, "models", "validacao_spi.txt")
    with open(report, "w", encoding="utf-8") as f:
        f.write("Validação do fine-tune com dados reais da SPI\n")
        f.write(f"Data: {datetime.datetime.now():%Y-%m-%d %H:%M}\n")
        f.write(f"Base: {os.path.basename(a.base)}  ->  {os.path.basename(a.out)}\n")
        f.write(f"Épocas: {a.epochs} | imgsz: {a.imgsz} | freeze: {a.freeze} | lr0: {a.lr0}\n\n")
        f.write(f"Precision (média): {mp:.3f}\n")
        f.write(f"Recall (média):    {mr:.3f}\n")
        f.write(f"mAP@0.5:           {map50:.3f}\n")
        f.write(f"mAP@0.5:0.95:      {map5095:.3f}\n")
    print(open(report, encoding="utf-8").read())
    print(f"Relatório salvo em: {report}")
    print("\nPara promover à produção (depois de conferir): copie best_spi.pt sobre o modelo usado pelo detector.")


if __name__ == "__main__":
    main()
