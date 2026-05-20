"""Tests for the vision pipeline components (no camera required)."""
from __future__ import annotations

from pathlib import Path

import pytest

from src.decision.engine import BlackjackAdvisor
from src.decision.hand import Card
from src.vision.detector import CardDetector, Detection, _RANK_ONLY_LABELS
from src.vision.pipeline import Pipeline
from src.vision.state_parser import StateParser, _POSITION_THRESHOLD


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def det(rank: str, x1: int, y1: int, x2: int, y2: int) -> Detection:
    """Build a Detection with a rank-only card (suit='s') and 90% confidence."""
    return Detection(Card(rank, 's'), 0.9, (x1, y1, x2, y2))


# ---------------------------------------------------------------------------
# detector — _RANK_ONLY_LABELS
# ---------------------------------------------------------------------------

def test_rank_only_labels_contains_all_ten_model_classes():
    assert _RANK_ONLY_LABELS == {'A', '2', '3', '4', '5', '6', '7', '8', '9', '10'}


def test_rank_only_labels_excludes_suit_strings():
    for label in ('As', 'Kh', '10d', '7c'):
        assert label not in _RANK_ONLY_LABELS


def test_detector_passes_conf_threshold_to_yolo():
    class FakeBox:
        conf = [0.6]
        cls = [0]
        xyxy = [[10, 20, 30, 40]]

    class FakeResults:
        names = {0: 'A'}
        boxes = [FakeBox()]

    class FakeModel:
        def __init__(self):
            self.kwargs = None

        def __call__(self, frame, **kwargs):
            self.kwargs = kwargs
            return [FakeResults()]

    detector = CardDetector.__new__(CardDetector)
    detector.model = FakeModel()
    detector.conf_threshold = 0.25

    import numpy as np

    detections = detector.detect(np.zeros((100, 100, 3), dtype=np.uint8))

    assert detector.model.kwargs["conf"] == 0.25
    assert detector.model.kwargs["verbose"] is False
    assert detections[0].card == Card('A', 's')


# ---------------------------------------------------------------------------
# StateParser — zone assignment
# ---------------------------------------------------------------------------

def test_dealer_zone_upper_half(frame_height=720):
    # threshold = int(720 * 0.45) = 324
    parser = StateParser(frame_height=frame_height)
    # center_y = (50 + 130) // 2 = 90 → dealer zone
    d = det('A', 100, 50, 170, 130)
    state = parser.update([d])
    assert state.dealer_cards == [Card('A', 's')]
    assert state.player_cards == []


def test_player_zone_lower_half(frame_height=720):
    parser = StateParser(frame_height=frame_height)
    # center_y = (400 + 480) // 2 = 440 → player zone
    d = det('K', 100, 400, 170, 480)
    state = parser.update([d])
    assert state.dealer_cards == []
    assert state.player_cards == [Card('K', 's')]


# ---------------------------------------------------------------------------
# StateParser — spatial deduplication
# ---------------------------------------------------------------------------

def test_first_detection_is_always_new():
    parser = StateParser(frame_height=720)
    state = parser.update([det('7', 50, 400, 120, 480)])
    assert len(state.new_cards) == 1
    assert state.new_cards[0].rank == '7'


def test_same_position_not_reported_twice():
    parser = StateParser(frame_height=720)
    d = det('7', 50, 400, 120, 480)
    parser.update([d])
    # Same bbox in the next frame — card hasn't moved
    state = parser.update([d])
    assert state.new_cards == []


def test_nearby_position_within_threshold_not_reported_twice():
    """Card jitters by a few pixels between frames — must not be double-counted."""
    parser = StateParser(frame_height=720)
    parser.update([det('A', 50, 400, 120, 480)])   # center (85, 440)
    # Shift by 3 pixels — well within _POSITION_THRESHOLD
    state = parser.update([det('A', 53, 403, 123, 483)])  # center (88, 443)
    assert state.new_cards == []


