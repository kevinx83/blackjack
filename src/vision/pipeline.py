"""
Real-time blackjack advisor pipeline.

Usage:
    python -m src.vision.pipeline
    python -m src.vision.pipeline --camera 1 --decks 6

Keys:
    r — new round  (resets seen cards, keeps count)
    n — new shoe   (resets count + round)
    q — quit
"""
from __future__ import annotations
import argparse
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

from src.decision.engine import BlackjackAdvisor, Recommendation
from src.decision.hand import Hand
from src.vision.detector import CardDetector, Detection
from src.vision.state_parser import GameState, StateParser

DEFAULT_MODEL_PATH = Path(__file__).resolve().parents[2] / 'detect' / 'weights' / 'best.pt'

_ACTION_COLORS: dict[str, tuple[int, int, int]] = {
    'HIT':       (0,   200,   0),
    'STAND':     (0,     0, 220),
    'DOUBLE':    (0,   180, 255),
    'SPLIT':     (255, 140,   0),
    'SURRENDER': (180,   0, 220),
    'INSURANCE': (0,   220, 220),
}


@dataclass
class FrameResult:
    detections: list[Detection]
    state: GameState
    recommendation: Recommendation | None
    count_status: dict


class Pipeline:
    def __init__(
        self,
        model_path: str | Path = DEFAULT_MODEL_PATH,
        camera_index: int = 0,
        num_decks: int = 6,
        conf_threshold: float = 0.5,
        confirmation_frames: int = 2,
        empty_reset_frames: int = 8,
    ) -> None:
        self.camera_index = camera_index
        self.detector = CardDetector(model_path, conf_threshold)
        self.advisor = BlackjackAdvisor(num_decks=num_decks)
        self.parser: StateParser | None = None
        self.confirmation_frames = confirmation_frames
        self.empty_reset_frames = empty_reset_frames
        self._last_recommendation: Recommendation | None = None

    def run(self) -> None:
        cap = self._open_camera()
        if not cap.isOpened():
            raise RuntimeError(self._camera_error_message())

        try:
            while True:
                ret, frame = cap.read()
                if not ret:
                    break

                result = self.process_frame(frame)
                frame = self._draw(
                    frame,
                    result.detections,
                    result.state,
                    result.recommendation,
                    result.count_status,
                )
                cv2.imshow('BlackjackAI', frame)

                key = cv2.waitKey(1) & 0xFF
                if key == ord('q'):
                    break
                elif key == ord('r'):
                    self.parser.new_round()
                    self._last_recommendation = None
                elif key == ord('n'):
                    self.advisor.new_shoe()
                    self.parser.new_round()
                    self._last_recommendation = None
        finally:
            cap.release()
            cv2.destroyAllWindows()

    def _open_camera(self) -> cv2.VideoCapture:
        if hasattr(cv2, 'CAP_AVFOUNDATION'):
            return cv2.VideoCapture(self.camera_index, cv2.CAP_AVFOUNDATION)
        return cv2.VideoCapture(self.camera_index)

    def _camera_error_message(self) -> str:
        return (
            f"Cannot open camera {self.camera_index}. On macOS, allow camera "
            "access for the terminal app you are running from in System Settings "
            "> Privacy & Security > Camera, then fully quit and reopen that "
            "terminal. If multiple cameras are connected, try --camera 1."
        )

    def process_frame(self, frame: np.ndarray) -> FrameResult:
        """
        Run CV for one frame and feed newly confirmed cards into the counter.

        This is the integration boundary for the current webcam flow and a
        future camera sync layer: pass a BGR frame in, get detections,
        current table state, recommendation, and count telemetry back.
        """
        h = frame.shape[0]
        if self.parser is None:
            self.parser = StateParser(
                frame_height=h,
                confirmation_frames=self.confirmation_frames,
                empty_reset_frames=self.empty_reset_frames,
            )

        detections = self.detector.detect(frame)
        state = self.parser.update(detections)

        if state.is_new_round:
            self._last_recommendation = None

        if state.new_cards:
            self.advisor.observe(*state.new_cards)

        rec = self._last_recommendation
        if self.parser.dealer_upcard and state.player_cards:
            hand = Hand(state.player_cards)
            first_action = len(state.player_cards) == 2
            rec = self.advisor.recommend(
                hand,
                self.parser.dealer_upcard,
                can_double=first_action,
                can_split=first_action,
            )
            self._last_recommendation = rec

        return FrameResult(
            detections=detections,
            state=state,
            recommendation=rec,
            count_status=self.advisor.state(),
        )

    # ------------------------------------------------------------------
    # Drawing
    # ------------------------------------------------------------------

    def _draw(
        self,
        frame: np.ndarray,
        detections: list[Detection],
        state: GameState,
        rec: Recommendation | None,
        count_status: dict,
    ) -> np.ndarray:
        h, w = frame.shape[:2]
        threshold_y = self.parser._dealer_threshold  # type: ignore[union-attr]

        self._draw_zone_line(frame, w, threshold_y)
        self._draw_detections(frame, detections, threshold_y)

        if rec is not None:
            self._draw_recommendation(frame, w, rec)
        else:
            tc = count_status['true_count']
            cv2.putText(frame, f"TC: {tc:+.1f}", (w - 130, 35),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2)

        self._draw_count_status(frame, count_status)
        cv2.putText(frame, 'r=round  n=shoe  q=quit',
                    (10, h - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (160, 160, 160), 1)
        return frame

    def _draw_zone_line(self, frame: np.ndarray, w: int, y: int) -> None:
        cv2.line(frame, (0, y), (w, y), (0, 255, 255), 1)
        cv2.putText(frame, 'DEALER', (10, y - 8),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 255, 255), 1)
        cv2.putText(frame, 'PLAYER', (10, y + 18),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 255, 255), 1)

    def _draw_detections(
        self, frame: np.ndarray, detections: list[Detection], threshold_y: int
    ) -> None:
        for det in detections:
            color = (0, 100, 255) if det.center_y <= threshold_y else (0, 220, 0)
            x1, y1, x2, y2 = det.bbox
            cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
            label = f"{det.card} {det.confidence:.0%}"
            cv2.putText(frame, label, (x1, y1 - 6),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.55, color, 2)

    def _draw_recommendation(self, frame: np.ndarray, w: int, rec) -> None:
        px, py, pw, ph = w - 225, 10, 215, 105

        # Semi-transparent dark panel
        overlay = frame.copy()
        cv2.rectangle(overlay, (px, py), (px + pw, py + ph), (20, 20, 20), -1)
        cv2.addWeighted(overlay, 0.65, frame, 0.35, 0, frame)

        color = _ACTION_COLORS.get(rec.action, (255, 255, 255))
        cv2.putText(frame, rec.action, (px + 10, py + 48),
                    cv2.FONT_HERSHEY_SIMPLEX, 1.3, color, 3)
        cv2.putText(frame, f"Bet {rec.bet_units}u   TC {rec.true_count:+.1f}",
                    (px + 10, py + 75), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (210, 210, 210), 1)
        if rec.is_deviation:
            cv2.putText(frame, 'DEVIATION', (px + 10, py + 96),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 220, 255), 1)

    def _draw_count_status(self, frame: np.ndarray, count_status: dict) -> None:
        lines = [
            f"RC {count_status['running_count']:+.0f}",
            f"TC {count_status['true_count']:+.1f}",
            f"Seen {count_status['cards_seen']}",
            f"Decks {count_status['decks_remaining']:.1f}",
        ]
        y = 24
        for line in lines:
            cv2.putText(frame, line, (10, y),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.55, (245, 245, 245), 2)
            y += 24


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--model', default=str(DEFAULT_MODEL_PATH), help='Path to best.pt')
    parser.add_argument('--camera', type=int, default=0)
    parser.add_argument('--decks', type=int, default=6)
    parser.add_argument('--conf', type=float, default=0.5)
    parser.add_argument(
        '--confirm-frames',
        type=int,
        default=2,
        help='Frames a detection must persist before it is counted',
    )
    parser.add_argument(
        '--empty-reset-frames',
        type=int,
        default=8,
        help='Consecutive empty frames before the visible round is reset',
    )
    args = parser.parse_args()

    Pipeline(
        model_path=args.model,
        camera_index=args.camera,
        num_decks=args.decks,
        conf_threshold=args.conf,
        confirmation_frames=args.confirm_frames,
        empty_reset_frames=args.empty_reset_frames,
    ).run()


if __name__ == '__main__':
    main()
