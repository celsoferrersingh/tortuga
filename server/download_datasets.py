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
        "name": "ppe-combined-44k",
        "workspace": "roboflow-universe-projects",
        "project": "personal-protective-equipment-combined-model",
        "version": 8,
        "classes_interest": ["Hardhat", "NO-Hardhat", "Safety Vest", "NO-Safety Vest",
                              "Mask", "NO-Mask", "Goggles", "NO-Goggles"],
        "description": "44k imagens PPE — grande diversidade de ambientes (obra, escritorio, industria)",
    },
    {
        "name": "safety-ppe-shoes",
        "workspace": "safety-jmser",
        "project": "safety_ppe",
        "version": 23,
        "classes_interest": ["Shoe", "No_Shoe", "Helmet", "No_Helmet", "Goggles", "No_Goggles"],
        "description": "6.6k imagens com Safety Boots (Shoe/No_Shoe) e capacete variado",
    },
    {
        # ATENCAO: este 'project/version' trouxe ANTES um dataset SEM protetor
        # auricular (veio Boots/Helmet/Person/Vest). verify_classes() agora
        # aborta esse caso. Confirme o slug correto no Roboflow Universe antes
        # de usar, ou troque por uma das fontes recomendadas abaixo.
        "name": "ear-protection",
        "workspace": "siabar",
        "project": "ppe-dataset-for-workplace-safety",
        "version": 1,
        "classes_interest": ["ear_protection", "no_ear_protection", "ear-protection",
                              "earmuff", "hearing protection"],
        "description": "FONTE DE PROTETOR AURICULAR — VERIFIQUE as classes! "
                       "Alternativas confiaveis: SH17 (17 EPIs, inclui ear "
                       "protection + boots) e datasets 'earmuff'/'hearing "
                       "protection' do Roboflow Universe.",
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
    "no_hardhat":         "NO-Hardhat",
    "no helmet":          "NO-Hardhat",
    "no_helmet":          "NO-Hardhat",   # safety_ppe dataset
    # Colete
    "safety vest":        "Safety Vest",
    "vest":               "Safety Vest",
    "hi-vis":             "Safety Vest",
    "hivis":              "Safety Vest",
    "no safety vest":     "NO-Safety Vest",
    "no-safety vest":     "NO-Safety Vest",
    "no_safety_vest":     "NO-Safety Vest",
    "no vest":            "NO-Safety Vest",
    # Óculos / Goggles
    "safety glasses":     "Safety Glasses",
    "glasses":            "Safety Glasses",
    "glass":              "Safety Glasses",   # SiaBar usa singular
    "goggles":            "Safety Glasses",   # PPE Combined usa goggles
    "goggle":             "Safety Glasses",
    "no glasses":         "NO-Safety Glasses",
    "no_glasses":         "NO-Safety Glasses",
    "no safety glasses":  "NO-Safety Glasses",
    "no_goggles":         "NO-Safety Glasses", # PPE Combined + safety_ppe
    "no-goggles":         "NO-Safety Glasses",
    "no goggles":         "NO-Safety Glasses",
    # Máscara
    "mask":               "Mask",
    "face mask":          "Mask",
    "respirator":         "Mask",
    "no mask":            "NO-Mask",
    "no-mask":            "NO-Mask",
    "no_mask":            "NO-Mask",
    # Bota — safety_ppe usa "shoe" / "no_shoe"
    "shoe":               "Safety Boots",
    "no_shoe":            "NO-Safety Boots",
    "no shoe":            "NO-Safety Boots",
    # Classes a ignorar
    "person":             None,
    "glove":              None,
    "gloves":             None,
    "no_glove":           None,
    "no glove":           None,
    "worker":             None,
    "human":              None,
    "ladder":             None,
    "safety cone":        None,
    "safety_cone":        None,
    "fall-detected":      None,
    "fall detected":      None,
    "safety_harness":     None,
    "safety harness":     None,
    "no_harness":         None,
    "no harness":         None,
    "no_breathingapparatus": None,
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


def verify_classes(location: str, entry: dict) -> None:
    """
    Confere se o dataset baixado REALMENTE contem as classes esperadas.
    Esta verificacao existe porque um download anterior trouxe o projeto
    errado: a pasta 'hearing-protection' veio com Boots/Helmet/Person/Vest
    (NENHUM protetor auricular), e isso so foi descoberto depois de 12h de
    treino. Agora o erro e detectado na hora do download.
    """
    import yaml as _yaml
    yfile = Path(location) / "data.yaml"
    if not yfile.exists():
        cands = list(Path(location).rglob("data.yaml"))
        if cands:
            yfile = cands[0]
    if not yfile.exists():
        print("  [AVISO] data.yaml nao encontrado — nao foi possivel verificar classes.")
        return
    got = [c.lower() for c in _yaml.safe_load(open(yfile)).get("names", [])]
    want = [c.lower() for c in entry.get("classes_interest", [])]
    matched = [w for w in want if any(w in g or g in w for g in got)]
    print(f"  Classes no dataset : {got}")
    if want and not matched:
        print("  " + "!" * 56)
        print(f"  [ERRO] NENHUMA classe esperada {want} foi encontrada!")
        print("         Este dataset NAO serve para o proposito declarado.")
        print("         NAO inclua no merge — baixe a fonte correta.")
        print("  " + "!" * 56)
    elif want:
        print(f"  [OK] Classes esperadas presentes: {matched}")


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
        verify_classes(dataset.location, entry)   # <<< pega download errado na hora
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
