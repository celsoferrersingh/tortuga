"""
gui.py — Tortuga PPE Monitor  v3.2
Interface profissional — Fase 1 (EPIs) + Fase 2 (Pose + RULA/REBA).
Uso  : python gui.py [--camera 0] [--confidence 0.4] [--no-pose]
Teclas: ESPACO pausa  |  Q / ESC sai  |  P toggle pose  |  S session report
"""
from __future__ import annotations
import argparse, os, sys, threading, time, math, queue
import cv2, numpy as np

os.environ["YOLO_OFFLINE"]        = "1"
os.environ["ULTRALYTICS_OFFLINE"] = "1"
os.environ["YOLO_AUTOINSTALL"]    = "0"
try:
    from ultralytics import settings as _us
    _us.update({"sync": False})
except Exception:
    pass

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from detector import PPEDetector
try:
    from pose_estimator import (
        PoseEstimator, render_pose_overlay, render_danger_zones,
        render_distance_warnings,
        POSTURE_SAFE, POSTURE_IMMEDIATE, POSTURE_ZONE, POSTURE_ERGONOMIC,
        POSTURE_LABELS, POSE_COLOR, _rula_color,
    )
    _POSE_AVAILABLE = True
except Exception as _pe:
    _POSE_AVAILABLE = False
    print(f"  [AVISO] Pose estimation indisponivel: {_pe}")


# ───────────────────────────────────────────────────────────
#  SCREEN SIZE
# ───────────────────────────────────────────────────────────
def _screen_size() -> tuple[int, int]:
    try:
        import Quartz
        d = Quartz.CGDisplayBounds(Quartz.CGMainDisplayID())
        return int(d.size.width), int(d.size.height)
    except Exception: pass
    try:
        import ctypes
        u32 = ctypes.windll.user32
        u32.SetProcessDPIAware()
        return u32.GetSystemMetrics(0), u32.GetSystemMetrics(1)
    except Exception: pass
    try:
        import subprocess
        out = subprocess.check_output(["xrandr"], stderr=subprocess.DEVNULL, text=True, timeout=3)
        for line in out.splitlines():
            if "current" in line:
                p = line.split("current")[1].split(",")[0].split("x")
                return int(p[0].strip()), int(p[1].strip())
    except Exception: pass
    return 1440, 900


# ───────────────────────────────────────────────────────────
#  PALETA  (BGR)
# ───────────────────────────────────────────────────────────
BG      = ( 10,  11,  14)
PANEL   = ( 18,  20,  26)
CARD    = ( 28,  31,  40)
CARD_HL = ( 38,  42,  55)
BORDER  = ( 50,  55,  72)
BORDER2 = ( 70,  76,  98)
WHITE   = (255, 255, 255)
TEXT    = (225, 228, 238)
MUTED   = ( 95, 102, 120)
MUTED2  = (140, 148, 168)
ACCENT  = ( 28, 138, 255)
GREEN   = ( 48, 195,  68)
RED     = ( 48,  55, 225)
AMBER   = ( 20, 160, 248)
BLUE    = (215, 128,  22)
PURPLE  = (195,  78, 168)
TEAL    = (175, 185,  52)
ORANGE  = ( 20, 100, 248)

EPI_LIST = ["Hardhat", "Mask", "Safety Vest", "Safety Glasses"]
EPI_PT   = {"Hardhat":"Capacete", "Mask":"Mascara",
            "Safety Vest":"Colete", "Safety Glasses":"Oculos"}
EPI_COL  = {"Hardhat":BLUE, "Mask":PURPLE,
            "Safety Vest":AMBER, "Safety Glasses":TEAL}

FONT  = cv2.FONT_HERSHEY_DUPLEX
FONT2 = cv2.FONT_HERSHEY_SIMPLEX


# ───────────────────────────────────────────────────────────
#  PRIMITIVOS
# ───────────────────────────────────────────────────────────
def blend(img, x1, y1, x2, y2, color, a):
    x1,y1=max(0,x1),max(0,y1)
    x2,y2=min(img.shape[1],x2),min(img.shape[0],y2)
    if x2<=x1 or y2<=y1: return
    roi=img[y1:y2,x1:x2]
    cv2.addWeighted(np.full_like(roi,color),a,roi,1-a,0,roi)
    img[y1:y2,x1:x2]=roi

def rrect(img,x1,y1,x2,y2,r,color,fill=True,t=1,a=1.0):
    if x2<=x1 or y2<=y1: return
    if a<1.0:
        tmp=img.copy(); _rr(tmp,x1,y1,x2,y2,r,color,fill,max(1,t))
        cv2.addWeighted(tmp,a,img,1-a,0,img)
    else:
        _rr(img,x1,y1,x2,y2,r,color,fill,max(1,t))

