"""
find_esp.py — Descobre o IP do cinto ESP32 na rede local (sem Arduino IDE).
Varre a sub-rede do PC e procura quem responde como Tortuga na porta 80.
Uso: python find_esp.py
"""
import socket, ipaddress, urllib.request, concurrent.futures


def local_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("10.255.255.255", 1)); ip = s.getsockname()[0]
    except Exception:
        ip = "192.168.0.1"
    finally:
        s.close()
    return ip


def probe(ip):
    try:
        with urllib.request.urlopen("http://%s/" % ip, timeout=0.7) as r:
            body = r.read(300).decode("utf-8", "ignore")
            if "Tortuga" in body or "ESP32" in body:
                return ip
    except Exception:
        pass
    return None


def main():
    ip = local_ip()
    net = ipaddress.ip_network(ip + "/24", strict=False)
    print("  PC nesta rede: %s" % ip)
    print("  Varrendo %s (aguarde ~5-15s)...\n" % net)
    found = []
    hosts = [str(h) for h in net.hosts()]
    with concurrent.futures.ThreadPoolExecutor(max_workers=128) as ex:
        for res in ex.map(probe, hosts):
            if res:
                found.append(res)
    if found:
        for f in found:
            print("  >> CINTO ENCONTRADO:  %s" % f)
        print("\n  Use este IP no set_esp_metaindustria.bat.")
    else:
        print("  Nenhum cinto encontrado nesta sub-rede.")
        print("  Verifique: a telinha do cinto NAO pode estar em 'Config WiFi'")
        print("  (se estiver, conecte o celular na rede Tortuga-Setup e configure a WiFi de la).")
        print("  Se o cinto estiver em outra sub-rede, use o Serial Monitor para ver o IP.")


if __name__ == "__main__":
    main()
