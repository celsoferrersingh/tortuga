"""
pose_estimator.py — Fase 2: RULA/REBA, Análise Temporal e Comportamental
Challenge SPI 2026 — FIAP × SPI

Implementa (seções 5.3 e 5.6 — Boas Práticas + Out of the Box):
  1. RULA (Rapid Upper Limb Assessment) — score 1-7         [NR-17]
  2. REBA (Rapid Entire Body Assessment) — score 1-15       [NR-17]
  3. Análise temporal: gestos repetitivos, fadiga muscular   [NR-17]
  4. Predição preditiva de queda (0.5–1.5 s de antecedência)[NR-35]
  5. Score ergonômico individual por sessão/turno (SSMA)
  6. Detecção multi-pessoa: distância segura entre operadores
  7. Integração EPC: zona perigosa × pose do trabalhador

Referências científicas:
  McAtamney & Corlett (1993) — RULA, Applied Ergonomics 24(2):91-99
  Hignett & McAtamney (2000) — REBA, Applied Ergonomics 31(2):201-205
  ABNT NBR NR-17 (Portaria MTb 3.751/1990) — ergonomia industrial
  ABNT NBR NR-35 (Portaria MTE 313/2012)   — trabalho em altura
"""
from __future__ import annotations

import collections
import logging
import math
from pathlib import Path

import cv2
import numpy as np

log = logging.getLogger("tortuga")

# ─── Índices COCO 17 keypoints ────────────────────────────────
KP = {
    "nose": 0, "left_eye": 1, "right_eye": 2,
    "left_ear": 3, "right_ear": 4,
    "left_shoulder": 5, "right_shoulder": 6,
    "left_elbow": 7, "right_elbow": 8,
    "left_wrist": 9, "right_wrist": 10,
    "left_hip": 11, "right_hip": 12,
    "left_knee": 13, "right_knee": 14,
    "left_ankle": 15, "right_ankle": 16,
}

# Conexões do esqueleto para desenho
SKELETON = [
    (KP["left_shoulder"],  KP["right_shoulder"]),
    (KP["left_shoulder"],  KP["left_elbow"]),
    (KP["left_elbow"],     KP["left_wrist"]),
    (KP["right_shoulder"], KP["right_elbow"]),
    (KP["right_elbow"],    KP["right_wrist"]),
    (KP["left_shoulder"],  KP["left_hip"]),
    (KP["right_shoulder"], KP["right_hip"]),
    (KP["left_hip"],       KP["right_hip"]),
    (KP["left_hip"],       KP["left_knee"]),
    (KP["left_knee"],      KP["left_ankle"]),
    (KP["right_hip"],      KP["right_knee"]),
    (KP["right_knee"],     KP["right_ankle"]),
    (KP["nose"],           KP["left_shoulder"]),
    (KP["nose"],           KP["right_shoulder"]),
]

# ─── Categorias de postura ────────────────────────────────────
POSTURE_SAFE      = "safe"
POSTURE_ERGONOMIC = "ergonomic_risk"
POSTURE_IMMEDIATE = "immediate_risk"
POSTURE_ZONE      = "zone_risk"

POSTURE_LABELS = {
    POSTURE_SAFE:      "Postura OK",
    POSTURE_ERGONOMIC: "Risco Ergonomico",
    POSTURE_IMMEDIATE: "RISCO IMEDIATO",
    POSTURE_ZONE:      "ZONA CRITICA",
}

# Cores BGR
POSE_COLOR = {
    POSTURE_SAFE:      ( 48, 195,  68),
    POSTURE_ERGONOMIC: ( 20, 160, 248),
    POSTURE_IMMEDIATE: ( 48,  55, 225),
    POSTURE_ZONE:      ( 48,  55, 225),
}

_SEG_COLORS = {
    "upper": (215, 128,  22),
    "arms":  (175, 185,  52),
    "legs":  (195,  78, 168),
    "head":  (230, 230, 230),
}

_SKELETON_COLOR = [
    _SEG_COLORS["upper"],  _SEG_COLORS["arms"],  _SEG_COLORS["arms"],
    _SEG_COLORS["arms"],   _SEG_COLORS["arms"],  _SEG_COLORS["upper"],
    _SEG_COLORS["upper"],  _SEG_COLORS["upper"], _SEG_COLORS["legs"],
    _SEG_COLORS["legs"],   _SEG_COLORS["legs"],  _SEG_COLORS["legs"],
    _SEG_COLORS["head"],   _SEG_COLORS["head"],
]

# Cor do badge RULA por score
def _rula_color(score: int) -> tuple[int, int, int]:
    if score <= 2: return ( 48, 195,  68)   # verde
    if score <= 4: return ( 20, 160, 248)   # âmbar
    if score <= 6: return ( 20, 100, 248)   # laranja
    return ( 48,  55, 225)                  # vermelho


# ═══════════════════════════════════════════════════════════════
#  TABELAS RULA  (McAtamney & Corlett, 1993)
# ═══════════════════════════════════════════════════════════════
# TABLE_A[upper_arm-1][lower_arm-1][wrist-1]  → valor base (1-9)
_RULA_A = [
    [[1,2,3,3],[2,2,3,3]],  # UA=1
    [[2,2,3,4],[3,3,3,4]],  # UA=2
    [[2,3,3,4],[4,4,4,5]],  # UA=3
    [[3,3,4,5],[4,4,5,5]],  # UA=4
]

# TABLE_B[neck-1][trunk-1][legs-1]  → valor base (1-9)
_RULA_B = [
    [[1,3],[2,3],[3,4],[5,5]],  # neck=1
    [[2,3],[2,3],[4,5],[5,6]],  # neck=2
    [[3,3],[3,4],[5,5],[6,7]],  # neck=3
    [[5,5],[5,6],[6,7],[7,8]],  # neck=4 (extensão ou torção)
]

# TABLE_C[score_a-1][score_b-1]  → RULA final (1-7)
_RULA_C = [
    [1,2,3,3,4,5,5],  # sA=1
    [2,2,3,4,4,5,5],  # sA=2
    [3,3,3,4,4,5,6],  # sA=3
    [3,3,3,4,5,6,6],  # sA=4
    [4,4,4,5,6,7,7],  # sA=5
    [4,4,5,6,6,7,7],  # sA=6
    [5,5,6,6,7,7,7],  # sA=7
    [5,5,6,7,7,7,7],  # sA=8
]