def test_two_same_rank_at_different_positions_both_reported():
    """Two 7s on the table must each be counted independently."""
    parser = StateParser(frame_height=720)
    d1 = det('7', 50,  400, 120, 480)   # center (85,  440)
    d2 = det('7', 300, 400, 370, 480)   # center (335, 440) — 250 px apart
    state = parser.update([d1, d2])
    assert len(state.new_cards) == 2
    assert all(c.rank == '7' for c in state.new_cards)


def test_cards_beyond_threshold_are_independent():
    """Cards exactly at the threshold boundary: one pixel beyond → new card."""
    parser = StateParser(frame_height=720)
    # First card centred at (100, 400)
    parser.update([det('5', 85, 385, 115, 415)])
    # Second card whose centre is _POSITION_THRESHOLD + 1 away horizontally
    offset = _POSITION_THRESHOLD + 1
    x = 100 + offset
    state = parser.update([det('5', x - 15, 385, x + 15, 415)])
    assert len(state.new_cards) == 1


def test_cards_within_threshold_are_same():
    """Cards exactly within the threshold boundary → not a new card."""
    parser = StateParser(frame_height=720)
    parser.update([det('5', 85, 385, 115, 415)])  # centre (100, 400)
    # New detection one pixel inside threshold
    offset = _POSITION_THRESHOLD - 1
    x = 100 + offset
    state = parser.update([det('5', x - 15, 385, x + 15, 415)])
    assert state.new_cards == []


# ---------------------------------------------------------------------------
# StateParser — round reset
# ---------------------------------------------------------------------------

def test_empty_frame_after_cards_triggers_reset():
    parser = StateParser(frame_height=720)
    parser.update([det('A', 50, 400, 120, 480)])
    # Table cleared
    state = parser.update([])
    assert state.is_new_round is True
    # After reset, positions list is empty; next card at same spot is new again
    state2 = parser.update([det('K', 50, 400, 120, 480)])
    assert len(state2.new_cards) == 1


def test_empty_reset_can_require_multiple_frames():
    parser = StateParser(frame_height=720, empty_reset_frames=2)
    parser.update([det('A', 50, 400, 120, 480)])
    state = parser.update([])
    assert state.is_new_round is False
    state = parser.update([])
    assert state.is_new_round is True


def test_confirmation_frames_delay_new_card_until_stable():
    parser = StateParser(frame_height=720, confirmation_frames=2)
    state = parser.update([det('5', 50, 400, 120, 480)])
    assert state.new_cards == []

    state = parser.update([det('5', 52, 402, 122, 482)])
    assert state.new_cards == [Card('5', 's')]

    state = parser.update([det('5', 52, 402, 122, 482)])
    assert state.new_cards == []


def test_manual_new_round_clears_seen_positions():
    parser = StateParser(frame_height=720)
    parser.update([det('Q', 50, 400, 120, 480)])
    parser.new_round()
    state = parser.update([det('Q', 50, 400, 120, 480)])
    assert len(state.new_cards) == 1


def test_empty_frame_with_no_prior_cards_does_not_reset():
    """Idle camera before any cards are dealt — must not spuriously reset."""
    parser = StateParser(frame_height=720)
    state = parser.update([])
    assert state.new_cards == []
    assert state.dealer_cards == []
    assert state.player_cards == []


# ---------------------------------------------------------------------------
# StateParser — dealer_upcard property
# ---------------------------------------------------------------------------

def test_dealer_upcard_returns_first_dealer_card(frame_height=720):
    parser = StateParser(frame_height=frame_height)
    parser.update([det('A', 100, 50, 170, 130)])  # dealer zone
    assert parser.dealer_upcard == Card('A', 's')


def test_dealer_upcard_none_when_no_dealer_cards(frame_height=720):
    parser = StateParser(frame_height=frame_height)
    assert parser.dealer_upcard is None


