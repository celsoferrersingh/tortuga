"""
train_model.py — Retreino YOLOv8 com novos EPIs (Fase 1 lacunas)
Challenge SPI 2026

Treina ou fine-tune o modelo best.pt adicionando as classes:
  - Protetor auricular (Ear Protection / NO-Ear Protection)
  - Bota de segurança  (Safety Boots  / NO-Safety Boots)

USO:
  python train_model.py                          # treino padrão
  python train_model.py --epochs 50 --batch 16   # personalizado
  python train_model.py --resume                 # continuar treino interrompido
  python train_model.py --validate               # só validar modelo atual

SAÍDA:
  server/runs/train/tortuga_ppe/weights/best.pt  → copia para server/models/best.pt
"""

import argparse
import shutil
import yaml
from pathlib import Path

# ─── Constantes ───────────────────────────────────────────────
BASE_DIR    = Path(__file__).parent
MODELS_DIR  = BASE_DIR / "models"
DATASET_DIR = BASE_DIR / "datasets"
RUNS_DIR    = BASE_DIR / "runs"

# Dataset consolidado (merge de todos os baixados)
MERGED_YAML = BASE_DIR / "datasets" / "merged" / "data.yaml"

# Classes alvo — todas as classes que o modelo final deve detectar
TARGET_CLASSES = [
    "Hardhat",          "NO-Hardhat",
    "Safety Vest",      "NO-Safety Vest",
    "Safety Glasses",   "NO-Safety Glasses",
    "Mask",             "NO-Mask",
    "Ear Protection",   "NO-Ear Protection",   # NOVO — Fase 1
    "Safety Boots",     "NO-Safety Boots",     # NOVO — Fase 1
]


def merge_datasets():
    """
    Combina múltiplos datasets YOLOv8 em um único diretório 'merged'.
    Realiza remapeamento de classes para o padrão Tortuga.
    """
    from download_datasets import CLASS_REMAP

    merged_dir = DATASET_DIR / "merged"
    for split in ["train", "valid", "test"]:
        (merged_dir / split / "images").mkdir(parents=True, exist_ok=True)
        (merged_dir / split / "labels").mkdir(parents=True, exist_ok=True)

    all_classes = TARGET_CLASSES
    class_to_id = {c.lower(): i for i, c in enumerate(all_classes)}

    img_count = {"train": 0, "valid": 0, "test": 0}

    for ds_dir in DATASET_DIR.iterdir():
        if ds_dir.name == "merged" or not ds_dir.is_dir():
            continue

        # Lê classes deste dataset — procura data.yaml na raiz ou subpasta
        yaml_file = ds_dir / "data.yaml"
        if not yaml_file.exists():
            # Alguns downloads colocam data.yaml numa subpasta
            candidates = list(ds_dir.rglob("data.yaml"))
            if not candidates:
                print(f"  AVISO: {ds_dir.name} sem data.yaml — ignorando")
                continue
            yaml_file = candidates[0]
            ds_dir = yaml_file.parent  # ajusta base para a subpasta

        with open(yaml_file) as f:
            ds_cfg = yaml.safe_load(f)
        ds_classes = [c.lower() for c in ds_cfg.get("names", [])]

        print(f"  Mesclando: {ds_dir.name} ({len(ds_classes)} classes)")

        for split in ["train", "valid", "test"]:
            img_dir = ds_dir / split / "images"
            lbl_dir = ds_dir / split / "labels"
            if not img_dir.exists():
                continue

            for img_path in img_dir.glob("*.*"):
                lbl_path = lbl_dir / (img_path.stem + ".txt")
                if not lbl_path.exists():
                    continue

                # Remap labels
                new_lines = []
                with open(lbl_path) as f:
                    for line in f:
                        parts = line.strip().split()
                        if not parts:
                            continue
                        old_id = int(parts[0])
                        if old_id >= len(ds_classes):
                            continue
                        old_cls = ds_classes[old_id]
                        # Normaliza pelo mapeamento
                        mapped = CLASS_REMAP.get(old_cls, "")
                        if mapped is None:
                            continue  # classe explicitamente ignorada (person, glove, etc.)
                        new_cls = mapped.lower() if mapped else old_cls
                        new_id = class_to_id.get(new_cls)
                        if new_id is None:
                            continue  # classe não relevante para o projeto
                        new_lines.append(f"{new_id} " + " ".join(parts[1:]))

                if not new_lines:
                    continue

                # Copia imagem
                dest_img = merged_dir / split / "images" / img_path.name
                shutil.copy2(img_path, dest_img)

                # Escreve labels remapeados
                dest_lbl = merged_dir / split / "labels" / lbl_path.name
                with open(dest_lbl, "w") as f:
                    f.write("\n".join(new_lines))

                img_count[split] += 1

    # Cria data.yaml do dataset consolidado
    yaml_content = {
        "path":  str(merged_dir),
        "train": "train/images",
        "val":   "valid/images",
        "test":  "test/images",
        "nc":    len(all_classes),
        "names": all_classes,
    }
    with open(merged_dir / "data.yaml", "w") as f:
        yaml.dump(yaml_content, f, allow_unicode=True)

    print(f"\n  Dataset mesclado:")
    for split, cnt in img_count.items():
        print(f"    {split}: {cnt} imagens")
    return str(merged_dir / "data.yaml")


