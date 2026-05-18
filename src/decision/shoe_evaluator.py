"""
ShoeEvaluator: penetration tracking, CSM detection, and shoe quality rating.

Penetration is the single most important table-selection criterion.
Even a perfect count is useless with < 67% penetration.

Penetration impact on EV (6-deck, 1:12 spread, Hi-Lo):
  50% → EV ≈ −0.1%   (barely breaks even)
  67% → EV ≈ +0.3%
  75% → EV ≈ +0.6%   ← minimum viable target
  83% → EV ≈ +0.9%   ← premium

CSM (Continuous Shuffling Machine) detection: if the shoe resets with
very few cards dealt (< 10% of shoe) it is almost certainly a CSM.
CSM shoes cannot be profitably counted — leave immediately.
"""
from __future__ import annotations
from dataclasses import dataclass, field


# ---------------------------------------------------------------------------
# Penetration rating thresholds
# ---------------------------------------------------------------------------

@dataclass
class PenetrationRating:
    """Human-readable quality rating for a shoe's penetration."""
    label: str       # 'excellent' / 'good' / 'minimal' / 'avoid' / 'csm'
    min_pen: float   # lower bound (fraction dealt)
    ev_estimate: float  # approximate player EV with 1:12 spread (fraction)


_RATINGS = [
    PenetrationRating('excellent', 0.83, 0.009),
    PenetrationRating('good',      0.75, 0.006),
    PenetrationRating('minimal',   0.67, 0.003),
    PenetrationRating('avoid',     0.50, -0.001),
    PenetrationRating('unplayable', 0.0, -0.005),
]


def penetration_rating(pen: float) -> PenetrationRating:
    """Return the rating for a given penetration fraction."""
    for r in _RATINGS:
        if pen >= r.min_pen:
            return r
    return _RATINGS[-1]


# ---------------------------------------------------------------------------
# ShoeEvaluator
# ---------------------------------------------------------------------------

class ShoeEvaluator:
    """
    Tracks shoe penetration and raises alerts for CSMs or poor penetration.

    Usage: call `cards_dealt(n)` after each round; check `penetration` and
    `should_leave()` to decide whether to keep playing.
    """

    # Minimum fraction of shoe dealt before we can estimate penetration
    _MIN_SAMPLE_ROUNDS: int = 3

    def __init__(
        self,
        num_decks: int = 6,
        min_penetration: float = 0.75,
        csm_threshold: float = 0.10,
    ) -> None:
        """
        num_decks       : decks in shoe (default 6)
        min_penetration : leave if observed pen drops below this (default 75%)
        csm_threshold   : if shoe resets below this fraction, flag as CSM
        """
        self.num_decks = num_decks
        self.total_cards = num_decks * 52
        self.min_penetration = min_penetration
        self.csm_threshold = csm_threshold

        self._cards_dealt: int = 0
        self._round_cards: list[int] = []  # cards dealt per round
        self._reshuffle_at: int | None = None
        self._is_csm: bool = False
        self._shuffle_count: int = 0

    # ------------------------------------------------------------------
    # Observation
    # ------------------------------------------------------------------

    def observe_round(self, cards_in_round: int) -> None:
        """
        Record the number of cards dealt in one round (all hands + dealer).
        Call this at the end of each round before checking penetration.
        """
        self._cards_dealt += cards_in_round
        self._round_cards.append(cards_in_round)

    def observe_shuffle(self) -> None:
        """
        Call when the dealer shuffles (shoe resets).
        Detects CSMs by checking penetration at shuffle time.
        """
        if self._cards_dealt > 0:
            pen_at_shuffle = self._cards_dealt / self.total_cards
            if pen_at_shuffle < self.csm_threshold:
                self._is_csm = True
            elif self._shuffle_count > 0:
                # Running average of cut-card penetration
                self._reshuffle_at = self._cards_dealt
        self._shuffle_count += 1
        self._cards_dealt = 0
        self._round_cards.clear()

    def observe_cards(self, count: int) -> None:
        """Increment card counter by count (alternative to observe_round)."""
        self._cards_dealt += count

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    @property
    def penetration(self) -> float:
        """
        Current fraction of shoe dealt (0.0 – 1.0).
        Conservative: uses the minimum of observed fraction and 1.0.
        """
        return min(self._cards_dealt / self.total_cards, 1.0)

    @property
    def decks_dealt(self) -> float:
        return self._cards_dealt / 52

    @property
    def decks_remaining(self) -> float:
        remaining = max(0, self.total_cards - self._cards_dealt)
        return remaining / 52

    @property
    def is_csm(self) -> bool:
        """True if this shoe appears to be a continuous shuffling machine."""
        return self._is_csm

    @property
    def rating(self) -> PenetrationRating:
        """Quality rating of the current shoe."""
        return penetration_rating(self.penetration)

    def should_leave(self) -> bool:
        """
        True when the shoe is a CSM, or we are past 60% of the shoe and
        the observed penetration signals that the cut card will land below
        the minimum threshold.

        We only evaluate penetration once enough of the shoe has been dealt
        to form a reliable estimate of where the cut card is placed.
        """
        if self._is_csm:
            return True
        # Need at least 3 rounds of data AND be past 50% of the shoe
        # before we can reliably estimate cut-card placement.
        if len(self._round_cards) < self._MIN_SAMPLE_ROUNDS:
            return False
        # Don't leave early in the shoe — we need to see where the cut card is.
        if self.penetration < 0.50:
            return False
        return self.penetration < self.min_penetration

    def expected_ev(self, bet_spread: int = 12) -> float:
        """
        Estimate the achievable player EV given the current shoe penetration.
        Uses the empirical relationship between penetration and EV for 6-deck.
        """
        pen = self.penetration
        if self._is_csm or pen < 0.50:
            return -0.001
        # Linear interpolation between known penetration/EV pairs
        pts = [(0.83, 0.009), (0.75, 0.006), (0.67, 0.003), (0.50, -0.001)]
        for i in range(len(pts) - 1):
            p_hi, ev_hi = pts[i]
            p_lo, ev_lo = pts[i + 1]
            if pen >= p_lo:
                frac = (pen - p_lo) / (p_hi - p_lo)
                return ev_lo + frac * (ev_hi - ev_lo)
        return pts[-1][1]

    def expected_value(self) -> float:
        """Current expected player edge given shoe penetration."""
        return self.expected_ev()

    def avg_cards_per_round(self) -> float:
        """Estimate cards dealt per round based on observed history."""
        if not self._round_cards:
            return 5.5  # default: ~5-6 cards per round at average table
        return sum(self._round_cards) / len(self._round_cards)

    def rounds_until_shuffle(self) -> float:
        """Estimated rounds remaining until the cut card is reached."""
        avg = self.avg_cards_per_round()
        if avg == 0:
            return 0
        remaining_cards = max(0, self.total_cards * self.min_penetration - self._cards_dealt)
        return remaining_cards / avg

    def __repr__(self) -> str:
        pen_pct = self.penetration * 100
        rating = self.rating.label
        return f"ShoeEvaluator(pen={pen_pct:.1f}%, rating={rating!r}, csm={self._is_csm})"
