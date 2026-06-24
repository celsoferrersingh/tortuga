"""seed_events.py — Dados sintéticos (Fase 3): perfis com EPIs/confiança,
cintos ESP32 atribuídos, zonas de risco e eventos Poisson por operador."""
from __future__ import annotations
import argparse, random
from datetime import datetime, timedelta
from events_store import EventStore

ROSTER = [
    ("OP-001","Operador 001","Solda","A",0.30,["Hardhat","Safety Vest","Safety Glasses","Mask"],0.45),
    ("OP-002","Operador 002","Montagem","A",0.18,["Hardhat","Safety Vest","Safety Glasses"],0.40),
    ("OP-003","Operador 003","Prensa","B",0.45,["Hardhat","Safety Vest","Safety Glasses","Ear Protection"],0.45),
    ("OP-004","Operador 004","Pintura","B",0.25,["Hardhat","Safety Vest","Mask","Ear Protection"],0.40),
    ("OP-005","Operador 005","Expedição","C",0.20,["Hardhat","Safety Vest","Safety Boots"],0.40),
    ("OP-006","Operador 006","Solda","C",0.35,["Hardhat","Safety Vest","Safety Glasses","Mask"],0.45),
    ("OP-007","Operador 007","Prensa","A",1.25,["Hardhat","Safety Vest","Safety Glasses","Ear Protection"],0.45),
    ("OP-008","Operador 008","Montagem","B",0.22,["Hardhat","Safety Vest","Safety Glasses"],0.40),
    ("OP-009","Operador 009","Pintura","C",0.90,["Hardhat","Safety Vest","Mask","Ear Protection"],0.40),
    ("OP-010","Operador 010","Expedição","A",0.28,["Hardhat","Safety Vest","Safety Boots"],0.40),
]
SHIFTS = 30
BELTS = [
    ("CINTO-PRE-01","Cinto Prensa 1","EST-PRE","OP-007"),
    ("CINTO-PIN-01","Cinto Pintura 1","EST-PIN","OP-009"),
    ("CINTO-SOL-01","Cinto Solda 1","EST-SOL","OP-001"),
    ("CINTO-EXP-01","Cinto Expedição 1","EST-EXP","OP-010"),
]
ZONES = [
    ("Prensa — área da matriz","critica","EST-PRE",[[0.55,0.30],[0.95,0.30],[0.95,0.92],[0.55,0.92]],["Hardhat","Ear Protection"]),
    ("Pintura — cabine de vapores","alta","EST-PIN",[[0.05,0.40],[0.45,0.40],[0.45,0.95],[0.05,0.95]],["Mask"]),
]
TYPE_WEIGHTS = [("EPI_AUSENTE","alta",0.55),("POSTURA_RISCO","alta",0.22),
    ("ZONA_CRITICA","critica",0.10),("FADIGA","informativa",0.10),("QUEDA","critica",0.03)]
EPIS = ["Capacete","Colete","Óculos","Protetor Auricular","Bota"]
TURNO_HORA = {"A":(6,14),"B":(14,22),"C":(22,30)}

def _pick_type():
    r = random.random(); acc = 0.0
    for t,sev,w in TYPE_WEIGHTS:
        acc += w
        if r <= acc: return t,sev
    return TYPE_WEIGHTS[0][0],TYPE_WEIGHTS[0][1]

def _ts(day_offset,turno):
    h0,h1 = TURNO_HORA[turno]
    base = datetime.now() - timedelta(days=day_offset)
    hour = random.randint(h0,h1-1)
    dt = base.replace(hour=hour%24,minute=random.randint(0,59),second=random.randint(0,59),microsecond=0)
    if hour >= 24: dt += timedelta(days=1)
    return dt.isoformat()

def _poisson(lam):
    import math
    L = math.exp(-lam); k = 0; p = 1.0
    while True:
        k += 1; p *= random.random()
        if p <= L: return k-1

def seed(store, force=False):
    if store.total_events() > 0 and not force:
        print("Já há eventos. Use --force para repopular."); return
    if force:
        for t in ("safety_events","workers","belts","zones","audit_chain","area_levels"):
            store._conn.execute("DELETE FROM "+t)
        store._conn.commit()
    random.seed(42)
    for wid,name,area,turno,lam,epis,conf in ROSTER:
        store.upsert_worker(wid,name,area,turno,SHIFTS,required_epis=epis,confidence=conf)
    for dev,name,st,worker in BELTS:
        store.upsert_belt(dev,name,st); store.assign(dev,worker)
    for name,level,st,pts,zepis in ZONES:
        store.add_zone(name,level,pts,station_id=st,required_epis=zepis)
    total = 0
    for wid,name,area,turno,lam,epis,conf in ROSTER:
        st = "EST-"+area[:3].upper()
        for d in range(SHIFTS):
            for _ in range(_poisson(lam)):
                etype,sev = _pick_type()
                epi = random.choice(EPIS) if etype == "EPI_AUSENTE" else None
                store.add_event(worker_id=wid,type=etype,severity=sev,epi=epi,area=area,
                                turno=turno,station_id=st,timestamp=_ts(SHIFTS-d,turno))
                total += 1
    print("Seed: %d perfis, %d cintos, %d zonas, %d eventos." % (len(ROSTER),len(BELTS),len(ZONES),total))

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db",default="data/tortuga.db")
    ap.add_argument("--force",action="store_true")
    ap.add_argument("--rank",action="store_true")
    a = ap.parse_args()
    store = EventStore(a.db); seed(store,force=a.force)
    if a.rank:
        from risk_engine import rank_workers
        l0,ranking = rank_workers(store.worker_summaries())
        print("\nλ0 = %.3f ev/turno" % l0)
        for r in ranking:
            print("%s %-10s ev=%3d P=%.2f p=%.4f %s" % (r.worker_id,r.area,r.events,r.p_next_shift,r.p_value_exact,r.risk_level))
    store.close()

if __name__ == "__main__":
    main()
