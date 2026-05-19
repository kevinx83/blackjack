"""
Bankroll management: Kelly criterion, risk-of-ruin, session stop-loss/win-goal.

Key formulas
------------
Kelly fraction:   f* = edge / variance
Risk of ruin:     RoR = ((1 - edge/var) / (1 + edge/var)) ^ (bankroll / bet_unit)

At TC +3, Hi-Lo 6-deck S17:
  edge ≈ +1.5%  variance ≈ 1.30
  f* = 0.015 / 1.30 ≈ 1.15% of bankroll

Half Kelly halves variance exposure at ~75% of maximum growth rate.

Bankroll requirements (1:12 spread, TC+2 entry):
  300–500 max-bet units for full Kelly
  → $300 max bet requires $90,000–$150,000 (full Kelly)
  → $300 max bet requires $45,000–$75,000  (half Kelly)
"""
from __future__ import annotations
import math


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_BJ_VARIANCE: float = 1.30   # 6-deck blackjack variance per unit wagered
_BASE_EDGE:   float = -0.005  # house edge at TC = 0 (−0.5%)
_EDGE_PER_TC: float = 0.005   # +0.5% per TC unit (Hi-Lo, 6-deck S17)


# ---------------------------------------------------------------------------
# Core math functions (pure, no state)
# ---------------------------------------------------------------------------

def kelly_fraction(
    edge: float,
    variance: float = _BJ_VARIANCE,
    divisor: float = 2.0,
) -> float:
    """
    Kelly fraction of bankroll to bet per hand.
    divisor=1 → full Kelly; divisor=2 → half Kelly (recommended).
    Returns 0 if edge ≤ 0 (don't bet when at a disadvantage).
    """
    if edge <= 0:
        return 0.0
    return max(0.0, edge / variance / divisor)


def edge_at_tc(true_count: float) -> float:
    """
    Expected player edge at a given Hi-Lo true count (6-deck S17).
    Approximate linear formula; accurate to ±0.05% in the TC −2 to +8 range.
    """
    return _BASE_EDGE + true_count * _EDGE_PER_TC


def risk_of_ruin(
    edge: float,
    bankroll_units: float,
    variance: float = _BJ_VARIANCE,
) -> float:
    """
    Risk-of-ruin formula for a fixed-fraction Kelly bettor.

    RoR = ((1 − edge/variance) / (1 + edge/variance)) ^ (bankroll_units)

    bankroll_units: bankroll expressed as multiples of one bet unit.
    Returns a probability in [0, 1]; < 0.05 is considered acceptable.
    """
    if edge <= 0:
        return 1.0  # certain ruin at a disadvantage
    ratio = (1.0 - edge / variance) / (1.0 + edge / variance)
    if ratio <= 0:
        return 0.0  # edge so large ruin is impossible
    return ratio ** bankroll_units


def minimum_bankroll_units(
    target_ror: float = 0.05,
    edge: float = 0.01,
    variance: float = _BJ_VARIANCE,
) -> float:
    """
    Minimum bankroll (in max-bet units) to achieve target_ror risk of ruin.

    Derived by inverting the RoR formula:
      bankroll = log(target_ror) / log(ratio)
    """
    if edge <= 0:
        return float('inf')
    ratio = (1.0 - edge / variance) / (1.0 + edge / variance)
    if ratio <= 0:
        return 0.0
    return math.log(target_ror) / math.log(ratio)


# ---------------------------------------------------------------------------
# Stateful session manager
# ---------------------------------------------------------------------------

