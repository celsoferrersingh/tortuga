"""
set_mode.py — alterna o Tortuga entre dois modos, editando 'defaults.headless'
em tortuga.config.json. Nao mexe em mais nada (cameras, RTSP, device ficam iguais).

  COMPLETO : janela + Fase 1 (EPI) + Fase 2 (pose/ergonomia/queda) + Fase 3.  [PADRAO]
  LEVE     : headless (sem janela) — so Fase 1 (EPI) + Fase 3. Mais leve na GPU,
             usar so como valvula de escape se algo travar ao vivo.

Uso:  python set_mode.py completo | leve
Depois de trocar, (re)inicie run_metaindustria.bat.
"""
import json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
CFG = os.path.join(HERE, "tortuga.config.json")


def main():
    mode = (sys.argv[1].lower() if len(sys.argv) > 1 else "")
    if mode not in ("leve", "completo"):
        print("uso: python set_mode.py completo | leve")
        return 2
    if not os.path.exists(CFG):
        print(f"[ERRO] nao encontrei {CFG}")
        return 1

    with open(CFG, "r", encoding="utf-8") as f:
        cfg = json.load(f)
    cfg.setdefault("defaults", {})["headless"] = (mode == "leve")
    with open(CFG, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)

    n = len(cfg.get("cameras", []))
    if mode == "leve":
        print(f"\n  >> MODO LEVE ativado ({n} cameras em headless).")
        print("     Roda so Fase 1 (EPI) + Fase 3 (dashboard/cinto). Fase 2 (pose) PAUSADA.")
        print("     Use apenas como contingencia se a GPU travar ao vivo.")
    else:
        print(f"\n  >> MODO COMPLETO ativado ({n} cameras com janela).")
        print("     Fase 1 (EPI) + Fase 2 (pose/ergonomia/queda) + Fase 3. Sistema inteiro.")
    print("\n  Proximo passo: feche as cameras abertas e rode  run_metaindustria.bat\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
