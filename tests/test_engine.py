"""
Integration tests for BlackjackAdvisor.
Validates that basic strategy, deviations, and count tracking all compose correctly.
"""
import pytest
from src.decision.engine import BlackjackAdvisor, HIT, STAND, DOUBLE, SPLIT, SURRENDER, INSURANCE
from src.decision.hand import Hand, Card, parse_card


def make(advisor: BlackjackAdvisor, *player_tokens: str, dealer: str) -> str:
    player_hand = Hand([parse_card(t) for t in player_tokens])
    dealer_card = parse_card(dealer)
    return advisor.recommend(player_hand, dealer_card).action


class TestBasicStrategyViaEngine:
    """Engine with zero running count should mirror basic strategy."""

    def setup_method(self):
        self.adv = BlackjackAdvisor(num_decks=6, das=True, s17=True, surrender=True)

    def test_hard_16_vs_10_stand_at_neutral_tc(self):
        # Deviation: 16 vs 10 fires at TC >= 0 → STAND (overrides basic Rh)
        result = make(self.adv, '9h', '7s', dealer='10h')
        assert result == STAND

    def test_hard_16_vs_10_surrender_at_negative_tc(self):
        # Below deviation index → basic Rh → SURRENDER
        self.adv.counter.running_count = -8
        self.adv.counter.cards_seen = 52
        result = make(self.adv, '9h', '7s', dealer='10h')
        assert result == SURRENDER

    def test_hard_11_vs_7_double(self):
        result = make(self.adv, '7h', '4s', dealer='7d')
        assert result == DOUBLE

    def test_hard_12_vs_4_stand(self):
        result = make(self.adv, '7h', '5s', dealer='4d')
        assert result == STAND

    def test_soft_18_vs_2_double(self):
        result = make(self.adv, 'Ah', '7s', dealer='2d')
        assert result == DOUBLE

    def test_pair_8s_vs_9_split(self):
        result = make(self.adv, '8h', '8s', dealer='9d')
        assert result == SPLIT

    def test_pair_aces_vs_10_split(self):
        result = make(self.adv, 'Ah', 'As', dealer='10d')
        assert result == SPLIT

    def test_hard_17_always_stand(self):
        result = make(self.adv, 'Kh', '7s', dealer='Ah')
        assert result == STAND

    def test_hard_8_always_hit(self):
        result = make(self.adv, '3h', '5s', dealer='6d')
        assert result == HIT


class TestCountDeviations:
    """Index plays should override basic strategy at the correct true count."""

    def setup_method(self):
        self.adv = BlackjackAdvisor(num_decks=6)

    def _set_rc(self, rc: int, cards_seen: int = 104) -> None:
        """Manually set running count and cards seen for predictable TC."""
        self.adv.counter.reset()
        self.adv.counter.running_count = rc
        self.adv.counter.cards_seen = cards_seen

    # 16 vs 10: basic=Rh/Surrender; stand at TC >= 0
    def test_16_vs_10_stand_at_zero_tc(self):
        self._set_rc(0, 104)   # TC = 0 / ~4 decks remaining ≈ 0
        result = make(self.adv, '9h', '7s', dealer='10d')
        assert result == STAND

    def test_16_vs_10_surrender_at_negative_tc(self):
        self._set_rc(-12, 104)  # TC < 0
        result = make(self.adv, '9h', '7s', dealer='10d')
        assert result == SURRENDER

    # 11 vs A: basic S17=Hit; double at TC >= 1
    def test_11_vs_A_double_at_tc1(self):
        self._set_rc(5, 104)   # 5 / ~4 decks ≈ TC 1.25
        result = make(self.adv, '7h', '4s', dealer='Ah')
        assert result == DOUBLE

    def test_11_vs_A_hit_at_tc_zero(self):
        self._set_rc(0, 104)
        result = make(self.adv, '7h', '4s', dealer='Ah')
        assert result == HIT

    # 9 vs 2: basic=Hit; double at TC >= 1
    def test_9_vs_2_double_at_tc1(self):
        self._set_rc(5, 104)
        result = make(self.adv, '4h', '5s', dealer='2d')
        assert result == DOUBLE

    def test_9_vs_2_hit_at_tc0(self):
        self._set_rc(0, 104)
        result = make(self.adv, '4h', '5s', dealer='2d')
        assert result == HIT

    # 12 vs 2: basic=Hit; stand at TC >= 3
    def test_12_vs_2_stand_at_tc3(self):
        self._set_rc(12, 104)   # 12/~4 ≈ TC 3
        result = make(self.adv, '7h', '5s', dealer='2d')
        assert result == STAND

    def test_12_vs_2_hit_at_tc2(self):
        self._set_rc(7, 104)   # 7/~4 ≈ TC 1.75
        result = make(self.adv, '7h', '5s', dealer='2d')
        assert result == HIT

    # 13 vs 2: basic=Stand; hit at TC < -1 (negative index)
    def test_13_vs_2_hit_at_very_negative_tc(self):
        self._set_rc(-15, 52)   # -15/~5 ≈ TC -3
        result = make(self.adv, '8h', '5s', dealer='2d')
        assert result == HIT

    def test_13_vs_2_stand_at_tc_minus_1(self):
        self._set_rc(-4, 104)   # -4/~4 ≈ TC -1 → at the boundary, stand (>= -1)
        result = make(self.adv, '8h', '5s', dealer='2d')
        assert result == STAND

    # T,T vs 6: basic=Stand; split at TC >= 4
    def test_tens_vs_6_split_at_tc4(self):
        self._set_rc(16, 104)   # ~TC 4
        result = make(self.adv, 'Kh', 'Qs', dealer='6d')
        assert result == SPLIT

    def test_tens_vs_6_stand_at_tc3(self):
        self._set_rc(11, 104)   # ~TC 2.75
        result = make(self.adv, 'Kh', 'Qs', dealer='6d')
        assert result == STAND