RULA_ACTION = {
    1:"Aceitavel", 2:"Aceitavel",
    3:"Investigar", 4:"Investigar",
    5:"Agir em breve", 6:"Agir em breve",
    7:"AGIR IMEDIATAMENTE",
}

# ═══════════════════════════════════════════════════════════════
#  TABELAS REBA  (Hignett & McAtamney, 2000)
# ═══════════════════════════════════════════════════════════════
# TABLE_A[neck-1][trunk-1][legs-1]  → score_a (1-12)
_REBA_A = [
    # neck=1
    [[1,2,3,4],[2,3,4,5],[2,4,5,6],[3,5,6,7],[4,6,7,8]],
    # neck=2
    [[1,3,4,5],[3,4,5,6],[4,5,6,7],[5,6,7,8],[6,7,8,9]],
    # neck=3
    [[3,4,5,6],[4,5,6,7],[5,6,7,8],[6,7,8,9],[7,8,9,9]],
]

# TABLE_B[upper_arm-1][lower_arm-1][wrist-1]  → score_b (1-12)
_REBA_B = [
    [[1,2,2],[1,2,3]],  # UA=1
    [[1,2,3],[2,3,4]],  # UA=2
    [[3,4,5],[4,5,5]],  # UA=3
    [[4,5,5],[5,6,7]],  # UA=4
    [[6,7,8],[7,8,8]],  # UA=5
    [[7,8,8],[8,9,9]],  # UA=6
]

# TABLE_C[score_a-1][score_b-1]  → REBA score_c (1-12)
_REBA_C = [
    [ 1, 1, 1, 2, 3, 3, 4, 5, 6, 7, 7, 7],  # sA=1
    [ 1, 2, 2, 3, 4, 4, 5, 6, 6, 7, 7, 8],  # sA=2
    [ 2, 3, 3, 3, 4, 5, 6, 7, 7, 8, 8, 8],  # sA=3
    [ 3, 4, 4, 4, 5, 6, 7, 8, 8, 9, 9, 9],  # sA=4
    [ 4, 4, 4, 5, 6, 7, 8, 8, 9, 9,10,10],  # sA=5
    [ 6, 6, 6, 7, 8, 8, 9, 9,10,10,11,11],  # sA=6
    [ 7, 7, 7, 8, 9, 9, 9,10,11,11,11,12],  # sA=7
    [ 8, 8, 8, 9,10,10,10,11,11,12,12,12],  # sA=8
    [ 9, 9, 9,10,10,11,11,12,12,12,12,12],  # sA=9
    [10,10,10,11,11,11,12,12,12,12,12,12],  # sA=10
    [11,11,11,11,12,12,12,12,12,12,12,12],  # sA=11
    [12,12,12,12,12,12,12,12,12,12,12,12],  # sA=12
]

REBA_RISK = {
    1:"Negligivel",
    2:"Baixo",3:"Baixo",
    4:"Medio",5:"Medio",6:"Medio",7:"Medio",
    8:"Alto",9:"Alto",10:"Alto",
    11:"Muito Alto",12:"Muito Alto",13:"Muito Alto",
    14:"Muito Alto",15:"Muito Alto",
}


# ═══════════════════════════════════════════════════════════════
#  FUNÇÕES UTILITÁRIAS
# ═══════════════════════════════════════════════════════════════
def _visible(kp_row: np.ndarray, min_conf: float = 0.25) -> bool:
    return float(kp_row[2]) >= min_conf


def _pt(kp_row: np.ndarray) -> tuple[int, int]:
    return (int(kp_row[0]), int(kp_row[1]))


def _midpoint(a: np.ndarray, b: np.ndarray) -> tuple[float, float]:
    return ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)


def _angle_trunk(shoulder_mid, hip_mid) -> float:
    """Ângulo do tronco em relação ao eixo vertical. 0°=ereto, 90°=deitado."""
    dx = shoulder_mid[0] - hip_mid[0]
    dy = hip_mid[1] - shoulder_mid[1]
    return float(math.degrees(math.atan2(abs(dx), abs(dy) + 1e-6)))


def _angle_3pts(a, b, c) -> float:
    """Ângulo em graus no ponto B, entre segmentos BA e BC."""
    a, b, c = np.array(a[:2]), np.array(b[:2]), np.array(c[:2])
    ba, bc  = a - b, c - b
    cos = np.dot(ba, bc) / (np.linalg.norm(ba) * np.linalg.norm(bc) + 1e-6)
    return float(np.degrees(np.arccos(np.clip(cos, -1.0, 1.0))))


def _elevation(p_base: np.ndarray, p_tip: np.ndarray) -> float:
    """
    Elevação do segmento base→tip em relação ao vertical para baixo.
    0°=braço caído, 90°=horizontal, 180°=braço erguido.
    """
    dx = float(p_tip[0] - p_base[0])
    dy = float(p_tip[1] - p_base[1])   # positivo = para baixo em imagem
    vec  = np.array([dx, dy])
    down = np.array([0.0, 1.0])
    cos_v = np.dot(vec / (np.linalg.norm(vec) + 1e-6), down)
    return float(math.degrees(math.acos(np.clip(cos_v, -1.0, 1.0))))


def _bbox_iou(a, b) -> float:
    """IoU de dois bounding boxes (x1,y1,x2,y2)."""
    if a is None or b is None:
        return 0.0
    ax1,ay1,ax2,ay2 = a;  bx1,by1,bx2,by2 = b
    ix1=max(ax1,bx1); iy1=max(ay1,by1)
    ix2=min(ax2,bx2); iy2=min(ay2,by2)
    iw=max(0,ix2-ix1); ih=max(0,iy2-iy1)
    inter=iw*ih
    if inter==0: return 0.0
    area_a=(ax2-ax1)*(ay2-ay1); area_b=(bx2-bx1)*(by2-by1)
    return inter/(area_a+area_b-inter+1e-6)


# ═══════════════════════════════════════════════════════════════
#  SCORING RULA — componentes
# ═══════════════════════════════════════════════════════════════
def _ua_rula(kp: np.ndarray, side: str) -> int:
    """Upper arm score RULA (1-4): elevação do cotovelo em relação ao ombro."""
    sh = kp[KP[f"{side}_shoulder"]]; el = kp[KP[f"{side}_elbow"]]
    if not (_visible(sh) and _visible(el)): return 2
    elev = _elevation(sh, el)   # 0=braço caído, 180=erguido
    if elev < 20:  return 1
    if elev < 45:  return 2
    if elev < 90:  return 3
    return 4


