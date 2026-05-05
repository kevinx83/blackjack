"""
Validates the basic strategy table for 6-deck S17 DAS with late surrender.
Test cases drawn from standard published charts.
"""
import pytest
from src.decision.hand import Hand, parse_card
from src.decision.basic_strategy import get_basic_action


def hand(*tokens) -> Hand:
    return Hand([parse_card(t) for t in tokens])


def act(player_hand: Hand, dealer_rank: str, das: bool = True, s17: bool = True) -> str:
    upcard_value = parse_card(dealer_rank + 'h').value
    return get_basic_action(player_hand, upcard_value, das=das, s17=s17)


class TestHardStrategy:
    def test_hard_8_always_hit(self):
        for dealer in ['2h', '3h', '4h', '5h', '6h', '7h', '8h', '9h', '10h', 'Ah']:
            dv = parse_card(dealer).value
            assert get_basic_action(hand('3h', '5s'), dv) == 'H'

    def test_hard_9_hit_vs_2(self):
        assert act(hand('4h', '5s'), '2') == 'H'

    def test_hard_9_double_vs_3_through_6(self):
        for d in ['3', '4', '5', '6']:
            assert act(hand('4h', '5s'), d) == 'D'

    def test_hard_9_hit_vs_7_through_A(self):
        for d in ['7', '8', '9', '10', 'A']:
            assert act(hand('4h', '5s'), d) == 'H'

    def test_hard_10_double_vs_2_through_9(self):
        for d in ['2', '3', '4', '5', '6', '7', '8', '9']:
            assert act(hand('6h', '4s'), d) == 'D'

    def test_hard_10_hit_vs_10_and_A(self):
        assert act(hand('6h', '4s'), '10') == 'H'
        assert act(hand('6h', '4s'), 'A') == 'H'

    def test_hard_11_double_vs_2_through_10(self):
        for d in ['2', '3', '4', '5', '6', '7', '8', '9', '10']:
            assert act(hand('7h', '4s'), d) == 'D'

    def test_hard_11_hit_vs_A_s17(self):
        assert act(hand('7h', '4s'), 'A', s17=True) == 'H'

    def test_hard_11_double_vs_A_h17(self):
        assert act(hand('7h', '4s'), 'A', s17=False) == 'D'

    def test_hard_12_hit_vs_2_3(self):
        assert act(hand('7h', '5s'), '2') == 'H'
        assert act(hand('7h', '5s'), '3') == 'H'

    def test_hard_12_stand_vs_4_through_6(self):
        for d in ['4', '5', '6']:
            assert act(hand('7h', '5s'), d) == 'S'

    def test_hard_12_hit_vs_7_through_A(self):
        for d in ['7', '8', '9', '10', 'A']:
            assert act(hand('7h', '5s'), d) == 'H'

    def test_hard_13_stand_vs_2_through_6(self):
        for d in ['2', '3', '4', '5', '6']:
            assert act(hand('8h', '5s'), d) == 'S'

    def test_hard_13_hit_vs_7_through_A(self):
        for d in ['7', '8', '9', '10', 'A']:
            assert act(hand('8h', '5s'), d) == 'H'

    def test_hard_15_surrender_vs_10(self):
        assert act(hand('9h', '6s'), '10') == 'Rh'

    def test_hard_16_stand_vs_2_through_6(self):
        for d in ['2', '3', '4', '5', '6']:
            assert act(hand('9h', '7s'), d) == 'S'

    def test_hard_16_surrender_vs_9_10_A(self):
        for d in ['9', '10', 'A']:
            assert act(hand('9h', '7s'), d) == 'Rh'

    def test_hard_17_always_stand(self):
        for d in ['2', '3', '4', '5', '6', '7', '8', '9', '10', 'A']:
            assert act(hand('Kh', '7s'), d) == 'S'

    def test_hard_below_8_always_hit(self):
        h = hand('2h', '3s')   # hard 5
        for d in ['2', '7', 'A']:
            dv = parse_card(d + 'h').value
            assert get_basic_action(h, dv) == 'H'

    def test_hard_above_17_always_stand(self):
        h = hand('Kh', '9s')   # hard 19
        for d in ['2', '7', 'A']:
            dv = parse_card(d + 'h').value
            assert get_basic_action(h, dv) == 'S'