class TestInsurance:
    def setup_method(self):
        self.adv = BlackjackAdvisor(num_decks=6)

    def test_insurance_advised_at_tc3(self):
        self.adv.counter.running_count = 12
        self.adv.counter.cards_seen = 104   # ~TC 3
        assert self.adv.insurance_advised()

    def test_insurance_not_advised_at_tc2(self):
        self.adv.counter.running_count = 7
        self.adv.counter.cards_seen = 104   # ~TC 1.75
        assert not self.adv.insurance_advised()


class TestActionResolution:
    """Verify conditional actions (D→H, Rh→H, Rp→P) resolve correctly."""

    def setup_method(self):
        self.adv = BlackjackAdvisor()

    def test_double_falls_back_to_hit_when_not_allowed(self):
        # Hard 11 (4+4+3) vs 5 → basic D → fallback HIT when can_double=False
        player = Hand([parse_card('4h'), parse_card('4s'), parse_card('3d')])
        dealer = parse_card('5h')
        rec = self.adv.recommend(player, dealer, can_double=False)
        assert rec.action == HIT

    def test_double_ds_falls_back_to_stand_when_not_allowed(self):
        # Soft 18 vs 2 → Ds. With can_double=False → STAND
        player = Hand([parse_card('Ah'), parse_card('7s')])
        dealer = parse_card('2h')
        rec = self.adv.recommend(player, dealer, can_double=False)
        assert rec.action == STAND

    def test_rh_falls_back_to_hit_without_surrender(self):
        # Hard 16 vs 9: deviation only at TC >= 5; at neutral TC basic is Rh → HIT without surrender
        adv = BlackjackAdvisor(surrender=False)
        player = Hand([parse_card('9h'), parse_card('7s')])   # hard 16
        dealer = parse_card('9h')
        rec = adv.recommend(player, dealer)
        assert rec.action == HIT

    def test_pair_8s_rp_vs_A_falls_back_to_split_without_surrender(self):
        adv = BlackjackAdvisor(surrender=False)
        player = Hand([parse_card('8h'), parse_card('8s')])
        dealer = parse_card('Ah')
        rec = adv.recommend(player, dealer)
        assert rec.action == SPLIT


class TestCountTracking:
    """observe() should update the running count correctly."""

    def test_observe_cards_updates_count(self):
        adv = BlackjackAdvisor()
        adv.observe(parse_card('5h'), parse_card('Kd'))  # +1, -1
        assert adv.counter.running_count == 0
        assert adv.counter.cards_seen == 2

    def test_new_shoe_resets(self):
        adv = BlackjackAdvisor()
        adv.observe(parse_card('5h'), parse_card('5d'), parse_card('5c'))
        adv.new_shoe()
        assert adv.counter.running_count == 0


class TestBetSizing:
    def setup_method(self):
        self.adv = BlackjackAdvisor()

    def _tc_rec(self, rc: int, seen: int = 104) -> int:
        self.adv.counter.reset()
        self.adv.counter.running_count = rc
        self.adv.counter.cards_seen = seen
        player = Hand([parse_card('8h'), parse_card('5s')])
        dealer = parse_card('7h')
        return self.adv.recommend(player, dealer).bet_units

    def test_high_tc_max_bet(self):
        units = self._tc_rec(25, 104)   # TC ≈ 6.25
        assert units == 8

    def test_neutral_tc_flat_bet(self):
        units = self._tc_rec(0)
        assert units == 1

    def test_negative_tc_flat_bet(self):
        units = self._tc_rec(-8, 104)
        assert units == 1
