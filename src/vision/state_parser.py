"""
StateParser — converts raw per-frame detections into a structured game state.

Responsibilities:
  - Assign each detection to dealer or player zone based on vertical position
  - Deduplicate: only report cards not yet seen this round
  - Detect round resets (card count drops to 0)

Usage:
    parser = StateParser(frame_height=720)
    state = parser.update(detections)
    advisor.observe(*state.new_cards)
"""
from __future__ import annotations
import math
from dataclasses import dataclass

from src.decision.hand import Card
from src.vision.detector import Detection

# Fraction of frame height below which cards are treated as player cards.
# Cards above this line are dealer cards. Tune if your camera angle differs.
_DEALER_ZONE_MAX_Y_FRAC = 0.45

# Two detections whose centres are closer than this (pixels) are treated as
# the same physical card. Set relative to a typical card width of ~80-100px.
_POSITION_THRESHOLD = 80


@dataclass
class GameState:
    dealer_cards: list[Card]
    player_cards: list[Card]
    new_cards: list[Card]      # cards seen for the first time this round
    is_new_round: bool         # True on the frame a round reset was detected


class StateParser:
    """
    Stateful parser that tracks which cards have already been observed
    and emits only newly visible cards each frame.

    Parameters
    ----------
    frame_height:        pixel height of the camera frame
    dealer_zone_max_y:   override the default 0.45 zone fraction
    """

    def __init__(
        self,
        frame_height: int,
        dealer_zone_max_y: float = _DEALER_ZONE_MAX_Y_FRAC,
        confirmation_frames: int = 1,
        empty_reset_frames: int = 1,
    ) -> None:
        if confirmation_frames < 1:
            raise ValueError("confirmation_frames must be >= 1")
        if empty_reset_frames < 1:
            raise ValueError("empty_reset_frames must be >= 1")

        self._dealer_threshold = int(frame_height * dealer_zone_max_y)
        self._confirmation_frames = confirmation_frames
        self._empty_reset_frames = empty_reset_frames
        # Track seen cards by bounding-box centre rather than Card identity so
        # that two cards of the same rank (e.g. two 7s) are not collapsed into one.
        self._seen_positions: list[tuple[int, int]] = []
        self._pending_positions: list[tuple[int, int, Card, int]] = []
        self._dealer_cards: list[Card] = []
        self._player_cards: list[Card] = []
        self._empty_frame_count = 0

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def update(self, detections: list[Detection]) -> GameState:
        """Process one frame's detections and return the current game state."""
        is_new_round = False
        if self._should_reset(detections):
            self._reset_round()
            is_new_round = True

        dealer_cards: list[Card] = []
        player_cards: list[Card] = []
        new_cards: list[Card] = []
        pending_seen: list[tuple[int, int]] = []

        for det in detections:
            if det.center_y <= self._dealer_threshold:
                dealer_cards.append(det.card)
            else:
                player_cards.append(det.card)

            if not self._position_seen(det.center_x, det.center_y):
                confirmed = self._record_pending(det, pending_seen)
                if confirmed is not None:
                    new_cards.append(confirmed)

        self._prune_pending(pending_seen)
        self._dealer_cards = dealer_cards
        self._player_cards = player_cards

        return GameState(
            dealer_cards=dealer_cards,
            player_cards=player_cards,
            new_cards=new_cards,
            is_new_round=is_new_round,
        )

    def new_round(self) -> None:
        """Call this manually (e.g. keyboard shortcut) to reset between rounds."""
        self._reset_round()

    @property
    def dealer_upcard(self) -> Card | None:
        """The first dealer card, or None if no dealer cards are visible."""
        return self._dealer_cards[0] if self._dealer_cards else None

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _position_seen(self, cx: int, cy: int) -> bool:
        """True if any previously recorded card centre is within the threshold."""
        return any(
            math.hypot(cx - sx, cy - sy) < _POSITION_THRESHOLD
            for sx, sy in self._seen_positions
        )

    def _record_pending(
        self,
        det: Detection,
        pending_seen: list[tuple[int, int]],
    ) -> Card | None:
        """Track a not-yet-counted detection until it is stable enough to count."""
        pending_seen.append((det.center_x, det.center_y))
        for i, (px, py, card, frames) in enumerate(self._pending_positions):
            if math.hypot(det.center_x - px, det.center_y - py) < _POSITION_THRESHOLD:
                frames += 1
                self._pending_positions[i] = (det.center_x, det.center_y, det.card, frames)
                if frames >= self._confirmation_frames:
                    self._seen_positions.append((det.center_x, det.center_y))
                    self._pending_positions.pop(i)
                    return det.card
                return None

        if self._confirmation_frames == 1:
            self._seen_positions.append((det.center_x, det.center_y))
            return det.card

        self._pending_positions.append((det.center_x, det.center_y, det.card, 1))
        return None

    def _prune_pending(self, pending_seen: list[tuple[int, int]]) -> None:
        """Drop unconfirmed detections that disappeared this frame."""
        self._pending_positions = [
            pending
            for pending in self._pending_positions
            if any(
                math.hypot(pending[0] - sx, pending[1] - sy) < _POSITION_THRESHOLD
                for sx, sy in pending_seen
            )
        ]

    def _should_reset(self, detections: list[Detection]) -> bool:
        """
        Heuristic: if cards drop to 0 after we've already seen some,
        a new round has started (cards were swept off the table).
        """
        if detections:
            self._empty_frame_count = 0
            return False

        if not self._seen_positions:
            self._empty_frame_count = 0
            return False

        self._empty_frame_count += 1
        return self._empty_frame_count >= self._empty_reset_frames

    def _reset_round(self) -> None:
        self._seen_positions = []
        self._pending_positions = []
        self._dealer_cards = []
        self._player_cards = []
        self._empty_frame_count = 0