class TestSoftStrategy:
    def test_soft_13_hit_vs_2_3(self):
        h = hand('Ah', '2s')
        assert act(h, '2') == 'H'
        assert act(h, '3') == 'H'

    def test_soft_13_double_vs_4_through_6(self):
        h = hand('Ah', '2s')
        for d in ['4', '5', '6']:
            assert act(h, d) == 'D'

    def test_soft_13_hit_vs_7_through_A(self):
        h = hand('Ah', '2s')
        for d in ['7', '8', '9', '10', 'A']:
            assert act(h, d) == 'H'

    def test_soft_17_hit_vs_2(self):
        assert act(hand('Ah', '6s'), '2') == 'H'

    def test_soft_17_double_vs_3_through_6(self):
        for d in ['3', '4', '5', '6']:
            assert act(hand('Ah', '6s'), d) == 'D'

    def test_soft_18_double_else_stand_vs_2(self):
        assert act(hand('Ah', '7s'), '2') == 'Ds'

    def test_soft_18_stand_vs_7_8(self):
        assert act(hand('Ah', '7s'), '7') == 'S'
        assert act(hand('Ah', '7s'), '8') == 'S'

    def test_soft_18_hit_vs_9_10_A(self):
        for d in ['9', '10', 'A']:
            assert act(hand('Ah', '7s'), d) == 'H'

    def test_soft_19_stand_vs_all_except_6(self):
        for d in ['2', '3', '4', '7', '8', '9', '10', 'A']:
            assert act(hand('Ah', '8s'), d) == 'S'

    def test_soft_19_double_vs_6(self):
        assert act(hand('Ah', '8s'), '6') == 'Ds'

    def test_soft_20_always_stand(self):
        for d in ['2', '5', '10', 'A']:
            assert act(hand('Ah', '9s'), d) == 'S'

    def test_multicard_soft_same_as_two_card(self):
        # A + 3 + 3 = soft 17 — same play as A,6
        h_multi = hand('Ah', '3s', '3d')
        h_two   = hand('Ah', '6s')
        for d in ['2', '3', '5', '7', 'A']:
            dv = parse_card(d + 'h').value
            assert get_basic_action(h_multi, dv) == get_basic_action(h_two, dv)


class TestPairStrategy:
    def test_pair_2s_split_vs_2_through_7_das(self):
        h = hand('2h', '2s')
        for d in ['2', '3', '4', '5', '6', '7']:
            assert act(h, d) == 'P'

    def test_pair_2s_hit_vs_8_through_A_das(self):
        h = hand('2h', '2s')
        for d in ['8', '9', '10', 'A']:
            assert act(h, d) == 'H'

    def test_pair_2s_no_das_vs_2_3(self):
        h = hand('2h', '2s')
        assert act(h, '2', das=False) == 'H'
        assert act(h, '3', das=False) == 'H'

    def test_pair_4s_split_vs_5_6_das(self):
        h = hand('4h', '4s')
        assert act(h, '5') == 'P'
        assert act(h, '6') == 'P'

    def test_pair_4s_hit_otherwise_das(self):
        h = hand('4h', '4s')
        for d in ['2', '3', '4', '7', '8', '9', '10', 'A']:
            assert act(h, d) == 'H'

    def test_pair_5s_never_split_treated_as_hard_10(self):
        h = hand('5h', '5s')
        # Pair of 5s falls through to hard-10 strategy
        assert act(h, '2') == 'D'
        assert act(h, '10') == 'H'

    def test_pair_8s_always_split(self):
        h = hand('8h', '8s')
        for d in ['2', '3', '4', '5', '6', '7', '8', '9', '10']:
            assert act(h, d) == 'P'

    def test_pair_8s_rp_vs_A(self):
        assert act(hand('8h', '8s'), 'A') == 'Rp'

    def test_pair_9s_split_vs_2_through_6(self):
        h = hand('9h', '9s')
        for d in ['2', '3', '4', '5', '6']:
            assert act(h, d) == 'P'

    def test_pair_9s_stand_vs_7(self):
        assert act(hand('9h', '9s'), '7') == 'S'

    def test_pair_9s_split_vs_8_9(self):
        assert act(hand('9h', '9s'), '8') == 'P'
        assert act(hand('9h', '9s'), '9') == 'P'

    def test_pair_9s_stand_vs_10_A(self):
        assert act(hand('9h', '9s'), '10') == 'S'
        assert act(hand('9h', '9s'), 'A') == 'S'

    def test_pair_tens_always_stand(self):
        h = hand('Kh', 'Qs')  # mixed ten-value pair
        for d in ['2', '5', '6', '10', 'A']:
            assert act(h, d) == 'S'

    def test_pair_aces_always_split(self):
        h = hand('Ah', 'As')
        for d in ['2', '5', '10', 'A']:
            assert act(h, d) == 'P'

    def test_pair_6s_das_vs_2(self):
        assert act(hand('6h', '6s'), '2') == 'P'

    def test_pair_6s_no_das_vs_2(self):
        assert act(hand('6h', '6s'), '2', das=False) == 'H'