def _rr(img,x1,y1,x2,y2,r,color,fill,t):
    r=max(1,min(r,(x2-x1)//2,(y2-y1)//2))
    if fill:
        cv2.rectangle(img,(x1+r,y1),(x2-r,y2),color,-1)
        cv2.rectangle(img,(x1,y1+r),(x2,y2-r),color,-1)
        for cx,cy in [(x1+r,y1+r),(x2-r,y1+r),(x1+r,y2-r),(x2-r,y2-r)]:
            cv2.circle(img,(cx,cy),r,color,-1)
    else:
        cv2.line(img,(x1+r,y1),(x2-r,y1),color,t)
        cv2.line(img,(x1+r,y2),(x2-r,y2),color,t)
        cv2.line(img,(x1,y1+r),(x1,y2-r),color,t)
        cv2.line(img,(x2,y1+r),(x2,y2-r),color,t)
        for cx,cy,a0,a1 in [(x1+r,y1+r,180,270),(x2-r,y1+r,270,360),
                             (x1+r,y2-r,90,180),(x2-r,y2-r,0,90)]:
            cv2.ellipse(img,(cx,cy),(r,r),0,a0,a1,color,t)

def T(img,text,x,y,sz=0.55,color=TEXT,bold=False,align="l",font=FONT):
    t=2 if bold else 1
    (w,h),_=cv2.getTextSize(text,font,sz,t)
    if align=="r": x-=w
    elif align=="c": x-=w//2
    cv2.putText(img,text,(x+1,y+h+1),font,sz,(0,0,0),t+1,cv2.LINE_AA)
    cv2.putText(img,text,(x,y+h),font,sz,color,t,cv2.LINE_AA)
    return w,h

def hline(img,y,x1=None,x2=None,color=BORDER,t=1):
    W=img.shape[1]
    cv2.line(img,(x1 or 0,y),(x2 or W,y),color,t)

def vline(img,x,y1=0,y2=None,color=BORDER,t=1):
    H=img.shape[0]
    cv2.line(img,(x,y1),(x,y2 or H),color,t)

def toggle_sw(img,cx,cy,on,color,scale=1.0):
    w,h=int(50*scale),int(26*scale)
    x1,y1=cx-w//2,cy-h//2
    x2,y2=cx+w//2,cy+h//2
    rrect(img,x1,y1,x2,y2,h//2,color if on else CARD_HL)
    rrect(img,x1,y1,x2,y2,h//2,color if on else BORDER2,fill=False,t=2)
    kx=x2-h//2-2 if on else x1+h//2+2
    cv2.circle(img,(kx,cy),h//2-2,(230,235,245),-1)
    cv2.circle(img,(kx,cy),h//2-2,(180,185,200),1)
    if on:
        cv2.circle(img,(kx,cy),h//2-5,color,-1)

def corner_box(img,x1,y1,x2,y2,color,t=3,ln=22):
    H,W=img.shape[:2]
    x1,y1=max(0,x1),max(0,y1)
    x2,y2=min(W-1,x2),min(H-1,y2)
    ln=min(ln,abs(x2-x1)//3,abs(y2-y1)//3)
    for (ax,ay),(bx,by),(cx2,cy2) in [
        ((x1,y1+ln),(x1,y1),(x1+ln,y1)),
        ((x2-ln,y1),(x2,y1),(x2,y1+ln)),
        ((x1,y2-ln),(x1,y2),(x1+ln,y2)),
        ((x2-ln,y2),(x2,y2),(x2,y2-ln)),
    ]:
        cv2.line(img,(ax,ay),(bx,by),color,t,cv2.LINE_AA)
        cv2.line(img,(bx,by),(cx2,cy2),color,t,cv2.LINE_AA)

def det_label(img,x1,y1,x2,y2,name,conf,color):
    text=f" {name}  {conf:.0%} "
    sz=0.52; t=1
    (tw,th),_=cv2.getTextSize(text,FONT,sz,t)
    pad=6
    ly2=max(th+pad*2,y1); ly1=max(0,ly2-th-pad*2)
    lx1=max(0,x1); lx2=min(img.shape[1]-1,lx1+tw+pad)
    rrect(img,lx1,ly1,lx2,ly2,5,color)
    rrect(img,lx1,ly1,lx2,ly2,5,WHITE,fill=False,t=1,a=0.3)
    cv2.putText(img,text,(lx1+2,ly2-pad),FONT,sz,(255,255,255),t,cv2.LINE_AA)


# ───────────────────────────────────────────────────────────
#  SIDEBAR
# ───────────────────────────────────────────────────────────
class Sidebar:
    def __init__(self, width:int, height:int):
        self.W = width; self.H = height
        self.SC = width / 300.0
        self.states      = {e:True for e in EPI_LIST}
        self.confidence  = 0.4
        self.has_glasses = False
        # Fase 2
        self.pose_enabled  = _POSE_AVAILABLE
        self.pose_status   = POSTURE_SAFE if _POSE_AVAILABLE else "unavailable"
        self.pose_details  : list[str] = []
        self.n_people      = 0
        self.worst_rula    = 0
        self.worst_reba    = 0
        self.temporal_flags: list[str] = []
        self.dist_warnings  = 0
        self._toggles: dict[str,tuple] = {}
        self._cbar     = (0,0,0,0)
        self._drag     = False
        self._n_viol   = 0
        self._t0       = time.time()
        self._last_vt  = 0.0
        self._cache: np.ndarray|None = None
        self._cache_key = None

    def required(self): return [e for e,v in self.states.items() if v]

    def tick(self, has_v):
        if has_v:
            now = time.time()
            if now - self._last_vt > 2.0:
                self._n_viol += 1; self._last_vt = now

    def update_pose(self, pose_status:str, details:list, n_people:int,
                    worst_rula:int=0, worst_reba:int=0,
                    temporal_flags:list|None=None, dist_warnings:int=0):
        changed = (pose_status != self.pose_status
                   or n_people != self.n_people
                   or worst_rula != self.worst_rula
                   or details != self.pose_details)
        if changed:
            self.pose_status    = pose_status
            self.pose_details   = details
            self.n_people       = n_people
            self.worst_rula     = worst_rula
            self.worst_reba     = worst_reba
            self.temporal_flags = temporal_flags or []
            self.dist_warnings  = dist_warnings
            self.invalidate()

    def invalidate(self): self._cache_key = None

    def _key(self, fps, has_v, viols, fn):
        return (tuple(self.states.values()), round(self.confidence,2),
                has_v, tuple(viols[:1]), fn//12,
                self.pose_status, self.n_people,
                self.pose_enabled, self.worst_rula, self.dist_warnings)

    def render(self, fps, has_v, viols, fn) -> np.ndarray:
        key = self._key(fps, has_v, viols, fn)
        if key == self._cache_key and self._cache is not None:
            return self._cache

        W,H,S = self.W, self.H, self.SC
        img = np.full((H,W,3), PANEL, dtype=np.uint8)
        self._toggles.clear()
        P = int(18*S)

        # ══ HEADER ══════════════════════════════════════════
        cv2.rectangle(img,(0,0),(W,int(72*S)),BG,-1)
        hline(img,int(72*S),color=BORDER2,t=2)
        T(img,"TORTUGA",P,int(10*S),sz=0.82*S,color=ACCENT,bold=True)
        T(img,"PPE Safety Monitor",P,int(38*S),sz=0.40*S,color=MUTED2)
        fc=GREEN if fps>=20 else AMBER if fps>=10 else RED
        bw,bh=int(64*S),int(38*S)
        bx1,by1=W-P-bw,int(17*S)
        rrect(img,bx1,by1,bx1+bw,by1+bh,int(8*S),CARD_HL)
        rrect(img,bx1,by1,bx1+bw,by1+bh,int(8*S),fc,fill=False,t=2)
        T(img,str(int(fps)),bx1+bw//2,by1+int(2*S),sz=0.72*S,color=fc,bold=True,align="c")
        T(img,"FPS",bx1+bw//2,by1+int(22*S),sz=0.30*S,color=fc,align="c")

        y = int(80*S)

        # ══ STATUS CARD — EPI ════════════════════════════════
        sc = RED if has_v else GREEN
        sh = int(80*S)
        blend(img,P,y,W-P,y+sh,sc,0.12)
        rrect(img,P,y,W-P,y+sh,int(12*S),sc,fill=False,t=3)
        pulse = abs(math.sin(fn*0.07))
        dr = int((7+3*pulse)*S) if has_v else int(7*S)
        cx_dot=P+int(22*S); cy_dot=y+int(26*S)
        cv2.circle(img,(cx_dot,cy_dot),dr+int(4*S),sc,2)
        cv2.circle(img,(cx_dot,cy_dot),dr,sc,-1)
        tx=P+int(40*S)
        T(img,"VIOLACAO DETECTADA" if has_v else "AREA SEGURA",
          tx,y+int(8*S),sz=0.58*S,color=sc,bold=True)
        sub = viols[0][:32] if viols else "Todos os EPIs presentes"
        T(img,sub,tx,y+int(36*S),sz=0.38*S,color=MUTED2)
        if len(viols)>1:
            T(img,f"+{len(viols)-1} alertas",tx,y+int(56*S),sz=0.32*S,color=MUTED)
        y += sh+int(12*S)

        # ══ EPIs ═════════════════════════════════════════════
        sec_h = int(20*S)
        hline(img,y+int(10*S),P,W-P,BORDER2,t=1)
        rrect(img,P+int(6*S),y+int(2*S),P+int(6*S)+int(130*S),y+sec_h,int(4*S),CARD)
        T(img,"  EPIs Obrigatorios",P+int(10*S),y+int(3*S),sz=0.33*S,color=MUTED2)
        y += sec_h+int(4*S)

        card_h = int(58*S)
        for epi in EPI_LIST:
            on=self.states[epi]; ec=EPI_COL[epi]
            una=(epi=="Safety Glasses" and not self.has_glasses)
            rrect(img,P,y,W-P,y+card_h,int(10*S),CARD_HL if on else CARD)
            if on and not una:
                rrect(img,P,y,W-P,y+card_h,int(10*S),ec,fill=False,t=2,a=0.5)
                cv2.rectangle(img,(P,y+int(10*S)),(P+int(4*S),y+card_h-int(10*S)),ec,-1)
            dc=ec if (on and not una) else BORDER2
            cv2.circle(img,(P+int(22*S),y+card_h//2),int(8*S),dc,-1)
            if on and not una:
                cv2.circle(img,(P+int(22*S),y+card_h//2),int(4*S),PANEL,-1)
            lc=ec if (on and not una) else MUTED2
            T(img,EPI_PT[epi],P+int(38*S),y+int(8*S),sz=0.55*S,color=lc,bold=on and not una)
            T(img,epi,P+int(38*S),y+int(34*S),sz=0.33*S,color=MUTED)
            if una:
                rx1,ry1=W-P-int(88*S),y+int(16*S)
                rrect(img,rx1,ry1,rx1+int(80*S),ry1+int(26*S),int(6*S),AMBER,fill=False,t=2)
                T(img,"Retreinar",rx1+int(40*S),ry1+int(4*S),sz=0.33*S,color=AMBER,align="c")
            else:
                tcx=W-P-int(32*S); tcy=y+card_h//2
                toggle_sw(img,tcx,tcy,on,ec,S)
                self._toggles[epi]=(tcx,tcy)
            y += card_h+int(6*S)

        # ══ POSE ESTIMATION — Fase 2 ═════════════════════════
        y += int(6*S)
        hline(img,y+int(10*S),P,W-P,BORDER2)
        rrect(img,P+int(6*S),y+int(2*S),P+int(6*S)+int(150*S),y+sec_h,int(4*S),CARD)
        T(img,"  Pose + Ergonomia",P+int(10*S),y+int(3*S),sz=0.33*S,color=MUTED2)
        y += sec_h+int(4*S)

        if not _POSE_AVAILABLE:
            rrect(img,P,y,W-P,y+int(42*S),int(8*S),CARD)
            T(img,"Modulo indisponivel",P+int(12*S),y+int(6*S),sz=0.38*S,color=MUTED)
            T(img,"pip install ultralytics",P+int(12*S),y+int(26*S),sz=0.30*S,color=MUTED)
            y += int(48*S)
        else:
            ps = self.pose_status
            pc = POSE_COLOR.get(ps,(200,200,0))

            # Card de status de postura
            ph_card = int(60*S)
            blend(img,P,y,W-P,y+ph_card,pc,0.10)
            rrect(img,P,y,W-P,y+ph_card,int(10*S),pc,fill=False,t=2,a=0.7)
            dp = abs(math.sin(fn*0.07))
            dr2 = int((6+2*dp)*S) if ps!=POSTURE_SAFE else int(6*S)
            cv2.circle(img,(P+int(20*S),y+int(20*S)),dr2+int(3*S),pc,2)
            cv2.circle(img,(P+int(20*S),y+int(20*S)),dr2,pc,-1)
            lbl = POSTURE_LABELS.get(ps,"Analisando...")
            T(img,lbl,P+int(36*S),y+int(6*S),sz=0.48*S,color=pc,bold=(ps!=POSTURE_SAFE))
            T(img,f"{self.n_people} pessoa(s) em cena",
              P+int(36*S),y+int(30*S),sz=0.32*S,color=MUTED2)
            # Toggle
            tcx2=W-P-int(32*S); tcy2=y+ph_card//2
            toggle_sw(img,tcx2,tcy2,self.pose_enabled,TEAL if self.pose_enabled else BORDER2,S)
            self._toggles["_pose"] = ("pose",(tcx2,tcy2))
            y += ph_card+int(4*S)

            # RULA / REBA badges
            if self.worst_rula > 0:
                rula_c = _rula_color(self.worst_rula)
                reba_c = _rula_color(max(1, self.worst_reba // 2))
                badge_h = int(36*S)
                cw = (W-P*2)//2
                # RULA badge
                rx1=P; rx2=P+cw-int(4*S)
                rrect(img,rx1,y,rx2,y+badge_h,int(7*S),CARD)
                cv2.rectangle(img,(rx1,y+badge_h-int(4*S)),(rx2,y+badge_h),rula_c,-1)
                T(img,f"RULA {self.worst_rula}/7",rx1+(rx2-rx1)//2,y+int(2*S),
                  sz=0.45*S,color=rula_c,bold=True,align="c")
                # REBA badge
                bx1_r=P+cw; bx2_r=W-P
                rrect(img,bx1_r,y,bx2_r,y+badge_h,int(7*S),CARD)
                cv2.rectangle(img,(bx1_r,y+badge_h-int(4*S)),(bx2_r,y+badge_h),reba_c,-1)
                T(img,f"REBA {self.worst_reba}/15",bx1_r+(bx2_r-bx1_r)//2,y+int(2*S),
                  sz=0.45*S,color=reba_c,bold=True,align="c")
                y += badge_h+int(4*S)

            # Alertas temporais + distância
            flag_items = []
            if "repetition" in self.temporal_flags:
                flag_items.append(("REP", AMBER))
            if "fatigue" in self.temporal_flags:
                flag_items.append(("FAD", ORANGE))
            if "fall_predicted" in self.temporal_flags:
                flag_items.append(("QUEDA!", RED))
            if self.dist_warnings > 0:
                flag_items.append((f"DIST x{self.dist_warnings}", RED))
            if flag_items:
                fw = (W-P*2)//max(len(flag_items),1)
                for fi,(ftxt,fc2) in enumerate(flag_items):
                    fx1=P+fi*fw; fx2=fx1+fw-int(3*S)
                    rrect(img,fx1,y,fx2,y+int(24*S),int(5*S),CARD)
                    rrect(img,fx1,y,fx2,y+int(24*S),int(5*S),fc2,fill=False,t=2)
                    T(img,ftxt,fx1+(fx2-fx1)//2,y+int(3*S),
                      sz=0.32*S,color=fc2,bold=True,align="c")
                y += int(30*S)

            # Primeiro detalhe de risco
            if self.pose_details:
                det_txt = self.pose_details[0][:30]
                T(img,det_txt,P,y,sz=0.30*S,color=MUTED2)
                y += int(18*S)

        # ══ SENSIBILIDADE ════════════════════════════════════
        y += int(4*S)
        hline(img,y+int(10*S),P,W-P,BORDER2)
        rrect(img,P+int(6*S),y+int(2*S),P+int(6*S)+int(110*S),y+sec_h,int(4*S),CARD)
        T(img,"  Sensibilidade",P+int(10*S),y+int(3*S),sz=0.33*S,color=MUTED2)
        y += sec_h+int(4*S)
        T(img,"Confianca minima",P,y,sz=0.44*S,color=TEXT)
        T(img,f"{self.confidence:.0%}",W-P,y,sz=0.50*S,color=ACCENT,bold=True,align="r")
        y += int(26*S)
        bx1,bx2=P,W-P; ty=y+int(6*S); th=int(10*S)
        rrect(img,bx1,ty,bx2,ty+th,th//2,CARD)
        fx=int(bx1+(bx2-bx1)*(self.confidence-0.1)/0.8)
        if fx>bx1+2:
            rrect(img,bx1,ty,fx,ty+th,th//2,ACCENT)
        tr=int(13*S)
        cv2.circle(img,(fx,ty+th//2),tr+2,BG,-1)
        cv2.circle(img,(fx,ty+th//2),tr,ACCENT,-1)
        cv2.circle(img,(fx,ty+th//2),int(5*S),WHITE,-1)
        self._cbar=(bx1,ty-int(10*S),bx2,ty+th+int(10*S))
        y+=th+int(18*S)
        T(img,"10%",bx1,y,sz=0.30*S,color=MUTED)
        T(img,"50%",W//2,y,sz=0.30*S,color=MUTED,align="c")
        T(img,"90%",bx2,y,sz=0.30*S,color=MUTED,align="r")
        y+=int(18*S)

        # ══ STATS ════════════════════════════════════════════
        y+=int(8*S)
        hline(img,y+int(10*S),P,W-P,BORDER2)
        rrect(img,P+int(6*S),y+int(2*S),P+int(6*S)+int(74*S),y+sec_h,int(4*S),CARD)
        T(img,"  Sessao",P+int(10*S),y+int(3*S),sz=0.33*S,color=MUTED2)
        y += sec_h+int(4*S)
        ut=int(time.time()-self._t0)
        ustr=f"{ut//3600:02d}:{(ut%3600)//60:02d}:{ut%60:02d}"
        cw2=(W-P*2)//2
        for i,(lb,val,vc) in enumerate([
            ("Violacoes",str(self._n_viol),RED if self._n_viol else MUTED2),
            ("Uptime",ustr,MUTED2),
        ]):
            sx=P+i*cw2; ch=int(56*S)
            rrect(img,sx+int(3*S),y,sx+cw2-int(3*S),y+ch,int(8*S),CARD)
            T(img,val,sx+cw2//2,y+int(4*S),sz=0.65*S,color=vc,bold=True,align="c")
            T(img,lb,sx+cw2//2,y+ch-int(20*S),sz=0.32*S,color=MUTED,align="c")
        y+=int(62*S)

        # ══ FOOTER ═══════════════════════════════════════════
        fy=H-int(44*S)
        hline(img,fy,color=BORDER2,t=1)
        shortcuts=[("ESPACO","Pausar"),("Q/ESC","Sair"),("P","Pose"),("S","Relatorio")]
        for i,(k,d) in enumerate(shortcuts[:3]):
            fx2=P+i*int(90*S)
            rrect(img,fx2,fy+int(8*S),fx2+int(46*S),fy+int(30*S),int(5*S),CARD_HL)
            rrect(img,fx2,fy+int(8*S),fx2+int(46*S),fy+int(30*S),int(5*S),BORDER2,fill=False,t=1)
            T(img,k,fx2+int(23*S),fy+int(10*S),sz=0.28*S,color=ACCENT,align="c")
            T(img,d,fx2+int(50*S),fy+int(14*S),sz=0.30*S,color=MUTED2)

        vline(img,0,color=BORDER2,t=2)
        self._cache=img; self._cache_key=key
        return img

    def click(self,sx,sy):
        for key,val in self._toggles.items():
            if isinstance(val,tuple) and len(val)==2 and isinstance(val[0],str):
                tag,(cx,cy)=val
                if abs(sx-cx)<int(30*self.SC) and abs(sy-cy)<int(18*self.SC):
                    if tag=="pose": self.pose_enabled=not self.pose_enabled
                    self.invalidate(); return True
            else:
                cx,cy=val
                if abs(sx-cx)<int(30*self.SC) and abs(sy-cy)<int(18*self.SC):
                    self.states[key]=not self.states[key]; self.invalidate(); return True
        bx1,by1,bx2,by2=self._cbar
        if bx1<=sx<=bx2 and by1<=sy<=by2:
            self._drag=True; self._setc(sx); self.invalidate(); return True
        return False

    def drag(self,sx,sy):
        if self._drag: self._setc(sx); self.invalidate()

    def _setc(self,sx):
        bx1,_,bx2,_=self._cbar
        r=max(0.,min(1.,(sx-bx1)/max(bx2-bx1,1)))
        self.confidence=round(0.1+r*0.8,2)

    def stop(self): self._drag=False


# ───────────────────────────────────────────────────────────
#  CAMERA OVERLAY
# ───────────────────────────────────────────────────────────
def render_cam(frame, dets, has_v, fps, paused, fn, W, H,
               people=None, pose_enabled=True, danger_zones=None):
    h_orig,w_orig=frame.shape[:2]
    out=cv2.resize(frame,(W,H),interpolation=cv2.INTER_LINEAR)
    S=H/480.0
    rx,ry=W/max(w_orig,1),H/max(h_orig,1)

    # Zonas de perigo (EPC)
    if _POSE_AVAILABLE and danger_zones:
        render_danger_zones(out, danger_zones)

    # Esqueleto + RULA + alertas temporais
    if _POSE_AVAILABLE and pose_enabled and people:
        scaled_people = []
        for person in people:
            kp = person["keypoints"].copy()
            kp[:,0] *= rx; kp[:,1] *= ry
            p2 = dict(person); p2["keypoints"] = kp
            # Escala bbox também
            if p2.get("bbox"):
                x1,y1,x2,y2=p2["bbox"]
                p2["bbox"]=(int(x1*rx),int(y1*ry),int(x2*rx),int(y2*ry))
            scaled_people.append(p2)
        render_pose_overlay(out, scaled_people, S)
        # Linhas de distância multi-pessoa
        render_distance_warnings(out, scaled_people, S)

    # Bounding boxes EPI
    for d in dets:
        x1,y1,x2,y2=d["bbox"]; c=d["color"]
        x1s,y1s,x2s,y2s=int(x1*rx),int(y1*ry),int(x2*rx),int(y2*ry)
        blend(out,x1s,y1s,x2s,y2s,c,0.08)
        corner_box(out,x1s,y1s,x2s,y2s,c,t=max(2,int(3*S)),ln=int(22*S))
        det_label(out,x1s,y1s,x2s,y2s,d["class_name"],d["confidence"],c)

    # Top bar
    bar_h=int(58*S)
    blend(out,0,0,W,bar_h,RED if has_v else BG,0.85)
    cv2.line(out,(0,bar_h),(W,bar_h),RED if has_v else BORDER2,2)

    pose_immediate = (_POSE_AVAILABLE and people and
                      any(p.get("is_immediate") or p.get("is_zone") for p in (people or [])))
    has_any_alert  = has_v or pose_immediate

    if has_any_alert:
        pulse=abs(math.sin(fn*0.1)); dr=int((6+3*pulse)*S)
        cv2.circle(out,(int(20*S),bar_h//2),dr+int(4*S),RED,-1)
        cv2.circle(out,(int(20*S),bar_h//2),dr,(100,100,240),-1)
        if has_v and pose_immediate:
            msg="ALERTA: EPI + RISCO DE POSTURA"
        elif has_v:
            msg="ALERTA: VIOLACAO DE EPI"
        else:
            msg="ALERTA: RISCO DE POSTURA DETECTADO"
        T(out,msg,int(38*S),int(10*S),sz=0.68*S,color=(225,228,255),bold=True)
    else:
        cv2.circle(out,(int(20*S),bar_h//2),int(9*S),GREEN,-1)
        cv2.circle(out,(int(20*S),bar_h//2),int(5*S),BG,-1)
        n_str=f"  {len(people)} pessoa(s)" if people else ""
        T(out,f"AREA MONITORADA  —  SEGURO{n_str}",int(38*S),int(12*S),
          sz=0.60*S,color=TEXT)

    # FPS
    fc=GREEN if fps>=20 else AMBER if fps>=10 else RED
    T(out,f"{int(fps)} FPS",W-int(14*S),int(14*S),sz=0.50*S,color=fc,bold=True,align="r")

    # Timestamp
    ts=time.strftime("%Y-%m-%d  %H:%M:%S")
    blend(out,0,H-int(32*S),int(220*S),H,BG,0.70)
    T(out,ts,int(10*S),H-int(22*S),sz=0.38*S,color=MUTED2)
    T(out,"TORTUGA PPE Monitor",W-int(14*S),H-int(22*S),sz=0.36*S,color=MUTED,align="r")

    if paused:
        blend(out,0,0,W,H,BG,0.60)
        pw,ph=int(180*S),int(60*S)
        px,py=W//2-pw//2,H//2-ph//2
        rrect(out,px,py,px+pw,py+ph,int(14*S),CARD,a=0.96)
        rrect(out,px,py,px+pw,py+ph,int(14*S),ACCENT,fill=False,t=3)
        T(out,"PAUSADO",W//2,py+int(14*S),sz=0.75*S,color=ACCENT,bold=True,align="c")

    return out


# ───────────────────────────────────────────────────────────
#  PIPELINE DE DETECCAO
# ───────────────────────────────────────────────────────────
class DetectionPipeline:
    def __init__(self, camera, detector:PPEDetector, pose_estimator=None):
        self.det=detector; self._cam=camera
        self._pose=pose_estimator
        self._run=True; self._pause=False
        self._raw_q: queue.Queue = queue.Queue(maxsize=2)
        self._pose_q:queue.Queue = queue.Queue(maxsize=2)
        self._result = {"frame":None,"dets":[],"hv":False,"vd":[],
                        "people":[],"pose_risk":False,"pose_details":[]}
        self._rlock  = threading.Lock()
        self._ft:list[float]=[]; self._flock=threading.Lock()
        threading.Thread(target=self._capture,    daemon=True,name="cap").start()
        threading.Thread(target=self._detect_epi, daemon=True,name="det_epi").start()
        if self._pose:
            threading.Thread(target=self._detect_pose,daemon=True,name="det_pose").start()

    def _capture(self):
        cap=cv2.VideoCapture(self._cam)
        cap.set(cv2.CAP_PROP_BUFFERSIZE,1)
        while self._run:
            if self._pause: time.sleep(0.02); continue
            ok,f=cap.read()
            if not ok: time.sleep(0.02); continue
            now=time.time()
            with self._flock:
                self._ft.append(now)
                self._ft=[t for t in self._ft if now-t<1.0]
            if self._raw_q.full():
                try: self._raw_q.get_nowait()
                except queue.Empty: pass
            try: self._raw_q.put_nowait(f)
            except queue.Full: pass
            if self._pose:
                if self._pose_q.full():
                    try: self._pose_q.get_nowait()
                    except queue.Empty: pass
                try: self._pose_q.put_nowait(f.copy())
                except queue.Full: pass
        cap.release()

    def _detect_epi(self):
        while self._run:
            try: f=self._raw_q.get(timeout=0.1)
            except queue.Empty: continue
            h,w=f.shape[:2]; sc=320/max(h,w)
            sm=cv2.resize(f,(int(w*sc),int(h*sc))) if sc<1 else f
            d=self.det.detect(sm)
            if sc<1:
                for x in d:
                    a,b,c,e=x["bbox"]
                    x["bbox"]=(int(a/sc),int(b/sc),int(c/sc),int(e/sc))
            with self._rlock:
                self._result["frame"]=f
                self._result["dets"]=d
                self._result["hv"]=self.det.has_violations(d)
                self._result["vd"]=self.det.get_violation_summary(d)

    def _detect_pose(self):
        while self._run:
            try: f=self._pose_q.get(timeout=0.1)
            except queue.Empty: continue
            people=self._pose.detect(f)
            pr=self._pose.has_immediate_risk(people)
            pd=self._pose.get_risk_summary(people)
            with self._rlock:
                self._result["people"]      = people
                self._result["pose_risk"]   = pr
                self._result["pose_details"]= pd

    def get(self, required_epis):
        with self._flock: fps=len(self._ft)
        with self._rlock: r=dict(self._result)
        r["dets"]=PPEDetector.filter_by_station(r["dets"],required_epis)
        r["hv"]=any(d["is_violation"] for d in r["dets"])
        r["vd"]=[f"{d['class_name']} ({d['confidence']:.0%})"
                 for d in r["dets"] if d["is_violation"]]
        r["fps"]=fps; return r

    @property
    def paused(self): return self._pause
    @paused.setter
    def paused(self,v): self._pause=v
    def stop(self): self._run=False


# ───────────────────────────────────────────────────────────
#  APP
# ───────────────────────────────────────────────────────────
class App:
    def __init__(self, camera, model_path, confidence, enable_pose=True):
        print("\n  Tortuga PPE Monitor  v3.2  (Fase 1 + Fase 2)")
        print("  Carregando modelos...")
        self.det=PPEDetector(model_path, confidence=confidence)

        self._pose_est=None
        if enable_pose and _POSE_AVAILABLE:
            try:
                self._pose_est=PoseEstimator(model_path="yolov8n-pose.pt",
                                             confidence=0.30)
                print("  Pose Estimation: OK  (RULA + REBA + Temporal + Multi-pessoa)")
            except Exception as e:
                print(f"  Pose Estimation: indisponivel ({e})")
        print("  Pronto!\n")

        sw,sh=_screen_size()
        SIDE_W=max(300,sw//4)
        CAM_W =sw-SIDE_W; CAM_H=sh-40
        self._cw,self._ch,self._sw=CAM_W,CAM_H,SIDE_W
        self._total_w=sw; self._total_h=CAM_H

        self.sb=Sidebar(SIDE_W,CAM_H)
        self.sb.confidence  =confidence
        self.sb.has_glasses =any("glass" in n.lower()
                                 for n in self.det._class_names.values())
        self.sb.pose_enabled=(self._pose_est is not None)
        self.pipe=DetectionPipeline(camera,self.det,self._pose_est)
        self._fn=0

    def _mouse(self,event,mx,my,flags,_):
        sx=mx-self._cw
        if sx<0: return
        if event==cv2.EVENT_LBUTTONDOWN:
            if self.sb.click(sx,my): self.det.confidence=self.sb.confidence
        elif event==cv2.EVENT_MOUSEMOVE and flags&cv2.EVENT_FLAG_LBUTTON:
            self.sb.drag(sx,my); self.det.confidence=self.sb.confidence
        elif event==cv2.EVENT_LBUTTONUP:
            self.sb.stop()

    def _print_session_report(self):
        """Imprime relatório ergonômico SSMA no console (tecla S)."""
        if not self._pose_est: return
        print("\n" + "="*55)
        print("  RELATORIO ERGONOMICO DE SESSAO — SSMA")
        print("  (sem identidade individual)")
        print("="*55)
        summary = self._pose_est.get_session_summary()
        if not summary:
            print("  Nenhum dado disponivel ainda.")
        for s in summary:
            print(f"\n  Operador {s['worker_id']}")
            print(f"    RULA medio:    {s['avg_rula']:.2f}/7")
            print(f"    RULA maximo:   {s['max_rula']}/7")
            print(f"    Frames risco:  {s['frames_high']}")
            print(f"    Acao recomend: {s['action']}")
        print("="*55+"\n")

    def run(self):
        win="Tortuga - PPE Monitor"
        cv2.namedWindow(win,cv2.WINDOW_NORMAL)
        cv2.resizeWindow(win,self._total_w,self._total_h)
        cv2.moveWindow(win,0,0)
        cv2.setMouseCallback(win,self._mouse)

        ph=np.full((self._ch,self._cw,3),BG,dtype=np.uint8)
        T(ph,"Aguardando camera...",self._cw//2,self._ch//2-14,
          sz=0.65,color=MUTED,align="c")

        while True:
            self._fn+=1
            r=self.pipe.get(self.sb.required())
            f=r["frame"]; hv=r["hv"]; vd=r["vd"]; fps=r["fps"]; dets=r["dets"]
            people   =r.get("people",[])
            pose_risk=r.get("pose_risk",False)
            pose_det =r.get("pose_details",[])
            self.sb.tick(hv or pose_risk)

            # Extrai métricas agregadas para sidebar
            worst_rula = 0; worst_reba = 0
            temporal_flags: list[str] = []
            dist_warnings = 0

            if people:
                worst_st = POSTURE_SAFE
                for p in people:
                    worst_rula = max(worst_rula, p.get("rula_score", 0))
                    worst_reba = max(worst_reba, p.get("reba_score", 0))
                    tmp = p.get("temporal", {})
                    if tmp.get("fall_predicted"): temporal_flags.append("fall_predicted")
                    if tmp.get("repetition"):     temporal_flags.append("repetition")
                    if tmp.get("fatigue"):         temporal_flags.append("fatigue")
                    if p.get("is_immediate") or p.get("is_zone"):
                        worst_st = POSTURE_IMMEDIATE
                    elif p.get("is_ergonomic") and worst_st != POSTURE_IMMEDIATE:
                        worst_st = POSTURE_ERGONOMIC

                from pose_estimator import compute_interperson_distances
                dist_warnings = len(compute_interperson_distances(people))
                if dist_warnings > 0:
                    temporal_flags.append("dist")

                self.sb.update_pose(worst_st, pose_det, len(people),
                                    worst_rula, worst_reba,
                                    temporal_flags, dist_warnings)
            else:
                self.sb.update_pose(POSTURE_SAFE,[],0)

            if self._pose_est:
                self._pose_est.set_danger_zones([])

            cam=render_cam(
                f if f is not None else ph,
                dets, hv, fps, self.pipe.paused, self._fn,
                self._cw, self._ch,
                people=people if self.sb.pose_enabled else [],
                pose_enabled=self.sb.pose_enabled,
                danger_zones=self._pose_est.danger_zones if self._pose_est else [],
            )
            side=self.sb.render(fps,hv,vd,self._fn)
            cv2.imshow(win,np.hstack([cam,side]))

            k=cv2.waitKey(1)&0xFF
            if k in (ord('q'),ord('Q'),27): break
            elif k==32: self.pipe.paused=not self.pipe.paused
            elif k in (ord('p'),ord('P')):
                self.sb.pose_enabled=not self.sb.pose_enabled; self.sb.invalidate()
            elif k in (ord('s'),ord('S')):
                self._print_session_report()

        self.pipe.stop()
        cv2.destroyAllWindows()
        print("\n  Encerrado.\n")


# ───────────────────────────────────────────────────────────
def main():
    p=argparse.ArgumentParser(description="Tortuga PPE Monitor v3.2")
    p.add_argument("--camera",     default="0")
    p.add_argument("--model",
                   default=os.path.join(os.path.dirname(__file__),"models","best.pt"))
    p.add_argument("--confidence", type=float, default=0.4)
    p.add_argument("--no-pose",    action="store_true",
                   help="Desabilita Fase 2 (Pose Estimation)")
    a=p.parse_args()
    cam=int(a.camera) if str(a.camera).isdigit() else a.camera
    App(cam, a.model, a.confidence, enable_pose=not a.no_pose).run()

if __name__=="__main__":
    main()