def _la_rula(kp: np.ndarray, side: str) -> int:
    """Lower arm score RULA (1-2): ângulo no cotovelo."""
    sh = kp[KP[f"{side}_shoulder"]]; el = kp[KP[f"{side}_elbow"]]
    wr = kp[KP[f"{side}_wrist"]]
    if not all(_visible(p) for p in [sh,el,wr]): return 1
    ang = _angle_3pts(sh, el, wr)    # 180=estendido, 90=flexão 90°
    return 1 if 60 <= ang <= 100 else 2


def _wr_rula(kp: np.ndarray, side: str) -> int:
    """Wrist score RULA (1-3): desvio estimado pulso-antebraço."""
    el = kp[KP[f"{side}_elbow"]]; wr = kp[KP[f"{side}_wrist"]]
    if not (_visible(el) and _visible(wr)): return 1
    dy = abs(float(wr[1]-el[1])); dx = abs(float(wr[0]-el[0]))
    if dx < 1e-6: return 1
    ang = math.degrees(math.atan2(dy, dx))
    if ang < 15: return 1
    if ang < 30: return 2
    return 3


def _neck_rula(kp: np.ndarray) -> int:
    """Neck score RULA (1-4): inclinação da cabeça."""
    nose = kp[KP["nose"]]; ls = kp[KP["left_shoulder"]]; rs = kp[KP["right_shoulder"]]
    if not _visible(nose): return 2
    sh_vis = _visible(ls) or _visible(rs)
    if not sh_vis: return 2
    sh_mid = _midpoint(ls if _visible(ls) else rs, rs if _visible(rs) else ls)
    dx = float(nose[0]) - sh_mid[0]; dy = sh_mid[1] - float(nose[1])
    ang = math.degrees(math.atan2(abs(dx), abs(dy) + 1e-6))
    if ang < 10: return 1
    if ang < 20: return 2
    if ang < 35: return 3
    return 4


def _trunk_rula(kp: np.ndarray) -> int:
    """Trunk score RULA (1-4): inclinação do tronco."""
    ls=kp[KP["left_shoulder"]]; rs=kp[KP["right_shoulder"]]
    lh=kp[KP["left_hip"]];     rh=kp[KP["right_hip"]]
    vis = [_visible(p) for p in [ls,rs,lh,rh]]
    if sum(vis) < 2: return 1
    s_mid = _midpoint(ls if vis[0] else rs, rs if vis[1] else ls)
    h_mid = _midpoint(lh if vis[2] else rh, rh if vis[3] else lh)
    ang = _angle_trunk(s_mid, h_mid)
    if ang < 10: return 1
    if ang < 20: return 2
    if ang < 60: return 3
    return 4


def _legs_rula(kp: np.ndarray) -> int:
    """Leg score RULA (1-2): estabilidade do apoio."""
    la = kp[KP["left_ankle"]]; ra = kp[KP["right_ankle"]]
    if not (_visible(la) and _visible(ra)): return 1
    dy = abs(float(la[1]) - float(ra[1])); dx = abs(float(la[0]) - float(ra[0]))
    if dx > 1e-6 and dy / dx > 0.5: return 2
    return 1


def compute_rula(kp: np.ndarray) -> dict:
    """Calcula score RULA completo (1-7) a partir de keypoints COCO."""
    ua = max(_ua_rula(kp,"left"), _ua_rula(kp,"right"))
    la = max(_la_rula(kp,"left"), _la_rula(kp,"right"))
    wr = max(_wr_rula(kp,"left"), _wr_rula(kp,"right"))
    neck  = _neck_rula(kp)
    trunk = _trunk_rula(kp)
    legs  = _legs_rula(kp)

    # Group A — membros superiores
    a_base  = _RULA_A[ua-1][la-1][wr-1]
    score_a = min(a_base, 8)   # sem ajuste de carga (sem dado)

    # Group B — pescoço/tronco/pernas
    b_base  = _RULA_B[min(neck-1,3)][min(trunk-1,3)][min(legs-1,1)]
    score_b = min(b_base, 7)

    final = _RULA_C[score_a-1][score_b-1]
    return {
        "rula_score":  final,
        "rula_action": RULA_ACTION.get(final, "AGIR IMEDIATAMENTE"),
        "rula_a": score_a, "rula_b": score_b,
        "rula_components": {
            "upper_arm":ua,"lower_arm":la,"wrist":wr,
            "neck":neck,"trunk":trunk,"legs":legs,
        },
    }


# ═══════════════════════════════════════════════════════════════
#  SCORING REBA — componentes
# ═══════════════════════════════════════════════════════════════
def _neck_reba(kp: np.ndarray) -> int:
    """Neck score REBA (1-3)."""
    nose=kp[KP["nose"]]; ls=kp[KP["left_shoulder"]]; rs=kp[KP["right_shoulder"]]
    if not _visible(nose): return 1
    if not (_visible(ls) or _visible(rs)): return 1
    sh_mid = _midpoint(ls if _visible(ls) else rs, rs if _visible(rs) else ls)
    dx=float(nose[0])-sh_mid[0]; dy=sh_mid[1]-float(nose[1])
    ang = math.degrees(math.atan2(abs(dx), abs(dy)+1e-6))
    if ang < 20: return 1
    return 2


def _trunk_reba(kp: np.ndarray) -> int:
    """Trunk score REBA (1-5)."""
    ang = _trunk_angle_deg(kp)
    if ang <  5: return 1
    if ang < 20: return 2
    if ang < 60: return 3
    return 4


def _legs_reba(kp: np.ndarray) -> int:
    """Leg score REBA (1-4): considera flexão do joelho."""
    lh=kp[KP["left_hip"]];  rh=kp[KP["right_hip"]]
    lk=kp[KP["left_knee"]]; rk=kp[KP["right_knee"]]
    la=kp[KP["left_ankle"]];ra=kp[KP["right_ankle"]]
    # Base
    score = 1
    if _visible(la) and _visible(ra):
        dy=abs(float(la[1])-float(ra[1])); dx=abs(float(la[0])-float(ra[0]))
        if dx > 1e-6 and dy/dx > 0.5: score = 2
    # Flexão de joelho
    for hp,kn,ak in [(lh,lk,la),(rh,rk,ra)]:
        if all(_visible(p) for p in [hp,kn,ak]):
            knee_ang = _angle_3pts(hp,kn,ak)   # 180=esticado
            if knee_ang < 120:   # > 60° de flexão
                score += 1; break
    return min(score, 4)