class BankrollManager:
    """
    Tracks bankroll across a session and enforces stop-loss / win-goal rules.

    Parameters
    ----------
    bankroll        : starting bankroll in dollars
    unit            : one betting unit in dollars (minimum bet)
    kelly_divisor   : 1=full Kelly, 2=half Kelly, 4=quarter Kelly
    stop_loss_pct   : leave when session bankroll drops by this fraction
    win_goal_pct    : consider leaving when session bankroll grows by this fraction
    """

    def __init__(
        self,
        bankroll: float = 10_000.0,
        unit: float = 25.0,
        kelly_divisor: float = 2.0,
        stop_loss_pct: float = 0.25,
        win_goal_pct: float = 0.50,
    ) -> None:
        self.bankroll = bankroll
        self.session_start = bankroll
        self.unit = unit
        self.kelly_divisor = kelly_divisor
        self.stop_loss_pct = stop_loss_pct
        self.win_goal_pct = win_goal_pct
        self.hands_played = 0
        self.peak_bankroll = bankroll

    # ------------------------------------------------------------------
    # Bet sizing
    # ------------------------------------------------------------------

    def kelly_bet(self, true_count: float) -> float:
        """
        Kelly-optimal dollar bet for the current TC, clamped to [unit, bankroll/2].
        Rounds to the nearest unit for practicality.
        """
        edge = edge_at_tc(true_count)
        frac = kelly_fraction(edge, variance=_BJ_VARIANCE, divisor=self.kelly_divisor)
        raw = self.bankroll * frac
        clamped = max(self.unit, min(self.bankroll / 2, raw))
        # Round to nearest unit
        return round(clamped / self.unit) * self.unit

    # ------------------------------------------------------------------
    # Settlement
    # ------------------------------------------------------------------

    def settle(self, net_units: float) -> None:
        """
        Record the result of a hand.
        net_units: positive = win, negative = loss, 0 = push.
        """
        self.bankroll += net_units * self.unit
        self.peak_bankroll = max(self.peak_bankroll, self.bankroll)
        self.hands_played += 1

    def settle_dollars(self, net_dollars: float) -> None:
        self.bankroll += net_dollars
        self.peak_bankroll = max(self.peak_bankroll, self.bankroll)
        self.hands_played += 1

    # ------------------------------------------------------------------
    # Session control
    # ------------------------------------------------------------------

    def session_pnl(self) -> float:
        """Net P&L vs session start in dollars."""
        return self.bankroll - self.session_start

    def session_pnl_pct(self) -> float:
        return self.session_pnl() / self.session_start

    def stop_loss_triggered(self) -> bool:
        """True when session loss exceeds stop_loss_pct of starting bankroll."""
        return self.session_pnl_pct() <= -self.stop_loss_pct

    def win_goal_reached(self) -> bool:
        """True when session profit exceeds win_goal_pct of starting bankroll."""
        return self.session_pnl_pct() >= self.win_goal_pct

    def max_drawdown(self) -> float:
        """Largest peak-to-trough drop in session (approximate)."""
        return self.peak_bankroll - self.bankroll

    # ------------------------------------------------------------------
    # Risk metrics
    # ------------------------------------------------------------------

    def current_ror(self, edge: float = 0.01) -> float:
        """
        Current risk of ruin given current bankroll and a representative edge.
        """
        br_units = self.bankroll / self.unit
        return risk_of_ruin(edge, br_units)

    def bankroll_in_units(self) -> float:
        return self.bankroll / self.unit

    # ------------------------------------------------------------------
    # Expected value
    # ------------------------------------------------------------------

    def expected_value(self) -> float:
        """
        Long-run expected hourly dollar rate at a representative TC.
        Assumes 100 hands/hour, 1:12 spread, average edge ~0.8%.
        """
        avg_bet = self.unit * 4   # rough average over full spread
        return avg_bet * 0.008 * 100   # $/hour at +0.8% edge, 100 hands/hr

    def new_session(self) -> None:
        """Reset session tracking (keep total bankroll)."""
        self.session_start = self.bankroll
        self.hands_played = 0

    def __repr__(self) -> str:
        return (
            f"BankrollManager(${self.bankroll:,.0f}, "
            f"session_pnl={self.session_pnl():+,.0f}, "
            f"hands={self.hands_played})"
        )
