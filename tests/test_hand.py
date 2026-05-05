import pytest
from src.decision.hand import Card, Hand, parse_card, RANKS, SUITS


class TestCard:
    def test_valid_card(self):
        c = Card('A', 'h')
        assert c.rank == 'A'
        assert c.suit == 'h'

    def test_value_face_cards(self):
        assert Card('J', 's').value == 10
        assert Card('Q', 'd').value == 10
        assert Card('K', 'c').value == 10

    def test_value_ace(self):
        assert Card('A', 'h').value == 11

    def test_value_numeric(self):
        for r in ['2', '3', '4', '5', '6', '7', '8', '9']:
            assert Card(r, 'h').value == int(r)
        assert Card('10', 'h').value == 10

    def test_is_ace(self):
        assert Card('A', 'h').is_ace
        assert not Card('K', 'h').is_ace

    def test_is_ten_value(self):
        for r in ['10', 'J', 'Q', 'K']:
            assert Card(r, 'h').is_ten_value
        assert not Card('9', 'h').is_ten_value
        assert not Card('A', 'h').is_ten_value

    def test_invalid_rank(self):
        with pytest.raises(ValueError):
            Card('1', 'h')

    def test_invalid_suit(self):
        with pytest.raises(ValueError):
            Card('A', 'x')

    def test_frozen(self):
        c = Card('A', 'h')
        with pytest.raises(Exception):
            c.rank = 'K'

    def test_str(self):
        assert str(Card('A', 'h')) == 'A♥'
        assert str(Card('10', 's')) == '10♠'


class TestParseCard:
    def test_ace_of_spades(self):
        assert parse_card('As') == Card('A', 's')

    def test_ten_of_diamonds(self):
        assert parse_card('10d') == Card('10', 'd')

    def test_king_of_hearts(self):
        assert parse_card('Kh') == Card('K', 'h')

    def test_lowercase_rank(self):
        # ranks are uppercased
        assert parse_card('ah') == Card('A', 'h')

    def test_invalid(self):
        with pytest.raises(ValueError):
            parse_card('X')


class TestHand:
    def _hand(self, *tokens):
        return Hand([parse_card(t) for t in tokens])

    # --- Total calculation ---

    def test_hard_total(self):
        h = self._hand('8h', '9s')
        assert h.total == 17

    def test_soft_total_ace_counted_11(self):
        h = self._hand('Ah', '6s')
        assert h.total == 17

    def test_ace_downgraded_to_avoid_bust(self):
        h = self._hand('Ah', '6s', '9d')
        assert h.total == 16  # A counted as 1

    def test_two_aces(self):
        h = self._hand('Ah', 'As')
        assert h.total == 12  # 11+1

    def test_three_aces(self):
        h = self._hand('Ah', 'As', 'Ad')
        assert h.total == 13  # 11+1+1

    def test_bust(self):
        h = self._hand('Kh', 'Qs', '5d')
        assert h.total == 25
        assert h.is_bust

    # --- Soft detection ---

    def test_is_soft_ace_six(self):
        assert self._hand('Ah', '6s').is_soft

    def test_is_not_soft_hard_17(self):
        assert not self._hand('Kh', '7s').is_soft

    def test_is_soft_multicard(self):
        # A + 3 + 3 = soft 17
        assert self._hand('Ah', '3s', '3d').is_soft

    def test_ace_downgraded_not_soft(self):
        # A + 6 + 9 = 16 (hard)
        assert not self._hand('Ah', '6s', '9d').is_soft

    # --- Blackjack ---

    def test_blackjack(self):
        assert self._hand('Ah', 'Ks').is_blackjack

    def test_not_blackjack_three_card_21(self):
        h = self._hand('7h', '7s', '7d')
        assert h.total == 21
        assert not h.is_blackjack

    # --- Pair detection ---

    def test_pair_of_eights(self):
        h = self._hand('8h', '8s')
        assert h.is_pair
        assert h.pair_value == 8

    def test_pair_of_tens_mixed_faces(self):
        # J and Q both value 10 → splittable pair
        h = self._hand('Jh', 'Qs')
        assert h.is_pair
        assert h.pair_value == 10

    def test_pair_of_aces(self):
        h = self._hand('Ah', 'As')
        assert h.is_pair
        assert h.pair_value == 11

    def test_not_pair_three_cards(self):
        h = self._hand('8h', '8s', '8d')
        assert not h.is_pair

    def test_not_pair_different_values(self):
        h = self._hand('8h', '9s')
        assert not h.is_pair

    # --- Ace count ---

    def test_ace_count(self):
        assert self._hand('Ah', 'As', '5d').ace_count == 2

    # --- len ---

    def test_len(self):
        h = self._hand('Ah', '6s', '3d')
        assert len(h) == 3
