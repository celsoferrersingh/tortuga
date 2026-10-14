"""
set_cams.py — Grava usuario/senha (e o caminho do stream) nas cameras de uma config.

Existe porque a senha das cameras muda de local para local: a metaindustria tinha
dois lotes com senhas diferentes, e as cameras do auditorio da FIAP / da arena sao
de outro parque. Em vez de editar JSON na hora da apresentacao, o lancador pergunta
e este script regrava as URLs.

Uso:
    python set_cams.py --config tortuga.config.fiap.json --user admin --pass "SENHA"
    python set_cams.py --config tortuga.config.fiap.json --user admin --pass "X" \\
                       --path "/Streaming/Channels/102"      # caminho Hikvision
    python set_cams.py --config tortuga.config.fiap.json --listar
"""
from __future__ import annotations
import argparse, json, os, re, sys
from urllib.parse import quote

HERE = os.path.dirname(os.path.abspath(__file__))
RX = re.compile(r"^rtsp://(?:[^@/]*@)?(?P<host>[^/:]+)(?::(?P<porta>\d+))?(?P<path>/.*)?$")


def resolver(nome):
    caminho = nome if os.path.isabs(nome) else os.path.join(HERE, nome)
    if not os.path.exists(caminho):
        sys.exit(f"  [ERRO] config nao encontrada: {caminho}")
    return caminho


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="tortuga.config.json")
    ap.add_argument("--user", default=None)
    ap.add_argument("--password", "--pass", dest="password", default=None)
    ap.add_argument("--path", default=None,
                    help="caminho do stream (padrao: mantem o que ja esta na config)")
    ap.add_argument("--porta", default=None)
    ap.add_argument("--listar", action="store_true", help="so mostra as cameras")
    a = ap.parse_args()

    arq = resolver(a.config)
    cfg = json.load(open(arq, encoding="utf-8"))
    cams = cfg.get("cameras", [])
    if not cams:
        sys.exit("  [ERRO] nenhuma camera nesta config.")

    def mostrar(titulo):
        print(f"\n  {titulo}")
        for c in cams:
            u = c.get("source", "")
            # nunca imprime a senha
            seguro = re.sub(r"//[^@/]*@", "//***:***@", u)
            print(f"   {c.get('station_id','?'):<12} {c.get('name',''):<10} {seguro}")

    if a.listar or (a.user is None and a.password is None and a.path is None):
        mostrar(f"Cameras em {os.path.basename(arq)}:")
        print("\n  Para gravar credenciais:")
        print(f'   python set_cams.py --config {a.config} --user admin --pass "SENHA"')
        return 0

    if a.password is None:
        sys.exit("  [ERRO] informe --pass \"SENHA\" (use aspas se tiver caracteres especiais).")
    user = a.user or "admin"
    pw = quote(a.password, safe="")        # codifica !@#$ etc. para caber na URL

    n = 0
    for c in cams:
        m = RX.match(c.get("source", ""))
        if not m:
            print(f"   [pulado] {c.get('station_id','?')}: URL em formato inesperado")
            continue
        host = m.group("host")
        porta = a.porta or m.group("porta") or "554"
        path = a.path or m.group("path") or "/cam/realmonitor?channel=1&subtype=1"
        c["source"] = f"rtsp://{user}:{pw}@{host}:{porta}{path}"
        n += 1

    json.dump(cfg, open(arq, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(f"\n  OK: credenciais gravadas em {n} camera(s) de {os.path.basename(arq)}.")
    mostrar("Resultado (senha ocultada):")
    print("\n  Agora teste se entregam frame:")
    print(f"   python diag_rtsp.py --config {a.config}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
