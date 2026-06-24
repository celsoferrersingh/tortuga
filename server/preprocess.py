"""
preprocess.py — Robustez a iluminacao adversa (Fase 4) · Projeto Tortuga

Na metaindustria a camera enfrenta baixo contraste (galpao escuro, contraluz)
e alto contraste (sol direto, faisca de solda estourando o sensor). Antes de
mandar o frame ao YOLO, normalizamos a iluminacao para que os EPIs pequenos
(oculos, protetor) continuem detectaveis.

Tecnicas (classicas, sem custo de GPU, deterministicas e auditaveis):
  - CLAHE no canal L do LAB: realca contraste local sem estourar areas claras.
  - Correcao de gama AUTOMATICA: clareia cena escura / escurece cena estourada,
    mirando um brilho-alvo, com base no brilho medio medido.

Modo ADAPTATIVO (recomendado): so realca quando o frame foge da faixa boa
(muito escuro/claro OU baixo contraste). Em cena ja bem iluminada, devolve o
frame original — economiza CPU e nao prejudica deteccoes que ja estao boas.

A imagem de exibicao continua a original; so a copia enviada a inferencia e
realcada — o operador ve a cena real, o modelo ve a cena tratada.
"""
from __future__ import annotations
import cv2
import numpy as np

TARGET_MEAN = 0.50
GAMMA_MIN, GAMMA_MAX = 0.4, 2.5
DEFAULT_TOL = 0.12          # tolerancia de brilho em torno do alvo
DEFAULT_MIN_CONTRAST = 0.12 # desvio-padrao minimo (0..1) antes de realcar


def brightness(frame: np.ndarray) -> float:
    """Brilho medio normalizado 0..1 — util para telemetria/auditoria por camera."""
    return round(float(np.mean(frame)) / 255.0, 3)


def contrast(frame: np.ndarray) -> float:
    """Contraste = desvio-padrao do cinza normalizado 0..1."""
    g = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY) if frame.ndim == 3 else frame
    return round(float(np.std(g)) / 255.0, 3)


def needs_enhancement(frame: np.ndarray, target: float = TARGET_MEAN,
                      tol: float = DEFAULT_TOL, min_contrast: float = DEFAULT_MIN_CONTRAST) -> bool:
    """True se o frame esta fora da faixa boa (escuro/claro demais ou sem contraste)."""
    return abs(brightness(frame) - target) > tol or contrast(frame) < min_contrast


def auto_gamma_value(frame: np.ndarray, target: float = TARGET_MEAN) -> float:
    """apply_gamma usa saida = entrada^(1/g); mean^(1/g)=target => g=ln(mean)/ln(target)."""
    mean = float(np.mean(frame)) / 255.0
    mean = min(max(mean, 1e-3), 0.999)
    g = float(np.log(mean) / np.log(max(target, 1e-3)))
    return float(min(max(g, GAMMA_MIN), GAMMA_MAX))


def apply_gamma(frame: np.ndarray, gamma: float) -> np.ndarray:
    inv = 1.0 / max(gamma, 1e-3)
    lut = np.array([((i / 255.0) ** inv) * 255 for i in range(256)], dtype=np.uint8)
    return cv2.LUT(frame, lut)


def apply_clahe(frame: np.ndarray, clip: float = 2.0, tile: int = 8) -> np.ndarray:
    lab = cv2.cvtColor(frame, cv2.COLOR_BGR2LAB)
    l, a, b = cv2.split(lab)
    clahe = cv2.createCLAHE(clipLimit=float(clip), tileGridSize=(int(tile), int(tile)))
    l = clahe.apply(l)
    return cv2.cvtColor(cv2.merge((l, a, b)), cv2.COLOR_LAB2BGR)


def enhance(frame: np.ndarray, clahe: bool = True, gamma="auto", clip: float = 2.0,
            tile: int = 8, adaptive: bool = False, target: float = TARGET_MEAN,
            tol: float = DEFAULT_TOL, min_contrast: float = DEFAULT_MIN_CONTRAST) -> np.ndarray:
    """Realca um frame BGR para inferencia robusta.
    adaptive=True: pula tudo se o frame ja esta bom (devolve o original).
    gamma: "auto" (recomendado), None/"off" (sem gama) ou um float fixo."""
    if frame is None or frame.size == 0:
        return frame
    if adaptive and not needs_enhancement(frame, target, tol, min_contrast):
        return frame
    out = frame
    if gamma not in (None, "off", "none", 0):
        g = auto_gamma_value(out, target) if gamma == "auto" else float(gamma)
        if abs(g - 1.0) > 0.05:
            out = apply_gamma(out, g)
    if clahe:
        out = apply_clahe(out, clip=clip, tile=tile)
    return out
