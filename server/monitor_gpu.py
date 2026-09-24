"""monitor_gpu.py — Monitor termico da GPU (somente leitura).

Mostra temperatura, clock, utilizacao e potencia em tempo real, e avisa quando
o clock cai por limite termico (throttling) — que e o que derruba o FPS.

NAO importa nada do Tortuga e NAO altera arquivo algum. Usa apenas o nvidia-smi.
Uso:  python monitor_gpu.py            (atualiza a cada 2 s; Ctrl+C encerra)
      python monitor_gpu.py --intervalo 1
"""
from __future__ import annotations
import argparse, subprocess, sys, time
from datetime import datetime

CAMPOS = ("temperature.gpu,clocks.current.graphics,clocks.max.graphics,"
          "utilization.gpu,power.draw,memory.used,memory.total,"
          "clocks_throttle_reasons.hw_thermal_slowdown,"
          "clocks_throttle_reasons.sw_thermal_slowdown")


def ler():
    try:
        out = subprocess.run(
            ["nvidia-smi", f"--query-gpu={CAMPOS}", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=5)
        if out.returncode != 0 or not out.stdout.strip():
            return None
        v = [x.strip() for x in out.stdout.strip().splitlines()[0].split(",")]
        return {"temp": float(v[0]), "clk": float(v[1]), "clk_max": float(v[2]),
                "uso": float(v[3]), "pot": float(v[4]),
                "mem": float(v[5]), "mem_tot": float(v[6]),
                "thr_hw": v[7].lower().startswith("active"),
                "thr_sw": v[8].lower().startswith("active")}
    except FileNotFoundError:
        print("\n  [ERRO] nvidia-smi nao encontrado. Driver NVIDIA instalado?\n"); sys.exit(1)
    except Exception:
        return None


def barra(pct, largura=22):
    n = max(0, min(largura, int(round(pct / 100 * largura))))
    return "#" * n + "." * (largura - n)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--intervalo", type=float, default=2.0)
    a = ap.parse_args()

    print("\n" + "=" * 68)
    print("  MONITOR TERMICO DA GPU — Projeto Tortuga (somente leitura)")
    print("=" * 68)
    print("  Ctrl+C encerra.  Deixe rodando enquanto o Tortuga opera.\n")
    tmin, tmax, n = 999.0, 0.0, 0
    try:
        while True:
            d = ler()
            if not d:
                print("  aguardando leitura da GPU..."); time.sleep(a.intervalo); continue
            n += 1
            tmin = min(tmin, d["temp"]); tmax = max(tmax, d["temp"])
            queda = (1 - d["clk"] / d["clk_max"]) * 100 if d["clk_max"] else 0.0

            if d["thr_hw"] or d["thr_sw"] or (d["temp"] >= 87):
                status = "!! THROTTLING TERMICO — o FPS vai cair"
            elif d["temp"] >= 80:
                status = ">> ATENCAO — perto do limite, melhore a ventilacao"
            elif d["temp"] >= 70:
                status = " - morno, ainda seguro"
            else:
                status = " OK — temperatura confortavel"

            print(f"\n  {datetime.now().strftime('%H:%M:%S')}   {status}")
            print(f"    Temperatura : {d['temp']:5.1f} C     (min {tmin:.0f} / max {tmax:.0f})")
            print(f"    Clock       : {d['clk']:5.0f} MHz   de {d['clk_max']:.0f} max"
                  + (f"   -> {queda:.0f}% abaixo do maximo" if queda > 15 else ""))
            print(f"    Utilizacao  : {d['uso']:5.0f} %     [{barra(d['uso'])}]")
            print(f"    Potencia    : {d['pot']:5.1f} W")
            print(f"    Memoria     : {d['mem']:5.0f} / {d['mem_tot']:.0f} MB")
            time.sleep(a.intervalo)
    except KeyboardInterrupt:
        print("\n" + "=" * 68)
        print(f"  Encerrado.  {n} leituras  ·  temperatura min {tmin:.0f} C / max {tmax:.0f} C")
        if tmax >= 87:
            print("  >> Houve throttling. Melhore a ventilacao antes de apresentar.")
        elif tmax >= 80:
            print("  >> Chegou perto do limite. Com cooler pad deve ficar folgado.")
        else:
            print("  >> Faixa segura. Pode apresentar tranquilo.")
        print("=" * 68 + "\n")


if __name__ == "__main__":
    main()
