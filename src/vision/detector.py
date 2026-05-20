"""
CardDetector — wraps a trained YOLOv8n model and returns typed card detections.

Usage:
    detector = CardDetector('runs/train/cards/weights/best.pt')
    detections = detector.detect(frame)   # frame is a BGR numpy array from OpenCV
"""
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from ultralytics import YOLO

from src.decision.hand import Card, parse_card

# Ranks output by the trained 10-class model (J/Q/K merged into '10').
# parse_card() is kept as a fallback for future suit-aware retrains.
_RANK_ONLY_LABELS: frozenset[str] = frozenset(
    {'A', '2', '3', '4', '5', '6', '7', '8', '9', '10'}
)


@dataclass(frozen=True)
class Detection:
    card: Card
    confidence: float
    bbox: tuple[int, int, int, int]  # x1, y1, x2, y2 in pixels

    @property
    def center_y(self) -> int:
        """Vertical midpoint of the bounding box — used for zone assignment."""
        return (self.bbox[1] + self.bbox[3]) // 2

    @property
    def center_x(self) -> int:
        return (self.bbox[0] + self.bbox[2]) // 2


class CardDetector:
    """
    Runs inference on a single frame and returns a list of card detections.

    Parameters
    ----------
    model_path:      path to best.pt produced by train.py
    conf_threshold:  minimum confidence to accept a detection (default 0.5)
    """

    def __init__(self, model_path: str | Path, conf_threshold: float = 0.5) -> None:
        self.model = YOLO(str(model_path))
        self.conf_threshold = conf_threshold

    def detect(self, frame: np.ndarray) -> list[Detection]:
        """
        Run card detection on a BGR frame.

        Returns one Detection per card found above the confidence threshold.
        Duplicate detections of the same card (e.g. from overlapping boxes)
        are left for the state parser to handle — this layer stays simple.
        """
        results = self.model(frame, conf=self.conf_threshold, verbose=False)[0]
        detections: list[Detection] = []

        for box in results.boxes:
            conf = float(box.conf[0])
            if conf < self.conf_threshold:
                continue

            label = results.names[int(box.cls[0])].strip()
            try:
                if label.upper() in _RANK_ONLY_LABELS:
                    # Trained model outputs rank only; suit is irrelevant for strategy.
                    card = Card(label.upper(), 's')
                else:
                    card = parse_card(label)
            except ValueError:
                continue

            x1, y1, x2, y2 = (int(v) for v in box.xyxy[0])
            detections.append(Detection(card=card, confidence=conf, bbox=(x1, y1, x2, y2)))

        return detections
