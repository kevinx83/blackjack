"""
Real-time blackjack advisor pipeline.

Usage:
    python -m src.vision.pipeline
    python -m src.vision.pipeline --camera 1 --decks 6
    python -m src.vision.pipeline --image examples/round.jpg --output annotated.jpg

Keys:
    r — new round  (resets seen cards, keeps count)
    n — new shoe   (resets count + round + counted-card history)
    q — quit
"""
from __future__ import annotations
import argparse
import json
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

from src.decision.engine import BlackjackAdvisor, Recommendation
from src.decision.hand import Hand
from src.vision.detector import CardDetector, Detection
from src.vision.state_parser import GameState, StateParser

DEFAULT_MODEL_PATH = Path(__file__).resolve().parents[2] / 'detect' / 'weights' / 'best.pt'
WINDOW_NAME = 'BlackjackAI'
SIDE_PANEL_WIDTH = 300
COUNTED_HISTORY_LIMIT = 120
COUNTED_HISTORY_ROWS = 18

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
        self.counted_cards: list[str] = []
        self._reset_button_rect: tuple[int, int, int, int] | None = None

    def run(self) -> None:
        cap = self._open_camera()
        if not cap.isOpened():
            raise RuntimeError(self._camera_error_message())

        try:
            cv2.namedWindow(WINDOW_NAME)
            cv2.setMouseCallback(WINDOW_NAME, self._handle_mouse)

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
                cv2.imshow(WINDOW_NAME, frame)

                key = cv2.waitKey(1) & 0xFF
                if key == ord('q'):
                    break
                elif key == ord('r'):
                    self.reset_round()
                elif key == ord('n'):
                    self.reset_shoe()
        finally:
            cap.release()
            cv2.destroyAllWindows()

    def run_images(
        self,
        image_paths: list[Path],
        output_path: Path | None = None,
        output_dir: Path | None = None,
        show: bool = False,
    ) -> list[dict]:
        if output_path is not None and len(image_paths) != 1:
            raise ValueError("--output can only be used with a single image")

        summaries = []
        try:
            for image_path in image_paths:
                target = output_path or self._default_image_output_path(image_path, output_dir)
                summaries.append(self.process_image_file(image_path, target, show=show))
                self.reset_round()
        finally:
            if show:
                cv2.destroyAllWindows()

        return summaries

    def process_image_file(
        self,
        image_path: Path,
        output_path: Path | None = None,
        show: bool = False,
    ) -> dict:
        frame = cv2.imread(str(image_path))
        if frame is None:
            raise ValueError(f"Could not read image: {image_path}")

        result = self.process_frame(frame)
        annotated = self._draw(
            frame.copy(),
            result.detections,
            result.state,
            result.recommendation,
            result.count_status,
        )

        if output_path is not None:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            if not cv2.imwrite(str(output_path), annotated):
                raise ValueError(f"Could not write annotated image: {output_path}")

        if show:
            cv2.imshow(WINDOW_NAME, annotated)
            cv2.waitKey(0)

        return self._image_summary(image_path, output_path, result)

    def _default_image_output_path(self, image_path: Path, output_dir: Path | None) -> Path | None:
        if output_dir is None:
            return None
        suffix = image_path.suffix if image_path.suffix else '.jpg'
        return output_dir / f"{image_path.stem}_annotated{suffix}"

    def reset_round(self) -> None:
        if self.parser is not None:
            self.parser.new_round()
        self._last_recommendation = None

    def reset_shoe(self) -> None:
        self.advisor.new_shoe()
        self.reset_round()
        self.counted_cards = []

    def _handle_mouse(self, event: int, x: int, y: int, flags: int, param: object) -> None:
        if event != cv2.EVENT_LBUTTONDOWN or self._reset_button_rect is None:
            return
        x1, y1, x2, y2 = self._reset_button_rect
        if x1 <= x <= x2 and y1 <= y <= y2:
            self.reset_shoe()

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

    def _image_summary(
        self,
        image_path: Path,
        output_path: Path | None,
        result: FrameResult,
    ) -> dict:
        return {
            'image': str(image_path),
            'output': str(output_path) if output_path is not None else None,
            'dealer_cards': [card.rank for card in result.state.dealer_cards],
            'player_cards': [card.rank for card in result.state.player_cards],
            'counted_cards': [card.rank for card in result.state.new_cards],
            'detections': [
                {
                    'card': det.card.rank,
                    'confidence': round(det.confidence, 3),
                    'bbox': det.bbox,
                    'zone': self._zone_for_detection(det),
                }
                for det in result.detections
            ],
            'recommendation': self._recommendation_summary(result.recommendation),
            'count': {
                'running_count': result.count_status['running_count'],
                'true_count': result.count_status['true_count'],
                'cards_seen': result.count_status['cards_seen'],
                'decks_remaining': result.count_status['decks_remaining'],
                'recommended_bet_units': result.count_status['recommended_bet']['units'],
            },
        }

    def _zone_for_detection(self, det: Detection) -> str:
        if self.parser is None:
            return 'unknown'
        return 'dealer' if det.center_y <= self.parser._dealer_threshold else 'player'

    def _recommendation_summary(self, rec: Recommendation | None) -> dict | None:
        if rec is None:
            return None
        return {
            'action': rec.action,
            'raw_code': rec.raw_code,
            'is_deviation': rec.is_deviation,
            'true_count': rec.true_count,
            'bet_units': rec.bet_units,
            'reasoning': rec.reasoning,
        }

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
            self.counted_cards.extend(card.rank for card in state.new_cards)
            self.counted_cards = self.counted_cards[-COUNTED_HISTORY_LIMIT:]

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
        return self._draw_side_panel(frame, count_status)

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

    def _draw_side_panel(self, frame: np.ndarray, count_status: dict) -> np.ndarray:
        h, w = frame.shape[:2]
        panel_x = w
        canvas = np.full((h, w + SIDE_PANEL_WIDTH, 3), (18, 27, 24), dtype=frame.dtype)
        canvas[:, :w] = frame

        cv2.rectangle(canvas, (panel_x, 0), (w + SIDE_PANEL_WIDTH - 1, h - 1), (28, 38, 34), -1)
        cv2.line(canvas, (panel_x, 0), (panel_x, h), (78, 92, 84), 1)

        x = panel_x + 18
        y = 34
        cv2.putText(canvas, 'SHOE CONTROL', (x, y),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.62, (236, 236, 226), 2)

        y += 36
        status_lines = [
            f"Running count {count_status['running_count']:+.0f}",
            f"True count {count_status['true_count']:+.1f}",
            f"Cards seen {count_status['cards_seen']}",
            f"Decks left {count_status['decks_remaining']:.1f}",
        ]
        for line in status_lines:
            cv2.putText(canvas, line, (x, y),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.48, (218, 222, 214), 1)
            y += 24

        y += 14
        button_x1, button_y1 = x, y
        button_x2, button_y2 = panel_x + SIDE_PANEL_WIDTH - 18, y + 42
        cv2.rectangle(canvas, (button_x1, button_y1), (button_x2, button_y2), (45, 126, 86), -1)
        cv2.rectangle(canvas, (button_x1, button_y1), (button_x2, button_y2), (91, 172, 128), 1)
        cv2.putText(canvas, 'Reset shoe (N)', (button_x1 + 16, button_y1 + 27),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.56, (250, 250, 242), 2)
        self._reset_button_rect = (button_x1, button_y1, button_x2, button_y2)

        y = button_y2 + 42
        cv2.putText(canvas, 'COUNTED CARDS', (x, y),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.58, (236, 236, 226), 2)
        y += 28

        recent_cards = self.counted_cards[-COUNTED_HISTORY_ROWS:]
        if not recent_cards:
            cv2.putText(canvas, 'No cards counted yet', (x, y),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.48, (160, 170, 164), 1)
            return canvas

        first_index = len(self.counted_cards) - len(recent_cards) + 1
        for offset, card in enumerate(recent_cards):
            label = f"{first_index + offset:>3}. {card}"
            cv2.putText(canvas, label, (x, y),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (232, 232, 220), 1)
            y += 24
            if y > h - 18:
                break

        return canvas


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--model', default=str(DEFAULT_MODEL_PATH), help='Path to best.pt')
    parser.add_argument('--camera', type=int, default=0)
    parser.add_argument(
        '--image',
        nargs='+',
        type=Path,
        help='Process one or more static blackjack images instead of webcam input',
    )
    parser.add_argument(
        '--output',
        type=Path,
        help='Annotated output image path. Use only with a single --image input.',
    )
    parser.add_argument(
        '--output-dir',
        type=Path,
        help='Directory for annotated static-image outputs',
    )
    parser.add_argument(
        '--show-image',
        action='store_true',
        help='Open annotated static-image output windows after processing',
    )
    parser.add_argument('--decks', type=int, default=6)
    parser.add_argument('--conf', type=float, default=0.5)
    parser.add_argument(
        '--confirm-frames',
        type=int,
        default=None,
        help='Frames a detection must persist before it is counted. Defaults to 1 for --image, 2 for webcam.',
    )
    parser.add_argument(
        '--empty-reset-frames',
        type=int,
        default=8,
        help='Consecutive empty frames before the visible round is reset',
    )
    args = parser.parse_args()

    if args.output is not None and args.output_dir is not None:
        parser.error('--output and --output-dir cannot be used together')
    if args.output is not None and (not args.image or len(args.image) != 1):
        parser.error('--output requires exactly one --image input')

    confirmation_frames = args.confirm_frames
    if confirmation_frames is None:
        confirmation_frames = 1 if args.image else 2

    pipeline = Pipeline(
        model_path=args.model,
        camera_index=args.camera,
        num_decks=args.decks,
        conf_threshold=args.conf,
        confirmation_frames=confirmation_frames,
        empty_reset_frames=args.empty_reset_frames,
    )

    if args.image:
        summaries = pipeline.run_images(
            args.image,
            output_path=args.output,
            output_dir=args.output_dir,
            show=args.show_image,
        )
        print(json.dumps(summaries, indent=2))
        return

    pipeline.run()


if __name__ == '__main__':
    main()
