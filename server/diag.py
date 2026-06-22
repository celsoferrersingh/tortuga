import cv2
from ultralytics import YOLO

m = YOLO('models/best.pt')
cap = cv2.VideoCapture(0)
ret, frame = cap.read()
cap.release()

if ret:
    results = m(frame, conf=0.05, verbose=False)
    dets = []
    for r in results:
        for i in range(len(r.boxes)):
            name = m.names[int(r.boxes.cls[i])]
            conf = float(r.boxes.conf[i])
            dets.append((conf, name))
    dets.sort(reverse=True)
    print(f"\n{len(dets)} deteccoes (threshold 5%):\n")
    for conf, name in dets:
        print(f"  {conf:.3f}  {name}")
else:
    print("Webcam nao abriu")