def _ua_reba(kp: np.ndarray, side: str) -> int:
    """Upper arm score REBA (1-6)."""
    sh=kp[KP[f"{side}_shoulder"]]; el=kp[KP[f"{side}_elbow"]]
    if not (_visible(sh) and _visible(el)): return 2
    elev = _elevation(sh, el)
    if elev < 20: return 1
    if elev < 45: return 2
    if elev < 90: return 3
    if elev < 135: return 4
    return 5   # ≥135° = braço muito acima da cabeça


def _la_reba(kp: np.ndarray, side: str) -> int:
    """Lower arm score REBA (1-2)."""
    sh=kp[KP[f"{side}_shoulder"]]; el=kp[KP[f"{side}_elbow"]]
    wr=kp[KP[f"{side}_wrist"]]
    if not all(_visible(p) for p in [sh,el,wr]): return 1
    ang = _angle_3pts(sh,el,wr)
    return 1 if 60 <= ang <= 100 else 2


def _wr_reba(kp: np.ndarray, side: str) -> int:
    """Wrist score REBA (1-3)."""
    el=kp[KP[f"{side}_elbow"]]; wr=kp[KP[f"{side}_wrist"]]
    if not (_visible(el) and _visible(wr)): return 1
    dy=abs(float(wr[1])-float(el[1])); dx=abs(float(wr[0])-float(el[0]))
    if dx < 1e-6: return 1
    ang = math.degrees(math.atan2(dy, dx))
    if ang < 15: return 1
    if ang < 30: return 2
    return 3


def compute_reba(kp: np.ndarray) -> dict:
    """Calcula score REBA completo (1-15) a partir de keypoints COCO."""
    neck  = _neck_reba(kp)
    trunk = _trunk_reba(kp)
    legs  = _legs_reba(kp)
    ua = max(_ua_reba(kp,"left"), _ua_reba(kp,"right"))
    la = max(_la_reba(kp,"left"), _la_reba(kp,"right"))
    wr = max(_wr_reba(kp,"left"), _wr_reba(kp,"right"))

    # Group A
    a_val   = _REBA_A[min(neck-1,2)][min(trunk-1,4)][min(legs-1,3)]
    score_a = min(a_val, 12)  # sem ajuste de carga

    # Group B
    b_val   = _REBA_B[min(ua-1,5)][min(la-1,1)][min(wr-1,2)]
    score_b = min(b_val, 12)  # sem ajuste de pega

    c_val = _REBA_C[score_a-1][score_b-1]
    final = c_val   # sem activity score (sem dado temporal aqui)

    return {
        "reba_score": final,
        "reba_risk":  REBA_RISK.get(final,"Muito Alto"),
        "reba_a": score_a, "reba_b": score_b,
        "reba_components": {
            "neck":neck,"trunk":trunk,"legs":legs,
            "upper_arm":ua,"lower_arm":la,"wrist":wr,
        },
    }


def _trunk_angle_deg(kp: np.ndarray) -> float:
    """Retorna o ângulo do tronco em graus (0=ereto)."""
    ls=kp[KP["left_shoulder"]]; rs=kp[KP["right_shoulder"]]
    lh=kp[KP["left_hip"]];     rh=kp[KP["right_hip"]]
    vis = [_visible(p) for p in [ls,rs,lh,rh]]
    if sum(vis) < 2: return 0.0
    s_mid = _midpoint(ls if vis[0] else rs, rs if vis[1] else ls)
    h_mid = _midpoint(lh if vis[2] else rh, rh if vis[3] else lh)
    return _angle_trunk(s_mid, h_mid)


