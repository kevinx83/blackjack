"""
SideBetEvaluator: count-dependent edge calculation for blackjack side bets.

Most side bets have large house edges and should be avoided.
A few are count-sensitive and can flip positive at high true counts:

Lucky Ladies (player total = 20):
  Standard house edge: −17% to −24%
  At TC ≥ +4 (Hi-Lo): edge can turn positive
  Requires separate 10-value card count for precision

Perfect Pairs:
  Standard edge: −2% to −17% (paytable dependent)
  Mildly count-sensitive: high TCs make pairs of 10s more likely
  Generally not exploitable

21+3 (poker hand: player two cards + dealer upcard):
  Standard edge: −3.2%
  Count-sensitive at extremes only; not worth betting unless TC ≥ +5

Rule: ONLY place side bets when the count indicator says the edge is positive.
NEVER place side bets as cover — that is both expensive and detectable.
"""
from __future__ import annotations
from dataclasses import dataclass


@dataclass
class SideBetResult:
    """Evaluation result for one side bet at current count."""
    name: str
    true_count: float
    base_edge: float           # house edge at neutral count (negative)
    adjusted_edge: float       # current edge (positive = player advantage)
    recommended: bool          # True when placing the bet is +EV
    reason: str


# ---------------------------------------------------------------------------
# Lucky Ladies
# ---------------------------------------------------------------------------

class LuckyLadies:
    """
    Lucky Ladies: player's first two cards total exactly 20.
    Paytable values (typical, will vary by casino):
      Any 20:            4:1
      Suited 20:         9:1
      Matched 20 (same rank+suit): 19:1
      Queen of Hearts pair: 125:1 (or 1000:1 with dealer BJ)

    High house edge at neutral count (−17% to −24%).
    Count-sensitivity: 10-value cards create more 20s.
    Approximate break-even: TC ≥ +4 (Hi-Lo) for a standard paytable.
    """

    _BASE_EDGE: float = -0.17   # −17% at neutral count (conservative)
    _EDGE_PER_TC: float = 0.035  # edge improves ~3.5% per TC point above 0

    def __init__(self, paytable_multiplier: float = 1.0) -> None:
        """
        paytable_multiplier: 1.0 for standard, higher for better paytables.
        A multiplier < 1.0 reflects a worse-than-standard paytable.
        """
        self.paytable_multiplier = paytable_multiplier

    def evaluate(
        self,
        true_count: float,
        tens_side_count: float = 0.0,
    ) -> SideBetResult:
        """
        Evaluate Lucky Ladies at current true count.
        tens_side_count: excess 10-value cards remaining (from separate tracking).
        """
        adjusted = (
            self._BASE_EDGE * self.paytable_multiplier
            + true_count * self._EDGE_PER_TC
            + tens_side_count * 0.01  # bonus for 10-excess tracking
        )
        recommended = adjusted > 0
        reason = (
            f"TC={true_count:+.1f}: edge={adjusted:+.1%} "
            f"({'bet' if recommended else 'skip'})"
        )
        return SideBetResult(
            name='Lucky Ladies',
            true_count=true_count,
            base_edge=self._BASE_EDGE,
            adjusted_edge=adjusted,
            recommended=recommended,
            reason=reason,
        )

    def expected_value(self, true_count: float = 0.0) -> float:
        return self._BASE_EDGE + true_count * self._EDGE_PER_TC


# ---------------------------------------------------------------------------
# Perfect Pairs
# ---------------------------------------------------------------------------

class PerfectPairs:
    """
    Perfect Pairs: first two cards form a pair.
    Paytable (typical): mixed pair 6:1, coloured pair 12:1, perfect pair 25:1.
    House edge: −5% to −17% depending on paytable.
    """

    _BASE_EDGE: float = -0.06   # −6% at neutral (reasonable mid-range paytable)
    _EDGE_PER_TC: float = 0.008  # minimal count sensitivity

    def evaluate(self, true_count: float) -> SideBetResult:
        adjusted = self._BASE_EDGE + true_count * self._EDGE_PER_TC
        recommended = adjusted > 0  # almost never
        return SideBetResult(
            name='Perfect Pairs',
            true_count=true_count,
            base_edge=self._BASE_EDGE,
            adjusted_edge=adjusted,
            recommended=recommended,
            reason=f"TC={true_count:+.1f}: edge={adjusted:+.1%} (avoid unless TC≥+8)",
        )

    def expected_value(self, true_count: float = 0.0) -> float:
        return self._BASE_EDGE + true_count * self._EDGE_PER_TC


# ---------------------------------------------------------------------------
# 21+3
# ---------------------------------------------------------------------------

class TwentyOnePlusThree:
    """
    21+3: player's two cards + dealer upcard form a poker hand
    (flush, straight, three-of-a-kind, straight flush, suited trips).
    Standard house edge: −3.2%.
    Count-sensitive at TC ≥ +5 for suited trips.
    """

    _BASE_EDGE: float = -0.032
    _EDGE_PER_TC: float = 0.004

    def evaluate(self, true_count: float) -> SideBetResult:
        adjusted = self._BASE_EDGE + true_count * self._EDGE_PER_TC
        recommended = adjusted > 0
        return SideBetResult(
            name='21+3',
            true_count=true_count,
            base_edge=self._BASE_EDGE,
            adjusted_edge=adjusted,
            recommended=recommended,
            reason=f"TC={true_count:+.1f}: edge={adjusted:+.1%}",
        )

    def expected_value(self, true_count: float = 0.0) -> float:
        return self._BASE_EDGE + true_count * self._EDGE_PER_TC


# ---------------------------------------------------------------------------
# SideBetEvaluator — aggregates all side bets
# ---------------------------------------------------------------------------

class SideBetEvaluator:
    """
    Evaluates all available side bets at the current count.
    Only recommends bets with a positive edge.
    """

    def __init__(self) -> None:
        self.lucky_ladies = LuckyLadies()
        self.perfect_pairs = PerfectPairs()
        self.twentyone_plus_three = TwentyOnePlusThree()

    def evaluate_all(
        self,
        true_count: float,
        tens_side_count: float = 0.0,
    ) -> list[SideBetResult]:
        """Return evaluation results for all registered side bets."""
        return [
            self.lucky_ladies.evaluate(true_count, tens_side_count),
            self.perfect_pairs.evaluate(true_count),
            self.twentyone_plus_three.evaluate(true_count),
        ]

    def recommended_bets(
        self,
        true_count: float,
        tens_side_count: float = 0.0,
    ) -> list[SideBetResult]:
        """Return only the side bets that are currently +EV."""
        return [r for r in self.evaluate_all(true_count, tens_side_count) if r.recommended]

    def expected_value(self, true_count: float = 0.0) -> float:
        """
        Combined EV if ALL side bets are placed. In practice, only place
        the recommended ones — never force negative-EV side bets for cover.
        """
        results = self.evaluate_all(true_count)
        # Only sum the positive ones (don't include forced negative bets)
        return sum(r.adjusted_edge for r in results if r.recommended)
