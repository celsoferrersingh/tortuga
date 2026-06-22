import csv as csvlib
from pathlib import Path

csv_path = Path('runs/train/tortuga_ppe/results.csv')
if not csv_path.exists():
    print('ERRO: results.csv nao encontrado em', csv_path)
else:
    rows = list(csvlib.DictReader(open(csv_path)))
    last = rows[-1]
    headers = {k.strip(): k for k in last.keys()}
    print(f'Epocas treinadas: {len(rows)}')
    print()
    for hstrip, horig in headers.items():
        hl = hstrip.lower()
        if any(k in hl for k in ['map', 'precision', 'recall']):
            try:
                print(f'  {hstrip:<35} {float(last[horig]):.4f}')
            except Exception:
                pass
