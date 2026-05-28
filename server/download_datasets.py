"""
download_datasets.py — Fase 1 (lacunas): Protetor Auricular + Bota de Segurança
Challenge SPI 2026

Este script baixa datasets públicos do Roboflow Universe para complementar
o modelo de detecção de EPIs com as classes que ainda faltam:
  - Protetor auricular (ear protection / hearing protection)
  - Bota de segurança (safety boots / safety shoes)

USO:
  pip install roboflow
  python download_datasets.py

Os datasets são baixados em server/datasets/ prontos para retreino.
Após o download, use train_model.py para retreinar o YOLOv8.
"""

import os, sys
from pathlib import Path

# ─── Datasets públicos escolhidos ────────────────────────────
# Fonte: Roboflow Universe — licença permissiva (CC BY 4.0 / MIT)
# Todos incluem as classes que precisamos.

DATASETS = [
    {
        "name": "ppe-complete-v3",
        "workspace": "construction-safety-gsnvb",
        "project": "construction-site-safety",
        "version": 30,
        "classes_interest": ["Hardhat", "Safety Vest", "Gloves", "Mask",
                              "Safety Glasses", "Ear Protection", "Safety Boots"],
        "description": "Dataset abrangente de EPIs em obras — 10+ classes",
    },
    {
        "name": "hearing-protection",
        "workspace": "roboflow-universe-projects",
        "project": "hearing-protection-detection",
        "version": 1,
        "classes_interest": ["ear_protection", "no_ear_protection"],
        "description": "Dataset específico para protetor auricular",
    },
    {
        "name": "safety-boots-ppe",
        "workspace": "roboflow-universe-projects",
        "project": "safety-shoes-detection",
        "version": 2,
        "classes_interest": ["safety_boots", "no_safety_boots", "regular_shoes"],
        "description": "Dataset específico para botas de segurança",
    },
]

# ─── Mapeamento de classes para nomes padrão do Tortuga ───────
CLASS_REMAP = {
    # Protetor auricular — todas as variações encontradas nos datasets
    "ear protection":     "Ear Protection",
    "ear_protection":     "Ear Protection",
    "ear-protection":     "Ear Protection",   # SiaBar usa hífen
    "hearing protection": "Ear Protection",
    "earmuff":            "Ear Protection",
    "earmuffs":           "Ear Protection",
    "no ear protection":  "NO-Ear Protection",
    "no_ear_protection":  "NO-Ear Protection",
    "no-ear-protection":  "NO-Ear Protection",
    # Bota
    "safety boots":       "Safety Boots",
    "safety_boots":       "Safety Boots",
    "safety shoes":       "Safety Boots",
    "safety_shoes":       "Safety Boots",
    "boots":              "Safety Boots",
    "boot":               "Safety Boots",
    "no safety boots":    "NO-Safety Boots",
    "no_safety_boots":    "NO-Safety Boots",
    "regular shoes":      "NO-Safety Boots",
    "regular_shoes":      "NO-Safety Boots",
    # Capacete
    "hardhat":            "Hardhat",
    "hard hat":           "Hardhat",
    "helmet":             "Hardhat",
    "hard-hat":           "Hardhat",
    "no hardhat":         "NO-Hardhat",
    "no-hardhat":         "NO-Hardhat",
    "no helmet":          "NO-Hardhat",
    # Colete
    "safety vest":        "Safety Vest",
    "vest":               "Safety Vest",
    "hi-vis":             "Safety Vest",
    "hivis":              "Safety Vest",
    "no safety vest":     "NO-Safety Vest",
    "no-safety vest":     "NO-Safety Vest",
    "no vest":            "NO-Safety Vest",
    # Óculos
    "safety glasses":     "Safety Glasses",
    "glasses":            "Safety Glasses",
    "glass":              "Safety Glasses",   # SiaBar usa singular
    "goggles":            "Safety Glasses",
    "no glasses":         "NO-Safety Glasses",
    "no_glasses":         "NO-Safety Glasses",
    "no safety glasses":  "NO-Safety Glasses",
    # Máscara
    "mask":               "Mask",
    "face mask":          "Mask",
    "respirator":         "Mask",
    "no mask":            "NO-Mask",
    "no-mask":            "NO-Mask",
    # Classes a ignorar (não são EPIs do projeto)
    "person":             None,
    "glove":              None,
    "gloves":             None,
    "worker":             None,
    "human":              None,
}