# ═══════════════════════════════════════════════════════════════
#  RASTREADOR TEMPORAL DE PESSOAS
# ═══════════════════════════════════════════════════════════════
class PersonTracker:
    """
    Rastreia pessoas entre frames para análise temporal (seção 5.6).
    Detecta: gestos repetitivos, fadiga, predição de queda.
    Mantém score ergonômico individual por sessão (SSMA).
    """
    MAX_HISTORY  = 90    # frames (~3 s a 30 fps)
    LOST_FRAMES  = 20    # frames sem detecção para descartar track
    FPS_EST      = 30.0  # estimativa de FPS para conversão tempo/frames

    def __init__(self):
        self._tracks:  dict[int, dict] = {}
        self._next_id: int = 0
        self._frame:   int = 0

    # ── API principal ─────────────────────────────────────────
    def update(self, people: list[dict]) -> list[dict]:
        """
        Associa cada pessoa a um track existente por IoU de bbox.
        Enriquece cada person-dict com campos temporais e de score.
        """
        self._frame += 1
        for t in self._tracks.values():
            t["updated"] = False

        enriched: list[dict] = []
        for person in people:
            tid = self._match_or_create(person.get("bbox"))
            track = self._tracks[tid]
            track["updated"]   = True
            track["last_seen"] = self._frame
            if person.get("bbox"):
                track["last_bbox"] = person["bbox"]

            # Salva métricas no histórico
            track["history"].append({
                "trunk_angle": _trunk_angle_deg(person["keypoints"]),
                "rula_score":  person.get("rula_score", 0),
                "reba_score":  person.get("reba_score", 0),
                "frame":       self._frame,
            })
            if person.get("rula_score", 0) > 0:
                track["session_rula"].append(person["rula_score"])

            # Análise temporal
            temporal = self._analyze(track)

            p = dict(person)
            p["track_id"]      = tid
            p["temporal"]      = temporal
            p["session_avg_rula"] = (
                sum(track["session_rula"]) / max(len(track["session_rula"]), 1)
            )
            p["session_max_rula"] = (
                max(track["session_rula"]) if track["session_rula"] else 0
            )
            enriched.append(p)

        # Remove tracks perdidos
        lost = [tid for tid, t in self._tracks.items()
                if self._frame - t["last_seen"] > self.LOST_FRAMES]
        for tid in lost:
            del self._tracks[tid]

        return enriched

    def session_summary(self) -> list[dict]:
        """Exporta resumo ergonômico por track (sem identidade — SSMA)."""
        out = []
        for tid, t in self._tracks.items():
            sr = t["session_rula"]
            if not sr: continue
            out.append({
                "worker_id":   f"OP-{tid:03d}",
                "avg_rula":    round(sum(sr)/len(sr), 2),
                "max_rula":    max(sr),
                "frames_high": sum(1 for v in sr if v >= 5),
                "action":      RULA_ACTION.get(max(sr),"AGIR IMEDIATAMENTE"),
            })
        return out

    # ── Internos ──────────────────────────────────────────────
    def _match_or_create(self, bbox) -> int:
        best_id, best_iou = -1, 0.25
        for tid, track in self._tracks.items():
            if track["updated"]: continue
            iou = _bbox_iou(bbox, track.get("last_bbox"))
            if iou > best_iou:
                best_iou, best_id = iou, tid
        if best_id == -1:
            best_id = self._next_id; self._next_id += 1
            self._tracks[best_id] = {
                "history":    collections.deque(maxlen=self.MAX_HISTORY),
                "last_bbox":  bbox,
                "last_seen":  self._frame,
                "updated":    False,
                "session_rula": [],
            }
        return best_id

    def _analyze(self, track: dict) -> dict:
        """Análise temporal: repetição, fadiga, predição de queda."""
        hist = list(track["history"])
        result = {
            "repetition":    False,
            "fatigue":       False,
            "fall_predicted":False,
            "fall_eta_s":    None,
            "details":       [],
        }
        if len(hist) < 8:
            return result

        angles = [h["trunk_angle"] for h in hist]

        # 1. Predição preditiva de queda (NR-35, seção 5.6)
        #    Velocidade angular: se o tronco está inclinando rapidamente,
        #    extrapola linearmente o tempo até atingir 60° (queda).
        if len(angles) >= 6:
            window = angles[-6:]
            velocity = (window[-1] - window[0]) / 5.0   # °/frame
            if velocity > 2.5 and angles[-1] > 20:
                frames_to_fall = max(1, (60.0 - angles[-1]) / max(velocity, 0.1))
                eta_s = frames_to_fall / self.FPS_EST
                if eta_s < 1.5:
                    result["fall_predicted"] = True
                    result["fall_eta_s"]     = round(eta_s, 1)
                    result["details"].append(
                        f"Queda prevista em ~{eta_s:.1f}s (vel {velocity:.1f} deg/frame)"
                    )

        # 2. Gestos repetitivos (NR-17, análise temporal seção 5.6)
        #    Detecta oscilação periódica no ângulo do tronco.
        if len(angles) >= 20:
            recent = angles[-20:]
            mean_a = sum(recent) / len(recent)
            amplitude = max(recent) - min(recent)
            crossings = sum(
                1 for i in range(1, len(recent))
                if (recent[i-1]-mean_a) * (recent[i]-mean_a) < 0
            )
            if crossings >= 6 and amplitude > 15:
                freq = crossings / (len(recent) / self.FPS_EST) / 2.0
                result["repetition"] = True
                result["details"].append(
                    f"Gesto repetitivo: ~{freq:.1f}Hz, ampl {amplitude:.0f} deg"
                )

        # 3. Fadiga (NR-17): RULA crescente ao longo da sessão
        rula_hist = [h["rula_score"] for h in hist if h["rula_score"] > 0]
        if len(rula_hist) >= 20:
            half = len(rula_hist)//2
            avg1 = sum(rula_hist[:half]) / half
            avg2 = sum(rula_hist[half:]) / max(len(rula_hist[half:]),1)
            if avg2 > avg1 + 0.8:
                result["fatigue"] = True
                result["details"].append(
                    f"Fadiga: RULA medio {avg1:.1f}→{avg2:.1f}"
                )

        return result


