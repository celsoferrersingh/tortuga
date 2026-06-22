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
    # Estatisticas para o relatorio pre-voo (evita re-treino quebrado):
    #   class_inst  -> nº de instancias (boxes) por classe alvo no train
    #   src_coverage-> quais classes alvo cada dataset realmente anota
    class_inst = {c: 0 for c in all_classes}
    src_coverage: dict[str, set] = {}

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
                        # Estatisticas (somente split de treino)
                        if split == "train":
                            class_inst[all_classes[new_id]] += 1
                        src_coverage.setdefault(ds_dir.name, set()).add(all_classes[new_id])

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

    # ── Relatorio pre-voo: distribuicao de classes + contaminacao ──
    _preflight_report(class_inst, src_coverage)
    return str(merged_dir / "data.yaml")


# Minimo de instancias por classe alvo para um treino saudavel.
MIN_INSTANCES = 150


def _preflight_report(class_inst: dict, src_coverage: dict) -> list:
    """
    Imprime a distribuicao de instancias por classe e detecta os dois
    erros que destruiram o re-treino anterior:
      1. Classe alvo com 0 instancias (ex.: Protetor Auricular) — o modelo
         declara a classe mas nunca aprende a detecta-la.
      2. Contaminacao por anotacao parcial — datasets que NAO anotam uma
         classe ensinam o modelo que aquele objeto e 'fundo', degradando
         TODAS as classes. Sinalizado quando ha datasets com coberturas
         muito diferentes.
    Retorna a lista de classes problematicas (0 ou < MIN_INSTANCES).
    """
    print("\n  " + "=" * 56)
    print("  RELATORIO PRE-VOO — distribuicao de classes (treino)")
    print("  " + "=" * 56)
    total = sum(class_inst.values()) or 1
    problems, zeros = [], []
    for cls, n in class_inst.items():
        pct = 100.0 * n / total
        flag = ""
        if n == 0:
            flag = "  <<< ZERO — classe nunca sera detectada!"
            zeros.append(cls)
        elif n < MIN_INSTANCES:
            flag = f"  <<< POUCAS amostras (< {MIN_INSTANCES})"
            problems.append(cls)
        print(f"    {cls:<20} {n:>7}  ({pct:4.1f}%){flag}")

    # Contaminacao por anotacao parcial
    print("\n  Cobertura por dataset (classes que cada fonte realmente anota):")
    for name, classes in sorted(src_coverage.items()):
        print(f"    {name:<22} -> {sorted(classes)}")
    if len(src_coverage) > 1:
        union = set().union(*src_coverage.values()) if src_coverage else set()
        partial = [n for n, c in src_coverage.items() if len(c) < len(union) * 0.6]
        if partial:
            print("\n  [ALERTA] Anotacao parcial detectada nas fontes:")
            print(f"           {partial}")
            print("           Datasets que anotam poucas das classes injetam")
            print("           'positivos nao rotulados' e degradam o modelo inteiro.")
            print("           Prefira UM dataset completo (ex.: SH17) ou rotule")
            print("           todas as classes presentes em cada imagem.")

    if zeros:
        print("\n  [ERRO] Classes com ZERO instancias:", zeros)
        print("         Treinar assim repete a regressao anterior. Baixe um")
        print("         dataset que contenha essas classes antes de treinar.")
    print("  " + "=" * 56 + "\n")
    return zeros   # somente classes fatais (0 instancias)


