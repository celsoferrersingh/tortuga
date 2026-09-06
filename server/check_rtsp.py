"""
check_rtsp.py — Teste DECISIVO de RTSP. Descobre se a maquina realmente alcanca
a camera (teste de rede puro na porta 554) e compara com a webcam local, pra
saber se um "frame 640x480" veio da CAMERA REAL ou de outra fonte.
"""
import json, os, re, socket, sys

HERE = os.path.dirname(os.path.abspath(__file__))
cfg = json.load(open(os.path.join(HERE, "tortuga.config.json"), encoding="utf-8"))
cam = cfg["cameras"][0]
url = cam["source"]
print("=" * 60)
print("  TESTE DECISIVO DE RTSP")
print("=" * 60)
print(f"  Camera: {cam.get('station_id')}  ->  {url}\n")

m = re.search(r"@([^/:]+):?(\d+)?", url) or re.search(r"://([^/:]+):?(\d+)?", url)
host = m.group(1)
port = int(m.group(2) or 554)

print(f"  [1] Rede: tentando conectar em {host}:{port} (timeout 4s)...")
reachable = False
try:
    s = socket.create_connection((host, port), timeout=4)
    s.close()
    reachable = True
    print(f"      >> ACESSIVEL. A porta {port} de {host} respondeu.")
    print(f"         Ou seja: esta maquina ESTA na rede das cameras (ou via VPN).")
except Exception as e:
    print(f"      >> INACESSIVEL. {host}:{port} nao respondeu ({e.__class__.__name__}).")
    print(f"         Ou seja: esta maquina NAO alcanca a camera daqui.")

try:
    import cv2
    os.environ.setdefault("OPENCV_FFMPEG_CAPTURE_OPTIONS", "rtsp_transport;tcp|stimeout;4000000")
    print("\n  [2] Abrindo o RTSP com FFMPEG...")
    cap = cv2.VideoCapture(url, cv2.CAP_FFMPEG)
    ok = cap.isOpened(); fr = None
    if ok:
        ok, fr = cap.read()
    cap.release()
    if ok and fr is not None:
        import numpy as np
        print(f"      >> RTSP OK — frame {fr.shape[1]}x{fr.shape[0]}, brilho medio {float(np.mean(fr)):.0f}/255")
    else:
        print("      >> RTSP FALHOU — nao entregou frame.")

    print("\n  [3] Webcam local (indice 0), so p/ comparar...")
    cap = cv2.VideoCapture(0)
    ok2 = cap.isOpened(); fr2 = None
    if ok2:
        ok2, fr2 = cap.read()
    cap.release()
    if ok2 and fr2 is not None:
        print(f"      >> Webcam local existe — frame {fr2.shape[1]}x{fr2.shape[0]}")
    else:
        print("      >> Sem webcam local acessivel.")
except Exception as e:
    print("      erro no OpenCV:", e)

print("\n" + "=" * 60)
print("  CONCLUSAO:")
if reachable:
    print("  Voce ESTA na rede das cameras -> o RTSP conecta de verdade. Otimo.")
else:
    print("  Voce NAO esta na rede das cameras. Se o passo [2] deu OK mesmo")
    print("  assim, o frame veio de OUTRA fonte (ex.: webcam), nao da camera real.")
print("=" * 60)