def test_pipeline_process_frame_feeds_confirmed_cards_to_counter():
    class FakeDetector:
        def __init__(self):
            self.calls = 0

        def detect(self, frame):
            self.calls += 1
            return [
                det('A', 100, 50, 170, 130),
                det('5', 100, 400, 170, 480),
                det('10', 220, 400, 290, 480),
            ]

    pipeline = Pipeline.__new__(Pipeline)
    pipeline.camera_index = 0
    pipeline.detector = FakeDetector()
    pipeline.advisor = BlackjackAdvisor(num_decks=6)
    pipeline.parser = None
    pipeline.confirmation_frames = 2
    pipeline.empty_reset_frames = 8
    pipeline._last_recommendation = None
    pipeline.counted_cards = []
    pipeline._reset_button_rect = None

    import numpy as np
    frame = np.zeros((720, 1280, 3), dtype=np.uint8)

    first = pipeline.process_frame(frame)
    assert first.state.new_cards == []
    assert first.count_status['cards_seen'] == 0

    second = pipeline.process_frame(frame)
    assert [card.rank for card in second.state.new_cards] == ['A', '5', '10']
    assert second.count_status['cards_seen'] == 3
    assert second.count_status['running_count'] == -1
    assert pipeline.counted_cards == ['A', '5', '10']
    assert second.recommendation is not None

    pipeline.reset_shoe()
    assert pipeline.counted_cards == []
    assert pipeline.advisor.counter.cards_seen == 0


def test_pipeline_requires_two_player_cards_for_recommendation():
    class FakeDetector:
        def detect(self, frame):
            return [
                det('A', 100, 50, 170, 130),
                det('10', 220, 400, 290, 480),
            ]

    pipeline = Pipeline.__new__(Pipeline)
    pipeline.camera_index = 0
    pipeline.detector = FakeDetector()
    pipeline.advisor = BlackjackAdvisor(num_decks=6)
    pipeline.parser = None
    pipeline.confirmation_frames = 1
    pipeline.empty_reset_frames = 8
    pipeline._last_recommendation = None
    pipeline.counted_cards = []
    pipeline._reset_button_rect = None

    import numpy as np

    frame = np.zeros((720, 1280, 3), dtype=np.uint8)
    result = pipeline.process_frame(frame)

    assert result.recommendation is None
    assert result.state.dealer_cards == [Card('A', 's')]
    assert result.state.player_cards == [Card('10', 's')]


def test_pipeline_process_image_file_writes_annotated_summary(tmp_path):
    class FakeDetector:
        def detect(self, frame):
            return [
                det('A', 100, 50, 170, 130),
                det('5', 100, 400, 170, 480),
                det('10', 220, 400, 290, 480),
            ]

    pipeline = Pipeline.__new__(Pipeline)
    pipeline.camera_index = 0
    pipeline.detector = FakeDetector()
    pipeline.advisor = BlackjackAdvisor(num_decks=6)
    pipeline.parser = None
    pipeline.confirmation_frames = 1
    pipeline.empty_reset_frames = 8
    pipeline._last_recommendation = None
    pipeline.counted_cards = []
    pipeline._reset_button_rect = None

    import cv2
    import numpy as np

    image_path = tmp_path / "round.jpg"
    output_path = tmp_path / "round_annotated.jpg"
    frame = np.zeros((720, 1280, 3), dtype=np.uint8)
    assert cv2.imwrite(str(image_path), frame)

    summary = pipeline.process_image_file(image_path, output_path)

    assert output_path.exists()
    assert summary["dealer_cards"] == ["A"]
    assert summary["player_cards"] == ["5", "10"]
    assert summary["counted_cards"] == ["A", "5", "10"]
    assert summary["recommendation"] is not None
    assert summary["count"]["cards_seen"] == 3
    assert summary["count"]["running_count"] == -1


def test_pipeline_default_image_output_path_uses_test_output():
    pipeline = Pipeline.__new__(Pipeline)

    default_path = pipeline._default_image_output_path(Path("static/image2.png"), None)
    custom_path = pipeline._default_image_output_path(Path("static/image2.png"), Path("custom"))

    assert default_path == Path("test_output/image2_annotated.png")
    assert custom_path == Path("custom/image2_annotated.png")
