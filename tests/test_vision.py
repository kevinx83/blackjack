"""Tests for the vision pipeline components (no camera required)."""
from __future__ import annotations

import pytest

from src.decision.hand import Card
from src.vision.detector import Detection, _RANK_ONLY_LABELS
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
    # After reset, positions list is empty; next card at same spot is new again
    state2 = parser.update([det('K', 50, 400, 120, 480)])
    assert len(state2.new_cards) == 1


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
