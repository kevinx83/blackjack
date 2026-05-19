"""
Bet sizing: Kelly criterion + count-based ramp for 6-deck shoe play.

The Kelly fraction f* = edge / variance gives the theoretically optimal
fraction of bankroll to wager for maximum long-run growth rate.
Full Kelly is too volatile in practice; Half Kelly is the standard choice.

Bet ramp (6-deck Hi-Lo, $25 min, 1:12 spread):
  TC ≤ 1:  1 unit  (minimum — negative/neutral edge)
  TC = 2:  2 units
  TC = 3:  4 units
  TC = 4:  6 units
  TC = 5:  8 units
  TC ≥ 6: 12 units  (maximum spread)

Sources: Thorp "Beat the Dealer"; Schlesinger "Blackjack Attack".
"""
from __future__ import annotations
import math
import random


# Blackjack variance per hand (6-deck, basic strategy + 1:1 payoffs approx)
# Actual variance ≈ 1.30 per hand (including doubles/splits/BJ payouts).
_BJ_VARIANCE: float = 1.30

# Approximate edge per true-count unit above the break-even TC of +1.
# Hi-Lo, 6-deck S17: player edge ≈ −0.50% + (TC × 0.50%)
# Breakeven at TC ≈ +1; every additional TC unit ≈ +0.50%.
_EDGE_PER_TC: float = 0.005   # 0.5% per TC unit
_BASE_EDGE:   float = -0.005  # house edge at TC = 0


# ---------------------------------------------------------------------------
# Bet ramp lookup table — maps true-count to unit multiplier
# ---------------------------------------------------------------------------

_BET_RAMP: list[tuple[float, int]] = [
    (6,   12),   # TC ≥ 6:  12 units (max spread 1:12)
    (5,    8),   # TC ≥ 5:   8 units
    (4,    6),   # TC ≥ 4:   6 units
    (3,    4),   # TC ≥ 3:   4 units
    (2,    2),   # TC ≥ 2:   2 units
    (1,    1),   # TC ≥ 1:   1 unit
    (-99,  1),   # negative: 1 unit (flat bet at disadvantage)
]

# Camouflage bet ramp — same thresholds but jumps are smoother to disguise
# the count-to-bet correlation; costs ~0.1–0.2% EV.
_CAMO_BET_RAMP: list[tuple[float, int]] = [
    (6,   10),
    (5,    7),
    (4,    5),
    (3,    3),
    (2,    2),
    (1,    1),
    (-99,  1),
]


def bet_units_for_true_count(tc: float, camouflage: bool = False) -> int:
    """
    Map a pre-round Hi-Lo true count to a suggested bet size in units.

    Implements a 1:12 spread for 6-deck play or a 1:10 camouflage ramp.
    """
    ramp = _CAMO_BET_RAMP if camouflage else _BET_RAMP
    for threshold, units in ramp:
        if tc >= threshold:
            return units
    return 1


def kelly_fraction(
    true_count: float,
    kelly_divisor: float = 2.0,
    variance: float = _BJ_VARIANCE,
) -> float:
    """
    Kelly fraction of bankroll to wager per hand.

    Returns a fraction in [0, max_kelly] where max_kelly ≈ 0.02 (2%).
    kelly_divisor = 2 → Half Kelly (recommended).
    kelly_divisor = 4 → Quarter Kelly (very conservative).
    """
    edge = _BASE_EDGE + true_count * _EDGE_PER_TC
    if edge <= 0:
        return 0.0
    full_kelly = edge / variance
    return full_kelly / kelly_divisor


def kelly_bet_dollars(
    bankroll: float,
    true_count: float,
    min_bet: float = 25.0,
    max_bet: float = 300.0,
    kelly_divisor: float = 2.0,
) -> float:
    """
    Compute the Kelly-optimal dollar bet, clamped to [min_bet, max_bet].

    Rounds to the nearest $25 chip denomination for practicality.
    """
    frac = kelly_fraction(true_count, kelly_divisor)
    raw = bankroll * frac
    clamped = max(min_bet, min(max_bet, raw))
    # Round to nearest $25
    return round(clamped / 25) * 25


class BetSpreader:
    """
    Stateful bet advisor that recommends the optimal bet size each round.

    Combines the count-based ramp with Kelly-optimal sizing and optional
    camouflage variance injection.
    """

    def __init__(
        self,
        unit: float = 25.0,
        max_spread: int = 12,
        kelly_divisor: float = 2.0,
        camouflage_variance: float = 0.0,
        wonging_entry_tc: float = 2.0,
        wonging_exit_tc: float = 0.0,
        wonging_enabled: bool = True,
    ) -> None:
        """
        unit             — minimum bet in dollars (1 unit)
        max_spread       — maximum units (1:12 → 12)
        kelly_divisor    — 2=half Kelly, 4=quarter Kelly
        camouflage_variance — fraction of the time to randomly deviate ±1 unit
        wonging_entry_tc — minimum TC to sit down / play (back-counting)
        wonging_exit_tc  — TC below which to leave the table
        """
        self.unit = unit
        self.max_spread = max_spread
        self.kelly_divisor = kelly_divisor
        self.camouflage_variance = camouflage_variance
        self.wonging_entry_tc = wonging_entry_tc
        self.wonging_exit_tc = wonging_exit_tc
        self.wonging_enabled = wonging_enabled

    # ------------------------------------------------------------------
    # Primary interface
    # ------------------------------------------------------------------

    def recommend_units(self, true_count: float) -> int:
        """
        Return unit multiplier (1–max_spread) for the given true count.
        Applies camouflage variance if configured.
        """
        units = bet_units_for_true_count(true_count, camouflage=False)
        units = min(units, self.max_spread)

        # Inject random ±1 unit camouflage noise
        if self.camouflage_variance > 0 and random.random() < self.camouflage_variance:
            delta = random.choice([-1, 1])
            units = max(1, min(self.max_spread, units + delta))

        return units

    def recommend_dollars(
        self,
        true_count: float,
        bankroll: float | None = None,
    ) -> float:
        """
        Return the recommended dollar bet.
        If bankroll is provided, uses Kelly sizing; otherwise uses the ramp.
        """
        if bankroll is not None:
            return kelly_bet_dollars(
                bankroll, true_count,
                min_bet=self.unit,
                max_bet=self.unit * self.max_spread,
                kelly_divisor=self.kelly_divisor,
            )
        return self.unit * self.recommend_units(true_count)

    def should_play(self, true_count: float) -> bool:
        """
        Wonging: True if TC is above the entry threshold.
        Always True when wonging is disabled.
        """
        if not self.wonging_enabled:
            return True
        return true_count >= self.wonging_entry_tc

    def should_leave(self, true_count: float) -> bool:
        """
        Wonging exit: True if TC drops below the exit threshold.
        Always False when wonging is disabled.
        """
        if not self.wonging_enabled:
            return False
        return true_count <= self.wonging_exit_tc

    def expected_value(self, true_count: float) -> float:
        """Approximate player edge at this true count (as a fraction)."""
        return _BASE_EDGE + true_count * _EDGE_PER_TC

    def __repr__(self) -> str:
        return (
            f"BetSpreader(unit=${self.unit}, spread=1:{self.max_spread}, "
            f"kelly=1/{self.kelly_divisor:.0f}, "
            f"wonging={'on' if self.wonging_enabled else 'off'})"
        )