# ═══════════════════════════════════════════════════════════════
#  ANALISADOR DE POSTURA  (regras + RULA + REBA)
# ═══════════════════════════════════════════════════════════════
class PostureAnalyzer:
    """
    Classifica a postura do trabalhador e calcula scores RULA e REBA
    a partir dos 17 keypoints COCO.
    """

    def __init__(
        self,
        trunk_bend_thresh: float = 40.0,
        fall_angle_thresh: float = 60.0,
        arms_above_ratio:  float = 0.05,
        crouch_ratio:      float = 0.4,
        min_conf:          float = 0.25,
    ):
        self.trunk_bend = trunk_bend_thresh
        self.fall_angle = fall_angle_thresh
        self.arms_ratio = arms_above_ratio
        self.crouch_r   = crouch_ratio
        self.min_conf   = min_conf

    def analyze(self, kp: np.ndarray, danger_zones: list | None = None) -> dict:
        result = {
            "posture":    POSTURE_SAFE,
            "label":      POSTURE_LABELS[POSTURE_SAFE],
            "color":      POSE_COLOR[POSTURE_SAFE],
            "risk_score": 0.0,
            "details":    [],
            "angles":     {},
            "rula_score": 0,
            "reba_score": 0,
            "rula_action":"",
            "reba_risk":  "",
        }

        # ── RULA / REBA (calculados sempre) ───────────────────
        rula = compute_rula(kp)
        reba = compute_reba(kp)
        result["rula_score"]  = rula["rula_score"]
        result["reba_score"]  = reba["reba_score"]
        result["rula_action"] = rula["rula_action"]
        result["reba_risk"]   = reba["reba_risk"]
        result["angles"]["rula_components"] = rula["rula_components"]
        result["angles"]["reba_components"] = reba["reba_components"]

        # ── 1. Queda / risco imediato ─────────────────────────
        fall = self._check_fall(kp)
        if fall["detected"]:
            result.update(
                posture=POSTURE_IMMEDIATE,
                label=POSTURE_LABELS[POSTURE_IMMEDIATE],
                color=POSE_COLOR[POSTURE_IMMEDIATE],
                risk_score=1.0,
                details=fall["details"],
            )
            return result

        # ── 2. Zona crítica (EPC) ─────────────────────────────
        if danger_zones:
            zone = self._check_zone(kp, danger_zones)
            if zone["detected"]:
                result.update(
                    posture=POSTURE_ZONE,
                    label=POSTURE_LABELS[POSTURE_ZONE],
                    color=POSE_COLOR[POSTURE_ZONE],
                    risk_score=0.92,
                    details=zone["details"],
                )
                return result

        # ── 3. Risco ergonômico (RULA ≥ 3 OU regras NR-17) ───
        ergo = self._check_ergonomic(kp)
        rula_risk = rula["rula_score"] >= 3

        if ergo["detected"] or rula_risk:
            details = list(ergo["details"])
            if rula_risk:
                details.insert(0,
                    f"RULA {rula['rula_score']}/7 — {rula['rula_action']}"
                    f"  |  REBA {reba['reba_score']}/15 ({reba['reba_risk']})"
                )
            score = max(ergo.get("score", 0.0),
                        min(1.0, (rula["rula_score"] - 1) / 6.0))
            result.update(
                posture=POSTURE_ERGONOMIC,
                label=POSTURE_LABELS[POSTURE_ERGONOMIC],
                color=POSE_COLOR[POSTURE_ERGONOMIC],
                risk_score=score,
                details=details,
                angles={**result["angles"], **ergo.get("angles", {})},
            )
            return result

        # Postura segura — adiciona RULA/REBA nos detalhes informativos
        result["details"].append(
            f"RULA {rula['rula_score']}/7 ({rula['rula_action']})"
            f"  |  REBA {reba['reba_score']}/15 ({reba['reba_risk']})"
        )
        result["angles"] = {**result["angles"], **self._all_angles(kp)}
        return result

    # ── Queda ─────────────────────────────────────────────────
    def _check_fall(self, kp: np.ndarray) -> dict:
        ls=kp[KP["left_shoulder"]]; rs=kp[KP["right_shoulder"]]
        lh=kp[KP["left_hip"]];     rh=kp[KP["right_hip"]]
        vis = [_visible(p, self.min_conf) for p in [ls,rs,lh,rh]]
        if sum(vis) < 3: return {"detected":False,"details":[]}
        s_mid = _midpoint(ls,rs); h_mid = _midpoint(lh,rh)
        ang = _angle_trunk(s_mid, h_mid)
        if ang > self.fall_angle:
            return {"detected":True,
                    "details":[f"Queda detectada: tronco {ang:.0f} graus"]}
        return {"detected":False,"details":[]}

    # ── Zona restrita ─────────────────────────────────────────
    def _check_zone(self, kp: np.ndarray, zones: list) -> dict:
        pts = [_pt(kp[i]) for i in range(17) if _visible(kp[i], self.min_conf)]
        if not pts: return {"detected":False,"details":[]}
        for zone in zones:
            arr = np.array(zone, dtype=np.int32)
            for pt in pts:
                if cv2.pointPolygonTest(arr, pt, False) >= 0:
                    return {"detected":True,
                            "details":["Trabalhador em zona restrita (EPC)"]}
        return {"detected":False,"details":[]}

    # ── Risco ergonômico (regras NR-17) ──────────────────────
    def _check_ergonomic(self, kp: np.ndarray) -> dict:
        details, angles, score = [], {}, 0.0
        ls=kp[KP["left_shoulder"]]; rs=kp[KP["right_shoulder"]]
        lh=kp[KP["left_hip"]];     rh=kp[KP["right_hip"]]
        lw=kp[KP["left_wrist"]];   rw=kp[KP["right_wrist"]]
        lk=kp[KP["left_knee"]];    rk=kp[KP["right_knee"]]
        la=kp[KP["left_ankle"]];   ra=kp[KP["right_ankle"]]
        mc = self.min_conf

        # A) Inclinação do tronco
        vis_t = [_visible(p,mc) for p in [ls,rs,lh,rh]]
        if sum(vis_t) >= 3:
            s_mid = _midpoint(ls,rs); h_mid = _midpoint(lh,rh)
            t_ang = _angle_trunk(s_mid, h_mid)
            angles["trunk_bend"] = round(t_ang,1)
            if t_ang > self.trunk_bend:
                details.append(f"Tronco inclinado {t_ang:.0f}° (NR-17 lim {self.trunk_bend:.0f}°)")
                score = max(score, min(1.0,(t_ang-self.trunk_bend)/50.0))

        # B) Braços acima dos ombros
        body_h = abs(float(lh[1])-float(ls[1])) if (_visible(ls,mc) and _visible(lh,mc)) else 200
        for side, sh, wr in [("esq",ls,lw),("dir",rs,rw)]:
            if _visible(sh,mc) and _visible(wr,mc):
                elev = (float(sh[1]) - float(wr[1])) / max(body_h,1)
                if elev > self.arms_ratio:
                    details.append(f"Braco {side} acima do ombro ({elev*100:.0f}%)")
                    score = max(score, 0.55)

        # C) Agachamento profundo
        vis_l = [_visible(p,mc) for p in [lh,rh,lk,rk,la,ra]]
        if sum(vis_l) >= 4:
            hip_y   = (float(lh[1])+float(rh[1]))/2
            knee_y  = (float(lk[1])+float(rk[1]))/2
            ankle_y = (float(la[1])+float(ra[1]))/2
            ratio = abs(hip_y-knee_y)/max(abs(knee_y-ankle_y),1)
            angles["knee_hip_ratio"] = round(ratio,2)
            if ratio < self.crouch_r:
                details.append(f"Agachamento profundo (ratio {ratio:.2f})")
                score = max(score, 0.5)

        return {"detected":len(details)>0,"details":details,"angles":angles,"score":score}

    # ── Ângulos auxiliares ────────────────────────────────────
    def _all_angles(self, kp: np.ndarray) -> dict:
        angles = {}
        for side, sh, el, wr in [
            ("esq", KP["left_shoulder"],  KP["left_elbow"],  KP["left_wrist"]),
            ("dir", KP["right_shoulder"], KP["right_elbow"], KP["right_wrist"]),
        ]:
            if all(_visible(kp[i],self.min_conf) for i in [sh,el,wr]):
                angles[f"elbow_{side}"] = round(_angle_3pts(kp[sh],kp[el],kp[wr]),1)
        for side, hp, kn, ak in [
            ("esq", KP["left_hip"],  KP["left_knee"],  KP["left_ankle"]),
            ("dir", KP["right_hip"], KP["right_knee"], KP["right_ankle"]),
        ]:
            if all(_visible(kp[i],self.min_conf) for i in [hp,kn,ak]):
                angles[f"knee_{side}"] = round(_angle_3pts(kp[hp],kp[kn],kp[ak]),1)
        return angles


