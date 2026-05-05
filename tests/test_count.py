import pytest
from src.decision.count import HiLoCounter


class TestHiLoCounter:
    def test_initial_state(self):
        c = HiLoCounter(6)
        assert c.running_count == 0
        assert c.cards_seen == 0
        assert c.aces_seen == 0

    def test_low_cards_increment(self):
        c = HiLoCounter()
        for rank in ['2', '3', '4', '5', '6']:
            c.add_card(rank)
        assert c.running_count == 5
        assert c.cards_seen == 5

    def test_high_cards_decrement(self):
        c = HiLoCounter()
        for rank in ['10', 'J', 'Q', 'K', 'A']:
            c.add_card(rank)
        assert c.running_count == -5

    def test_neutral_cards_no_change(self):
        c = HiLoCounter()
        for rank in ['7', '8', '9']:
            c.add_card(rank)
        assert c.running_count == 0

    def test_ace_tracking(self):
        c = HiLoCounter()
        c.add_card('A')
        c.add_card('A')
        assert c.aces_seen == 2
        assert c.running_count == -2

    def test_true_count_balanced_shoe(self):
        c = HiLoCounter(6)
        assert c.true_count() == pytest.approx(0.0)

    def test_true_count_with_positive_rc(self):
        c = HiLoCounter(1)
        # Burn half a deck's worth of low cards (+26 RC)
        for _ in range(26):
            c.add_card('5')
        dr = c.decks_remaining()
        expected = 26 / dr
        assert c.true_count() == pytest.approx(expected)

    def test_true_count_int_floors(self):
        c = HiLoCounter(6)
        for _ in range(5):
            c.add_card('5')   # RC = +5; ~6 decks remaining → TC ≈ 0.83 → floor 0
        assert c.true_count_int() == 0

    def test_true_count_int_positive(self):
        c = HiLoCounter(1)
        # With 1 deck, burn all but 6 cards. RC = +24 → DR ≈ 6/52 ≈ 0.5 (floor)
        for _ in range(46):
            c.add_card('5')  # RC = +46, but floored at 0.5 decks
        assert c.true_count_int() > 0

    def test_reset(self):
        c = HiLoCounter()
        c.add_card('A')
        c.add_card('5')
        c.reset()
        assert c.running_count == 0
        assert c.cards_seen == 0
        assert c.aces_seen == 0

    def test_deck_penetration(self):
        c = HiLoCounter(6)
        for _ in range(52):
            c.add_card('7')   # 52 cards = 1 deck
        assert c.deck_penetration == pytest.approx(1 / 6)

    def test_add_hand(self):
        c = HiLoCounter()
        c.add_hand(['A', 'K'])   # -2
        assert c.running_count == -2
        assert c.cards_seen == 2

    def test_invalid_rank_raises(self):
        c = HiLoCounter()
        with pytest.raises(ValueError):
            c.add_card('X')

    def test_decks_remaining_floor(self):
        c = HiLoCounter(1)
        # Burn the whole deck — decks_remaining should floor at 0.5
        for _ in range(52):
            c.add_card('7')
        assert c.decks_remaining() == pytest.approx(0.5)

    def test_ace_neutral_tc_excess_aces(self):
        c = HiLoCounter(6)
        # No cards seen yet — aces remaining == expected, adjustment = 0
        assert c.ace_neutral_tc() == pytest.approx(0.0)

    def test_balanced_deck_rc_zero_after_full_shoe(self):
        import random
        deck = []
        for _ in range(6):
            deck += (
                ['2', '3', '4', '5', '6'] * 4 +
                ['7', '8', '9'] * 4 +
                ['10', 'J', 'Q', 'K', 'A'] * 4
            )
        c = HiLoCounter(6)
        for rank in deck:
            c.add_card(rank)
        assert c.running_count == 0   # Hi-Lo is a balanced system
