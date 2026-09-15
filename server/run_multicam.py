"""
run_multicam.py — Multiplos pontos de visao (Fase 4) · Projeto Tortuga
Sobe uma instancia por camera (gui.py com janela ou headless.py para IP), cada
uma com seu station_id, todas no mesmo dashboard. Config: tortuga.config.json.
Uso: python run_multicam.py [--config X] [--dry-run]
"""
from __future__ import annotations
import argparse, json, os, signal, subprocess, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))


def load_config(path):
    if path is None:
        for cand in ("tortuga.config.json", "tortuga.config.example.json"):
            p = os.path.join(HERE, cand)
            if os.path.exists(p):
                path = p; break
    if not path or not os.path.exists(path):
        sys.exit("Config nao encontrada. Copie tortuga.config.example.json para tortuga.config.json.")
    with open(path, "r", encoding="utf-8") as f:
        cfg = json.load(f)
    print(f"  Config: {path}")
    return cfg


def build_cmd(cam, cfg):
    d = cfg.get("defaults", {})
    g = lambda k, dv=None: cam.get(k, d.get(k, dv))
    model = cfg.get("model", os.path.join("models", "best.pt"))
    if not os.path.isabs(model):
        model = os.path.join(HERE, model)
    headless = bool(g("headless", False))
    script = "headless.py" if headless else "gui.py"
    argv = [sys.executable, os.path.join(HERE, script),
            "--camera", str(cam["source"]),
            "--model", model,
            "--confidence", str(g("confidence", 0.40)),
            "--det-size", str(g("det_size", 640)),
            "--station-id", str(cam.get("station_id", "")),
            "--dashboard", cfg.get("dashboard", "http://localhost:5005")]
    pre = g("preprocess", False)
    if isinstance(pre, dict):
        argv += ["--preprocess-opts", json.dumps(pre)]
    elif pre:
        argv += ["--preprocess"]
    if g("fusion", False):
        argv += ["--fusion"]
    dev = cfg.get("device")
    if dev and dev != "auto":
        argv += ["--device", str(dev)]
    if not headless:
        if g("ingest", True):
            argv += ["--ingest"]
        if not g("pose", True):
            argv += ["--no-pose"]
    # A zona de exclusao de maquina vale para os DOIS modos (gui.py e headless.py).
    ig = cam.get("ignore")
    if ig:
        argv += ["--ignore", json.dumps(ig)]
    return argv


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default=None)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    cfg = load_config(a.config)
    cams = cfg.get("cameras", [])
    if not cams:
        sys.exit("Nenhuma camera na config.")
    print(f"  {len(cams)} ponto(s) de visao:")
    cmds = []
    for c in cams:
        cmd = build_cmd(c, cfg); cmds.append((c, cmd))
        _d = cfg.get("defaults", {})
        mode = "headless" if c.get("headless", _d.get("headless", False)) else "gui"
        print(f"   - {c.get('station_id','?'):8} [{mode:8}] {c.get('name','')}")
        if a.dry_run:
            print("     " + " ".join(cmd))
    if a.dry_run:
        return
    procs = []
    try:
        for c, cmd in cmds:
            procs.append(subprocess.Popen(cmd)); time.sleep(2.0)
        print("\n  Todas as estacoes no ar. Ctrl+C encerra todas.\n")
        while True:
            time.sleep(1.0)
            if all(p.poll() is not None for p in procs):
                print("  Todas as estacoes encerraram."); break
    except KeyboardInterrupt:
        print("\n  Encerrando estacoes...")
    finally:
        for p in procs:
            if p.poll() is None:
                try: p.send_signal(signal.SIGTERM)
                except Exception: pass
        time.sleep(1.0)
        for p in procs:
            if p.poll() is None:
                try: p.kill()
                except Exception: pass


if __name__ == "__main__":
    main()