OUTPUT_DIR = Path(__file__).parent / "datasets"


def check_roboflow():
    try:
        import roboflow
        return True
    except ImportError:
        print("\n  ERRO: roboflow nao instalado.")
        print("  Execute: pip install roboflow")
        return False


def download_dataset(entry: dict, api_key: str):
    from roboflow import Roboflow
    rf = Roboflow(api_key=api_key)

    print(f"\n  Baixando: {entry['name']}")
    print(f"  {entry['description']}")

    try:
        project  = rf.workspace(entry["workspace"]).project(entry["project"])
        version  = project.version(entry["version"])
        dataset  = version.download("yolov8", location=str(OUTPUT_DIR / entry["name"]))
        print(f"  OK: {OUTPUT_DIR / entry['name']}")
        return dataset.location
    except Exception as e:
        print(f"  AVISO: Falha ao baixar {entry['name']}: {e}")
        print(f"  Baixe manualmente em: https://universe.roboflow.com/{entry['workspace']}/{entry['project']}")
        return None


def list_manual_alternatives():
    """
    Imprime links para download manual caso não tenha API key.
    """
    print("\n" + "="*60)
    print("  DATASETS RECOMENDADOS — Download Manual")
    print("="*60)
    alternatives = [
        {
            "nome":  "Construction Site Safety (10 classes)",
            "url":   "https://universe.roboflow.com/roboflow-universe-projects/construction-site-safety-g9e2g",
            "obs":   "Inclui capacete, colete, luva, oculos, mascara",
        },
        {
            "nome":  "PPE Detection v8 (12 classes)",
            "url":   "https://universe.roboflow.com/university-of-queensland-uas/ppe-uqmcr",
            "obs":   "Inclui protetor auricular e bota",
        },
        {
            "nome":  "Safety Helmet and Vest Dataset",
            "url":   "https://universe.roboflow.com/new-workspace-2vbzj/safety-helmet-and-vest-uovsd",
            "obs":   "Boa diversidade de cenarios industriais",
        },
        {
            "nome":  "Hard Hat Workers (Kaggle)",
            "url":   "https://www.kaggle.com/datasets/andrewmvd/hard-hat-detection",
            "obs":   "2000+ imagens rotuladas, formato PASCAL VOC",
        },
        {
            "nome":  "SH17 Dataset (17 EPIs)",
            "url":   "https://github.com/SafetyHelmet/SH17",
            "obs":   "17 classes de EPIs incluindo protetor auricular e bota",
        },
    ]

    for a in alternatives:
        print(f"\n  [{a['nome']}]")
        print(f"  {a['url']}")
        print(f"  Obs: {a['obs']}")

    print("\n" + "="*60)
    print("  INSTRUCOES DE USO MANUAL:")
    print("  1. Baixe o dataset em formato YOLOv8")
    print("  2. Coloque em server/datasets/<nome>/")
    print("  3. Execute: python train_model.py --dataset <nome>")
    print("="*60 + "\n")


def main():
    print("\n" + "="*60)
    print("  Tortuga — Download de Datasets para Fase 1 (lacunas)")
    print("="*60)

    if not check_roboflow():
        list_manual_alternatives()
        sys.exit(0)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    api_key = os.environ.get("ROBOFLOW_API_KEY", "")
    if not api_key:
        print("\n  AVISO: ROBOFLOW_API_KEY nao definida.")
        print("  Obtanha em: https://app.roboflow.com → Settings → API")
        print("\n  Exibindo alternativas de download manual...\n")
        list_manual_alternatives()
        return

    locations = []
    for entry in DATASETS:
        loc = download_dataset(entry, api_key)
        if loc:
            locations.append(loc)

    if locations:
        print(f"\n  {len(locations)} datasets baixados em: {OUTPUT_DIR}")
        print("  Proximo passo: python train_model.py")
    else:
        list_manual_alternatives()


if __name__ == "__main__":
    main()