# ═══════════════════════════════════════════════════════════════
#  DETECTOR DE DISTÂNCIA ENTRE PESSOAS  (seção 5.6)
# ═══════════════════════════════════════════════════════════════
def compute_interperson_distances(
    people: list[dict],
    safe_dist_m: float = 1.5,
    person_height_m: float = 1.70,
) -> list[dict]:
    """
    Calcula distâncias entre pares de trabalhadores.
    Usa altura do bounding box como referência de escala (~1.70 m).
    Retorna lista de alertas para pares abaixo de safe_dist_m.
    """
    warnings: list[dict] = []
    n = len(people)
    for i in range(n):
        for j in range(i+1, n):
            bi = people[i].get("bbox"); bj = people[j].get("bbox")
            if bi is None or bj is None: continue
            ci = ((bi[0]+bi[2])//2, (bi[1]+bi[3])//2)
            cj = ((bj[0]+bj[2])//2, (bj[1]+bj[3])//2)
            pixel_dist = math.sqrt((ci[0]-cj[0])**2 + (ci[1]-cj[1])**2)
            hi = max(bi[3]-bi[1], 1); hj = max(bj[3]-bj[1], 1)
            avg_h_px = (hi + hj) / 2.0
            ppm = avg_h_px / person_height_m           # pixels por metro
            dist_m = pixel_dist / ppm
            if dist_m < safe_dist_m:
                warnings.append({
                    "idx_i":   i, "idx_j": j,
                    "dist_m":  round(dist_m, 2),
                    "center_i":ci,"center_j":cj,
                    "severity":"high" if dist_m < 0.8 else "medium",
                })
    return warnings


# ═══════════════════════════════════════════════════════════════
#  ESTIMADOR PRINCIPAL
# ═══════════════════════════════════════════════════════════════
class PoseEstimator:
    """
    Wrapper YOLOv8-pose com análise ergonômica completa:
    RULA, REBA, análise temporal, score por sessão e multi-pessoa.
    """

    def __init__(
        self,
        model_path:   str   = "yolov8n-pose.pt",
        confidence:   float = 0.30,
        device:       str | None = None,
        danger_zones: list | None = None,
    ):
        from ultralytics import YOLO as _YOLO
        from detector   import _best_device

        self.device      = device or _best_device()
        self.confidence  = confidence
        self.danger_zones: list = danger_zones or []
        self.analyzer    = PostureAnalyzer()
        self.tracker     = PersonTracker()

        resolved = Path(model_path)
        if not resolved.exists():
            resolved = Path(__file__).parent / "models" / model_path
        self.model = _YOLO(str(resolved) if resolved.exists() else model_path)
        self.model.to(self.device)

        # Warm-up
        dummy = np.zeros((320, 320, 3), dtype=np.uint8)
        self.model(dummy, conf=confidence, verbose=False, device=self.device)
        log.info("PoseEstimator pronto | device=%s | RULA+REBA+Temporal ativos",
                 self.device.upper())

    def detect(self, frame: np.ndarray) -> list[dict]:
        """
        Detecta pessoas, extrai keypoints, calcula RULA/REBA,
        aplica análise temporal e multi-pessoa.
        """
        results = self.model(frame, conf=self.confidence,
                             verbose=False, device=self.device)
        people: list[dict] = []

        for result in results:
            if result.keypoints is None: continue
            kp_data = result.keypoints.data
            boxes   = result.boxes

            for i in range(len(kp_data)):
                kp = kp_data[i].cpu().numpy()   # (17,3)
                bbox = None
                if boxes is not None and i < len(boxes):
                    x1,y1,x2,y2 = boxes.xyxy[i].tolist()
                    bbox = (int(x1),int(y1),int(x2),int(y2))

                posture = self.analyzer.analyze(
                    kp, self.danger_zones if self.danger_zones else None
                )

                people.append({
                    "keypoints":    kp,
                    "bbox":         bbox,
                    "posture":      posture["posture"],
                    "label":        posture["label"],
                    "color":        posture["color"],
                    "details":      posture["details"],
                    "risk_score":   posture["risk_score"],
                    "angles":       posture.get("angles", {}),
                    "rula_score":   posture["rula_score"],
                    "reba_score":   posture["reba_score"],
                    "rula_action":  posture["rula_action"],
                    "reba_risk":    posture["reba_risk"],
                    "is_immediate": posture["posture"] == POSTURE_IMMEDIATE,
                    "is_zone":      posture["posture"] == POSTURE_ZONE,
                    "is_ergonomic": posture["posture"] == POSTURE_ERGONOMIC,
                    "is_any_risk":  posture["posture"] != POSTURE_SAFE,
                })

        # Análise temporal por pessoa
        people = self.tracker.update(people)

        # Elevar prioridade se queda prevista temporalmente
        for p in people:
            tmp = p.get("temporal", {})
            if tmp.get("fall_predicted") and p["posture"] != POSTURE_IMMEDIATE:
                p["posture"]    = POSTURE_IMMEDIATE
                p["label"]      = POSTURE_LABELS[POSTURE_IMMEDIATE]
                p["color"]      = POSE_COLOR[POSTURE_IMMEDIATE]
                p["is_immediate"]= True
                p["is_any_risk"] = True
                p["details"]    = tmp["details"] + p["details"]

        return people

    # ── Helpers para pipeline ─────────────────────────────────
    def has_immediate_risk(self, people: list[dict]) -> bool:
        return any(p.get("is_immediate") or p.get("is_zone") for p in people)

    def has_any_risk(self, people: list[dict]) -> bool:
        return any(p.get("is_any_risk") for p in people)

    def get_risk_summary(self, people: list[dict]) -> list[str]:
        out = []
        for p in people:
            if p.get("is_any_risk"):
                base = p["label"]
                if p.get("details"):
                    base += f": {p['details'][0][:40]}"
                out.append(base)
            # Avisos temporais
            tmp = p.get("temporal", {})
            for key, msg in [
                ("repetition", "Gesto repetitivo detectado"),
                ("fatigue",    "Sinal de fadiga muscular"),
            ]:
                if tmp.get(key): out.append(msg)
        return out

    def get_session_summary(self) -> list[dict]:
        """Resumo SSMA por trabalhador (sem expor identidade)."""
        return self.tracker.session_summary()

    def set_danger_zones(self, zones: list) -> None:
        self.danger_zones = zones

    # ── Compatibilidade gui.py ─────────────────────────────────
    @property
    def model_proxy(self):
        return type("_F", (), {"names": {}})()


# ═══════════════════════════════════════════════════════════════
#  RENDERIZAÇÃO
# ═══════════════════════════════════════════════════════════════
def render_pose_overlay(frame: np.ndarray, people: list[dict],
                        S: float = 1.0) -> np.ndarray:
    """
    Desenha esqueleto colorido, keypoints, label de postura e
    badge RULA sobre o frame.
    S = fator de escala derivado da resolução do display.
    """
    font = cv2.FONT_HERSHEY_DUPLEX
    for person in people:
        kp    = person["keypoints"]
        color = person["color"]
        t     = max(1, int(2 * S))
        r_kp  = max(3, int(4 * S))

        # Segmentos do esqueleto
        for idx, (i, j) in enumerate(SKELETON):
            if _visible(kp[i]) and _visible(kp[j]):
                cv2.line(frame, _pt(kp[i]), _pt(kp[j]),
                         _SKELETON_COLOR[idx], t, cv2.LINE_AA)

        # Keypoints
        for i in range(17):
            if _visible(kp[i]):
                cv2.circle(frame, _pt(kp[i]), r_kp, color, -1, cv2.LINE_AA)
                cv2.circle(frame, _pt(kp[i]), r_kp, (0,0,0),  1, cv2.LINE_AA)

        # Badge RULA no canto superior do bbox
        rula_score = person.get("rula_score", 0)
        reba_score = person.get("reba_score", 0)
        if person.get("bbox") and rula_score > 0:
            x1, y1, x2, y2 = person["bbox"]
            rc = _rula_color(rula_score)
            badge_txt = f"RULA:{rula_score} REBA:{reba_score}"
            sz = 0.40 * S
            (bw, bh), _ = cv2.getTextSize(badge_txt, font, sz, 1)
            pad = int(4 * S)
            bx1 = x2 - bw - pad * 2
            by1 = y1
            by2 = y1 + bh + pad * 2
            # fundo badge
            overlay = frame.copy()
            cv2.rectangle(overlay, (bx1, by1), (x2, by2), rc, -1)
            cv2.addWeighted(overlay, 0.85, frame, 0.15, 0, frame)
            cv2.putText(frame, badge_txt, (bx1 + pad, by2 - pad),
                        font, sz, (255, 255, 255), 1, cv2.LINE_AA)

        # Bbox e label de postura quando há risco
        if person.get("bbox") and person.get("is_any_risk"):
            x1, y1, x2, y2 = person["bbox"]
            thick = max(2, int(3 * S))
            cv2.rectangle(frame, (x1, y1), (x2, y2), color, thick, cv2.LINE_AA)

            label = person["label"]
            sz    = 0.45 * S
            (tw, th), _ = cv2.getTextSize(label, font, sz, 1)
            pad = int(5 * S)
            lx1, ly1 = x1, max(0, y1 - th - pad * 2)
            lx2, ly2 = lx1 + tw + pad * 2, y1
            cv2.rectangle(frame, (lx1, ly1), (lx2, ly2), color, -1)
            cv2.putText(frame, label, (lx1+pad, ly2-pad),
                        font, sz, (255, 255, 255), 1, cv2.LINE_AA)

        # Badge de queda prevista (predição preditiva)
        tmp = person.get("temporal", {})
        if tmp.get("fall_predicted") and person.get("bbox"):
            x1, y1, x2, y2 = person["bbox"]
            eta = tmp.get("fall_eta_s", "?")
            warn_txt = f"QUEDA ~{eta}s"
            sz = 0.55 * S
            (ww, wh), _ = cv2.getTextSize(warn_txt, cv2.FONT_HERSHEY_SIMPLEX, sz, 2)
            wx = (x1 + x2) // 2 - ww // 2
            wy = y2 + int(8 * S)
            cv2.rectangle(frame, (wx-4, wy-wh-4), (wx+ww+4, wy+4), (0, 0, 200), -1)
            cv2.putText(frame, warn_txt, (wx, wy),
                        cv2.FONT_HERSHEY_SIMPLEX, sz, (255, 255, 255), 2, cv2.LINE_AA)

        # Badge de gesto repetitivo
        if tmp.get("repetition") and person.get("bbox"):
            x1, y1, x2, y2 = person["bbox"]
            cv2.putText(frame, "REP", (x1 + int(4*S), y2 - int(4*S)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.35*S, (20,160,248), 1, cv2.LINE_AA)

        # Badge de fadiga
        if tmp.get("fatigue") and person.get("bbox"):
            x1, y1, x2, y2 = person["bbox"]
            cv2.putText(frame, "FAD", (x1 + int(30*S), y2 - int(4*S)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.35*S, (20,100,248), 1, cv2.LINE_AA)

    return frame


def render_danger_zones(frame: np.ndarray, zones: list[list],
                        active: bool = True) -> np.ndarray:
    """Desenha polígonos de zonas perigosas no frame."""
    color_fill   = (0,  0, 200) if active else (60, 60, 60)
    color_border = (0,  0, 255) if active else (100,100,100)
    for zone in zones:
        if len(zone) < 3: continue
        pts = np.array(zone, dtype=np.int32)
        overlay = frame.copy()
        cv2.fillPoly(overlay, [pts], color_fill)
        cv2.addWeighted(overlay, 0.20, frame, 0.80, 0, frame)
        cv2.polylines(frame, [pts], True, color_border, 2, cv2.LINE_AA)
        cx, cy = pts.mean(axis=0).astype(int)
        cv2.putText(frame, "ZONA RESTRITA", (cx-55, cy),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255,255,255), 1, cv2.LINE_AA)
    return frame


def render_distance_warnings(frame: np.ndarray, people: list[dict],
                              S: float = 1.0) -> np.ndarray:
    """
    Desenha linhas e alertas de distância insegura entre operadores.
    Seção 5.6 — Detecção multi-pessoa.
    """
    if len(people) < 2:
        return frame

    warnings = compute_interperson_distances(people)
    for w in warnings:
        ci = w["center_i"]; cj = w["center_j"]
        col = (0, 0, 220) if w["severity"] == "high" else (20, 160, 248)
        thick = max(2, int(2 * S))
        cv2.line(frame, ci, cj, col, thick, cv2.LINE_AA)
        mx, my = (ci[0]+cj[0])//2, (ci[1]+cj[1])//2
        dist_txt = f"{w['dist_m']:.1f}m"
        sz = 0.45 * S
        (tw, th), _ = cv2.getTextSize(dist_txt, cv2.FONT_HERSHEY_SIMPLEX, sz, 1)
        cv2.rectangle(frame, (mx-tw//2-4, my-th-4), (mx+tw//2+4, my+4), col, -1)
        cv2.putText(frame, dist_txt, (mx-tw//2, my),
                    cv2.FONT_HERSHEY_SIMPLEX, sz, (255,255,255), 1, cv2.LINE_AA)
    return frame
