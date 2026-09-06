"""clear_zones.py — Remove todas as zonas de risco (para demo em ambiente
diferente do da Prensa). Depois reinicie o run_demo para ele recarregar."""
from __future__ import annotations
import os, sys
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
from events_store import EventStore

db = os.path.join(HERE, "data", "tortuga.db")
s = EventStore(db)
zs = s.list_zones()
for z in zs:
    s.delete_zone(z["id"])
s.close()
print("Removidas %d zona(s) de risco." % len(zs))
print("Reinicie o run_demo.bat para o app recarregar sem zonas.")
