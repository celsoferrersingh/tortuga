"""
detector.py — Detecção de EPIs usando YOLOv8.

Suporta dois modelos em paralelo:
  - Modelo principal (best.pt ou best.old.pt): Hardhat, Mask, Safety Vest, etc.
  - Modelo de óculos (best.pt): glasses, no_glasses

Se existir best.old.pt (backup do modelo original), usa-o para EPIs clássicos
e usa o best.pt atual para óculos, combinando as detecções automaticamente.

ACELERAÇÃO GPU:
  No Mac M1/M2/M3/M4 usa automaticamente Metal (MPS).
  Em Linux/Windows com NVIDIA usa CUDA automaticamente.
"""

from __future__ import annotations

import logging
from pathlib import Path

import numpy as np
import torch
from ultralytics import YOLO

log = logging.getLogger("tortuga")

# ─── Palavras-chave para classificação automática ─────────
_SAFE_KEYWORDS = {
    "hardhat", "helmet", "mask", "safety vest", "vest",
    "safety glasses", "glasses", "goggle", "glove",
    "safety shoe", "shield",
}
_VIOLATION_PREFIXES = ("no-", "no_", "without ", "sem ")
_VIOLATION_KEYWORDS = {
    "no-hardhat", "no-helmet", "no-mask", "no-safety vest", "no-vest",
    "no-safety glasses", "no-glasses", "no-goggle", "no-glove",
    "no_hardhat", "no_helmet", "no_mask", "no_vest",
    "no_safety_glasses", "no_glasses", "no_goggle", "no_glove",
}

class _FakeModel:
    """Proxy para compatibilidade: expõe .names como o modelo YOLO original."""
    def __init__(self, names: dict[int, str]):
        self.names = names


# Cores BGR
COLOR_SAFE      = (0, 200, 0)
COLOR_VIOLATION = (0, 0, 220)
COLOR_NEUTRAL   = (200, 200, 0)


def _best_device() -> str:
    if torch.backends.mps.is_available():
        return "mps"
    if torch.cuda.is_available():
        return "cuda"
    return "cpu"


def _classify_class(name: str) -> str:
    n = name.lower().strip()
    if n in _VIOLATION_KEYWORDS:
        return "violation"
    for prefix in _VIOLATION_PREFIXES:
        if n.startswith(prefix):
            return "violation"
    if n in _SAFE_KEYWORDS:
        return "safe"
    for kw in _SAFE_KEYWORDS:
        if kw in n:
            return "safe"
    return "neutral"


class _ModelWrapper:
    """Encapsula um modelo YOLO com seus metadados de classes."""

    def __init__(self, model_path: str, device: str, confidence: float, id_offset: int = 0):
        self.model = YOLO(model_path)
        self.model.to(device)
        self.device = device
        self.confidence = confidence
        self.id_offset = id_offset  # desloca IDs para evitar colisão entre modelos

        self.safe_ids:      set[int] = set()
        self.violation_ids: set[int] = set()
        self.class_names:   dict[int, str] = {}

        for cls_id, name in (self.model.names or {}).items():
            shifted = cls_id + id_offset
            self.class_names[shifted] = name
            kind = _classify_class(name)
            if kind == "safe":
                self.safe_ids.add(shifted)
            elif kind == "violation":
                self.violation_ids.add(shifted)

        log.info(
            "  [%s] seguras=%s | violacoes=%s",
            Path(model_path).name,
            [self.class_names[i] for i in sorted(self.safe_ids)],
            [self.class_names[i] for i in sorted(self.violation_ids)],
        )

    def detect(self, frame: np.ndarray) -> list[dict]:
        results = self.model(frame, conf=self.confidence, verbose=False, device=self.device)
        detections = []
        for result in results:
            if result.boxes is None:
                continue
            for i in range(len(result.boxes)):
                cls_id = int(result.boxes.cls[i].item()) + self.id_offset
                conf   = float(result.boxes.conf[i].item())
                x1, y1, x2, y2 = result.boxes.xyxy[i].tolist()

                if cls_id in self.violation_ids:
                    is_violation, color = True,  COLOR_VIOLATION
                elif cls_id in self.safe_ids:
                    is_violation, color = False, COLOR_SAFE
                else:
                    is_violation, color = False, COLOR_NEUTRAL

                detections.append({
                    "bbox":         (int(x1), int(y1), int(x2), int(y2)),
                    "class_id":     cls_id,
                    "class_name":   self.class_names.get(cls_id, f"class_{cls_id}"),
                    "confidence":   conf,
                    "is_violation": is_violation,
                    "color":        color,
                })
        return detections