def analyze_existing(yaml_path: str) -> list:
    """Le os labels de um dataset merged ja existente e roda o relatorio."""
    with open(yaml_path) as f:
        cfg = yaml.safe_load(f)
    names = cfg["names"]
    base = Path(cfg.get("path", Path(yaml_path).parent))
    lbl_dir = base / "train" / "labels"
    class_inst = {c: 0 for c in names}
    if lbl_dir.exists():
        for txt in lbl_dir.glob("*.txt"):
            for line in txt.read_text().splitlines():
                p = line.split()
                if p:
                    cid = int(p[0])
                    if 0 <= cid < len(names):
                        class_inst[names[cid]] += 1
    return _preflight_report(class_inst, {})


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

    # ── Guarda pre-voo: nao treinar com classes vazias (sem --force) ──
    zeros = analyze_existing(yaml_path)
    if zeros and not args.force:
        print("  [ABORTADO] Ha classes com ZERO instancias:", zeros)
        print("  Corrija o dataset (baixe fontes com essas classes) ou use")
        print("  --force para treinar mesmo assim (NAO recomendado).")
        return

    # Modelo base para fine-tune.
    # OBS: models/best.pt agora e o modelo de OCULOS (2 classes) restaurado para
    # a demo. NAO serve de base para o detector de 12 classes. Usamos os pesos
    # de 12 classes preservados (best_merged12.pt) como warm start; se nao
    # existirem, treina limpo a partir do COCO (yolov8s.pt).
    base_model = MODELS_DIR / "best_merged12.pt"
    if base_model.exists() and not args.from_scratch:
        model_source = str(base_model)
        print(f"  Fine-tune a partir de (12 classes): {model_source}")
    else:
        model_source = f"{args.model}.pt"
        print(f"  Treino limpo (COCO) com: {model_source}")

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
        "patience":    25,
        "save":        True,
        "val":         True,
        "plots":       True,
        # Augmentação ampla — generaliza para ambientes variados (sala de aula,
        # escritório, canteiro de obra, etc.)
        "hsv_h":       0.02,
        "hsv_s":       0.7,    # mais variação de saturação
        "hsv_v":       0.7,    # mais variação de brilho/escuridão
        "degrees":     12.0,
        "translate":   0.15,
        "scale":       0.5,
        "flipud":      0.0,
        "fliplr":      0.5,
        "mosaic":      1.0,
        "mixup":       0.15,
        "copy_paste":  0.1,    # copia objetos entre imagens — diversifica contexto
        "erasing":     0.4,    # oclusão aleatória — robustez a objetos parciais
        "auto_augment":"randaugment",  # augmentação automática variada
    }

    print(f"\n  Iniciando treino: {args.epochs} epocas | batch {args.batch}\n")
    results = model.train(**train_cfg)

    # Localiza o best.pt produzido pelo treino (usa save_dir real do run).
    try:
        best_path = Path(results.save_dir) / "weights" / "best.pt"
    except Exception:
        best_path = RUNS_DIR / "train" / "tortuga_ppe" / "weights" / "best.pt"

    if best_path.exists():
        # NAO sobrescreve best.pt/best.old.pt automaticamente — foi o que
        # causou a regressao silenciosa antes. Salva em STAGING e instrui a
        # validar antes de promover para producao.
        staged = MODELS_DIR / "best_retrained.pt"
        shutil.copy2(best_path, staged)
        print(f"\n  Modelo treinado salvo em STAGING: {staged}")
        print("\n  PROXIMOS PASSOS (nao pular):")
        print("   1) Validar:  python train_model.py --validate")
        print("   2) Testar ao vivo:  python gui.py --model models/best_retrained.pt")
        print("   3) So se passar nas metas e detectar bem na sala, promover:")
        print("        copie best_retrained.pt -> best.pt")
        print("      (detector usa o modo SINGLE 12-classes quando best.pt tem >4 classes)")
    else:
        print(f"\n  AVISO: best.pt nao encontrado em {best_path}")

    return results


def validate(args):
    """Valida o modelo atual no dataset de teste."""
    from ultralytics import YOLO

    # Valida o modelo em staging (recem-treinado) se existir; senao best.pt.
    model_path = MODELS_DIR / "best_retrained.pt"
    if not model_path.exists():
        model_path = MODELS_DIR / "best.pt"
    if not model_path.exists():
        print("  ERRO: nenhum modelo encontrado em models/.")
        return
    print(f"  Validando: {model_path.name}")

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
    parser.add_argument("--epochs",       type=int,   default=150,      help="Numero de epocas")
    parser.add_argument("--batch",        type=int,   default=16,       help="Tamanho do batch")
    parser.add_argument("--model",        type=str,   default="yolov8s", help="Modelo base (yolov8n/s/m)")
    parser.add_argument("--resume",       action="store_true",           help="Continuar treino")
    parser.add_argument("--from-scratch", action="store_true",           help="Treinar sem fine-tune")
    parser.add_argument("--validate",     action="store_true",           help="Somente validar")
    parser.add_argument("--merge-only",   action="store_true",           help="Somente mesclar datasets")
    parser.add_argument("--analyze",      action="store_true",           help="Relatorio de classes do dataset merged (sem treinar)")
    parser.add_argument("--force",        action="store_true",           help="Treinar mesmo com classes vazias (NAO recomendado)")
    args = parser.parse_args()

    print("\n" + "="*60)
    print("  Tortuga — Treino de Modelo EPI (Fase 1)")
    print("="*60)

    if args.analyze:
        if MERGED_YAML.exists():
            analyze_existing(str(MERGED_YAML))
        else:
            print("  Dataset merged nao existe. Rode --merge-only primeiro.")
    elif args.validate:
        validate(args)
    elif args.merge_only:
        merge_datasets()
    else:
        train(args)


if __name__ == "__main__":
    main()
