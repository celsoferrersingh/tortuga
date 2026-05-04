"""
train_oculos.py - Treino do modelo de oculos (Safety Glasses)
Uso: python train_oculos.py
Resultado: server/models/best.pt  (novo modelo de oculos)
           server/models/best.old.pt  (backup do modelo EPI anterior)
"""
import sys
import shutil
from pathlib import Path
import yaml
import torch


# ── Paths ──────────────────────────────────────────────────────────
SERVER_DIR  = Path(__file__).parent.resolve()
DATASET_DIR = SERVER_DIR / "datasets" / "oculos"
MODELS_DIR  = SERVER_DIR / "models"
YAML_SRC    = DATASET_DIR / "data.yaml"
YAML_FIXED  = DATASET_DIR / "data_fixed.yaml"
BASE_MODEL  = MODELS_DIR / "yolov8n.pt"
BEST_PT     = MODELS_DIR / "best.pt"
BEST_OLD_PT = MODELS_DIR / "best.old.pt"
RUNS_DIR    = SERVER_DIR / "runs_oculos"


def main():
    # ── Verifica GPU ───────────────────────────────────────────────
    device = "cuda" if torch.cuda.is_available() else "cpu"
    if device == "cuda":
        print(f"\n  GPU: {torch.cuda.get_device_name(0)}")
        print(f"  VRAM disponivel: {torch.cuda.get_device_properties(0).total_memory / 1e9:.1f} GB")
    else:
        print("\n  [AVISO] GPU nao encontrada, usando CPU (mais lento)")
    print()

    # ── Corrige paths do data.yaml para absolutos ──────────────────
    with open(YAML_SRC, "r") as f:
        data = yaml.safe_load(f)

    data["train"] = str(DATASET_DIR / "train" / "images")
    data["val"]   = str(DATASET_DIR / "valid" / "images")
    data["test"]  = str(DATASET_DIR / "test"  / "images")

    with open(YAML_FIXED, "w") as f:
        yaml.dump(data, f, allow_unicode=True)

    print(f"  Dataset : {DATASET_DIR}")
    print(f"  Classes : {data['names']}")
    print(f"  Device  : {device.upper()}")
    print()

    # ── Backup do modelo atual ─────────────────────────────────────
    if BEST_PT.exists():
        shutil.copy2(BEST_PT, BEST_OLD_PT)
        print(f"  [OK] Backup: best.pt -> best.old.pt")

    # ── Treino ─────────────────────────────────────────────────────
    from ultralytics import YOLO

    print("  Iniciando treino...\n")

    model = YOLO(str(BASE_MODEL))

    results = model.train(
        data     = str(YAML_FIXED),
        epochs   = 60,
        imgsz    = 640,
        batch    = 16,      # RTX 4050 — reduz para 8 se aparecer OOM
        device   = device,
        project  = str(RUNS_DIR),
        name     = "oculos",
        exist_ok = True,
        patience = 15,      # early stopping
        workers  = 0,       # Windows exige workers=0 (spawn)
        verbose  = True,
        plots    = True,
    )

    # ── Copia o melhor modelo para models/ ────────────────────────
    trained_best = RUNS_DIR / "oculos" / "weights" / "best.pt"

    if trained_best.exists():
        shutil.copy2(trained_best, BEST_PT)
        print(f"\n  [OK] Modelo salvo em: {BEST_PT}")
        print(f"  [OK] Backup anterior: {BEST_OLD_PT}")

        metrics = results.results_dict
        if metrics:
            p   = metrics.get("metrics/precision(B)", 0)
            r   = metrics.get("metrics/recall(B)", 0)
            mp5 = metrics.get("metrics/mAP50(B)", 0)
            print(f"\n  Resultados finais:")
            print(f"    Precision : {p:.3f}")
            print(f"    Recall    : {r:.3f}")
            print(f"    mAP@50    : {mp5:.3f}")
    else:
        print("\n  [ERRO] Arquivo best.pt nao encontrado nos resultados.")
        print(f"  Verifique: {RUNS_DIR / 'oculos' / 'weights'}")
        sys.exit(1)

    print("\n  Treino concluido! Reinicie o gui.py para usar o novo modelo.\n")


if __name__ == "__main__":
    main()