class PPEDetector:
    """
    Detector de EPIs com suporte a múltiplos modelos.

    Lógica automática:
    - Se best.old.pt existir: usa-o para EPIs clássicos + best.pt para óculos
    - Senão: usa somente best.pt
    """

    def __init__(self, model_path: str, confidence: float = 0.4):
        self._confidence = confidence
        self.device = _best_device()
        log.info("Dispositivo de inferencia: %s", self.device.upper())

        model_path = Path(model_path)
        old_model_path = model_path.parent / "best.old.pt"

        self._wrappers: list[_ModelWrapper] = []

        # Detecta se o best.pt atual é o modelo de óculos (poucas classes)
        # ou o modelo completo
        probe = YOLO(str(model_path))
        num_classes = len(probe.names or {})
        del probe

        if old_model_path.exists() and num_classes <= 4:
            # best.pt = modelo de óculos (2 classes), best.old.pt = modelo completo
            log.info("Modo DUAL: usando best.old.pt (EPIs) + best.pt (oculos)")
            # Modelo principal: EPIs clássicos (IDs 0-99)
            self._wrappers.append(_ModelWrapper(str(old_model_path), self.device, confidence, id_offset=0))
            # Modelo de óculos: IDs deslocados para 100+ para não colidir
            self._wrappers.append(_ModelWrapper(str(model_path), self.device, confidence, id_offset=100))
        else:
            log.info("Modo SINGLE: usando %s (%d classes)", model_path.name, num_classes)
            self._wrappers.append(_ModelWrapper(str(model_path), self.device, confidence, id_offset=0))

        # Consolida metadados de todos os modelos
        self._safe_ids:      set[int] = set()
        self._violation_ids: set[int] = set()
        self._class_names:   dict[int, str] = {}
        self._epi_to_violation: dict[str, int] = {}

        for w in self._wrappers:
            self._safe_ids.update(w.safe_ids)
            self._violation_ids.update(w.violation_ids)
            self._class_names.update(w.class_names)

        # Monta EPI → violação
        for sid in self._safe_ids:
            sname = self._class_names[sid]
            slower = sname.lower()
            for vid in self._violation_ids:
                vname = self._class_names[vid].lower()
                for prefix in _VIOLATION_PREFIXES:
                    expected = prefix + slower.replace(" ", "_")
                    if vname.replace("-", "_").replace(" ", "_") == expected.replace("-", "_"):
                        self._epi_to_violation[sname] = vid
                        break

        # Warm-up em todos os modelos
        dummy = np.zeros((320, 320, 3), dtype=np.uint8)
        for w in self._wrappers:
            w.model(dummy, conf=confidence, verbose=False, device=self.device)
        log.info("Todos os modelos aquecidos e prontos!")
        log.info("EPIs detectaveis: %s", sorted(self._class_names.values()))

    # ── Confiança propagada a todos os wrappers em tempo real ──
    @property
    def confidence(self) -> float:
        return self._confidence

    @confidence.setter
    def confidence(self, value: float):
        self._confidence = float(value)
        for w in self._wrappers:
            w.confidence = self._confidence

    def detect(self, frame: np.ndarray) -> list[dict]:
        """Roda todos os modelos e combina as detecções."""
        all_detections: list[dict] = []
        for w in self._wrappers:
            all_detections.extend(w.detect(frame))
        return all_detections

    def has_violations(self, detections: list[dict]) -> bool:
        return any(d["is_violation"] for d in detections)

    def get_violation_summary(self, detections: list[dict]) -> list[str]:
        return [
            f"{d['class_name']} ({d['confidence']:.0%})"
            for d in detections if d["is_violation"]
        ]

    # ── Compatibilidade com gui.py que acessa det.model.names ──
    @property
    def model(self) -> "_FakeModel":
        """Proxy para compatibilidade com código que acessa det.model.names."""
        return _FakeModel(self._class_names)

    def get_available_epis(self) -> list[str]:
        """Retorna lista de EPIs que este detector suporta."""
        return sorted(self._class_names[i] for i in self._safe_ids)

    @staticmethod
    def filter_by_station(detections: list[dict], required_epis: list[str]) -> list[dict]:
        """
        Filtra violações pelo nome da classe — independente dos IDs do modelo.
        Cada EPI ativo mantém sua violação; EPIs desativados viram neutros.
        """
        # Palavras-chave que identificam a violação de cada EPI
        _epi_viol_keywords: dict[str, list[str]] = {
            "Hardhat":        ["no-hardhat", "no_hardhat", "nohardhat"],
            "Mask":           ["no-mask",    "no_mask",    "nomask"],
            "Safety Vest":    ["no-safety vest", "no_safety_vest", "no-safety_vest", "no safety vest"],
            "Safety Glasses": ["no_glasses", "no-glasses", "no-safety glasses", "no_safety_glasses"],
        }

        # Constrói conjunto de nomes de violação ativos
        active_viol_names: set[str] = set()
        for epi in required_epis:
            for kw in _epi_viol_keywords.get(epi, []):
                active_viol_names.add(kw)

        filtered = []
        for d in detections:
            if not d["is_violation"]:
                filtered.append(d)
                continue

            name_lower = d["class_name"].lower().strip()
            # Verifica se esta violação corresponde a um EPI ativo
            is_active = any(kw in name_lower or name_lower in kw
                            for kw in active_viol_names)
            if is_active:
                filtered.append(d)
            else:
                filtered.append({**d, "is_violation": False, "color": COLOR_NEUTRAL})

        return filtered