def train(args):
    """Executa o treino YOLOv8."""
    from ultralytics import YOLO
    import torch

    # Verifica se existe dataset
    if not MERGED_YAML.exists():
        print("  Dataset mesclado nao encontrado. Mesclando agora...")
        yaml_path = merge_datasets()
    else:
        yaml_path = str(MERGED_YAML)

    # Modelo base: fine-tune a partir do best.pt existente
    base_model = MODELS_DIR / "best.pt"
    if base_model.exists() and not args.from_scratch:
        model_source = str(base_model)
        print(f"  Fine-tune a partir de: {model_source}")
    else:
        model_source = "yolov8n.pt"
        print(f"  Treino do zero com: {model_source}")

    model = YOLO(model_source)

    # Detecta device
    if torch.backends.mps.is_available():
        device = "mps"
    elif torch.cuda.is_available():
        device = "cuda"
    else:
        device = "cpu"
    print(f"  Device: {device.upper()}")

    # Configuração de treino
    train_cfg = {
        "data":        yaml_path,
        "epochs":      args.epochs,
        "batch":       args.batch,
        "imgsz":       640,
        "device":      device,
        "project":     str(RUNS_DIR / "train"),
        "name":        "tortuga_ppe",
        "exist_ok":    args.resume,
        "resume":      args.resume,
        "patience":    20,           # early stopping
        "save":        True,
        "val":         True,
        "plots":       True,
        # Augmentation industrial
        "hsv_h":       0.02,
        "hsv_s":       0.6,
        "hsv_v":       0.5,
        "degrees":     10.0,
        "translate":   0.1,
        "scale":       0.4,
        "flipud":      0.0,
        "fliplr":      0.5,
        "mosaic":      1.0,
        "mixup":       0.1,
    }

    print(f"\n  Iniciando treino: {args.epochs} epocas | batch {args.batch}\n")
    results = model.train(**train_cfg)

    # Copia best.pt para models/
    best_path = RUNS_DIR / "train" / "tortuga_ppe" / "weights" / "best.pt"
    if best_path.exists():
        # Faz backup do modelo anterior
        if base_model.exists():
            shutil.copy2(base_model, MODELS_DIR / "best.old.pt")
            print(f"  Backup do modelo anterior: models/best.old.pt")

        shutil.copy2(best_path, base_model)
        print(f"\n  Novo modelo salvo: models/best.pt")
        print(f"  Modelo antigo preservado: models/best.old.pt")
    else:
        print(f"\n  AVISO: best.pt nao encontrado em {best_path}")

    return results


def validate(args):
    """Valida o modelo atual no dataset de teste."""
    from ultralytics import YOLO

    model_path = MODELS_DIR / "best.pt"
    if not model_path.exists():
        print("  ERRO: models/best.pt nao encontrado.")
        return

    if not MERGED_YAML.exists():
        print("  ERRO: Dataset nao encontrado. Execute download_datasets.py primeiro.")
        return

    model   = YOLO(str(model_path))
    metrics = model.val(data=str(MERGED_YAML), split="test")

    print("\n  === Resultados da Validacao ===")
    print(f"  mAP@0.5      : {metrics.box.map50:.3f}  (meta: >= 0.75)")
    print(f"  mAP@0.5:0.95 : {metrics.box.map:.3f}")
    print(f"  Precision    : {metrics.box.mp:.3f}   (meta: >= 0.80)")
    print(f"  Recall       : {metrics.box.mr:.3f}   (meta: >= 0.80)")


def main():
    parser = argparse.ArgumentParser(description="Tortuga — Treino YOLOv8 EPIs")
    parser.add_argument("--epochs",       type=int,  default=100,  help="Numero de epocas")
    parser.add_argument("--batch",        type=int,  default=16,   help="Tamanho do batch")
    parser.add_argument("--resume",       action="store_true",     help="Continuar treino")
    parser.add_argument("--from-scratch", action="store_true",     help="Treinar sem fine-tune")
    parser.add_argument("--validate",     action="store_true",     help="Somente validar")
    parser.add_argument("--merge-only",   action="store_true",     help="Somente mesclar datasets")
    args = parser.parse_args()

    print("\n" + "="*60)
    print("  Tortuga — Treino de Modelo EPI (Fase 1)")
    print("="*60)

    if args.validate:
        validate(args)
    elif args.merge_only:
        merge_datasets()
    else:
        train(args)


if __name__ == "__main__":
    main()
