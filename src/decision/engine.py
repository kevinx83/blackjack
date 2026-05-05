"""
BlackjackAdvisor — top-level decision engine.

Combines basic strategy, Hi-Lo count deviations, and action resolution
into a single, testable interface. The CV pipeline calls this module;
the CV pipeline is never imported here.
"""
from __future__ import annotations
from dataclasses import dataclass, field

from .hand import Hand, Card
from .basic_strategy import get_basic_action
from .deviations import check_deviation
from .count import HiLoCounter

# Final resolved actions returned to callers
HIT = 'HIT'
STAND = 'STAND'
DOUBLE = 'DOUBLE'
SPLIT = 'SPLIT'
SURRENDER = 'SURRENDER'
INSURANCE = 'INSURANCE'

# Bet sizing thresholds (true count → unit multiplier)
_BET_RAMP: list[tuple[float, int]] = [
    (5, 8),
    (4, 6),
    (3, 4),
    (2, 2),
    (1, 1),
    (-99, 1),  # negative/neutral counts: flat bet
]


@dataclass
class Recommendation:
    action: str          # HIT / STAND / DOUBLE / SPLIT / SURRENDER / INSURANCE
    raw_code: str        # raw strategy code before resolution (e.g. 'Rh', 'Ds')
    is_deviation: bool   # True when an index play overrides basic strategy
    true_count: float
    bet_units: int       # suggested bet size in units (1–8)
    reasoning: str       # human-readable explanation


def _resolve(
    code: str,
    can_double: bool,
    can_split: bool,
    can_surrender: bool,
) -> str:
    """Map a raw strategy code to a final action, respecting table rules."""
    match code:
        case 'H':
            return HIT
        case 'S':
            return STAND
        case 'D' | 'Dh':
            return DOUBLE if can_double else HIT
        case 'Ds':
            return DOUBLE if can_double else STAND
        case 'P':
            return SPLIT if can_split else HIT
        case 'Rh':
            return SURRENDER if can_surrender else HIT
        case 'Rs':
            return SURRENDER if can_surrender else STAND
        case 'Rp':
            return SURRENDER if can_surrender else (SPLIT if can_split else HIT)
        case 'I':
            return INSURANCE
        case _:
            return code


def _bet_units(tc: float) -> int:
    for threshold, units in _BET_RAMP:
        if tc >= threshold:
            return units
    return 1


def _explain(
    hand: Hand,
    dealer: Card,
    raw_code: str,
    final_action: str,
    is_deviation: bool,
    tc: float,
) -> str:
    base = f"{hand} vs dealer {dealer} → {final_action}"
    if is_deviation:
        return f"{base} [deviation at TC {tc:+.1f}, code={raw_code}]"
    return f"{base} [basic strategy, code={raw_code}]"


class BlackjackAdvisor:
    """
    Stateful advisor that tracks the running count across a shoe.

    Parameters
    ----------
    num_decks:  number of decks in the shoe (1, 2, 4, 6, or 8)
    das:        double after split allowed
    s17:        dealer stands on soft 17 (False = H17)
    surrender:  late surrender available
    """

    def __init__(
        self,
        num_decks: int = 6,
        das: bool = True,
        s17: bool = True,
        surrender: bool = True,
    ) -> None:
        self.num_decks = num_decks
        self.das = das
        self.s17 = s17
        self.surrender = surrender
        self.counter = HiLoCounter(num_decks)

    # ------------------------------------------------------------------
    # Count maintenance
    # ------------------------------------------------------------------

    def observe(self, *cards: Card) -> None:
        """Record cards that have become visible (updates running count)."""
        for card in cards:
            self.counter.add_card(card.rank)

    def new_shoe(self) -> None:
        self.counter.reset()

    # ------------------------------------------------------------------
    # Core recommendation
    # ------------------------------------------------------------------

    def recommend(
        self,
        player_hand: Hand,
        dealer_upcard: Card,
        *,
        can_double: bool = True,
        can_split: bool = True,
        decks_remaining: float | None = None,
    ) -> Recommendation:
        """
        Compute the optimal action for the given game state.

        can_double / can_split should be False after the first two cards
        (e.g. after already hitting) or when table rules prohibit it.
        """
        dealer_val = dealer_upcard.value  # 2–11
        tc = self.counter.true_count(decks_remaining)
        tc_int = self.counter.true_count_int(decks_remaining)
        can_surrender = self.surrender

        # Deviation check takes priority over basic strategy
        raw = check_deviation(player_hand, dealer_val, tc_int)
        is_deviation = raw is not None
        if raw is None:
            raw = get_basic_action(player_hand, dealer_val, self.das, self.s17)

        # Restrict options that are not currently allowed
        if not can_double and raw in ('D', 'Dh', 'Ds'):
            raw = 'S' if raw == 'Ds' else 'H'
        if not can_split and raw in ('P', 'Rp'):
            raw = 'Rh'

        final = _resolve(raw, can_double, can_split, can_surrender)
        bet = _bet_units(tc)
        reason = _explain(player_hand, dealer_upcard, raw, final, is_deviation, tc)

        return Recommendation(
            action=final,
            raw_code=raw,
            is_deviation=is_deviation,
            true_count=tc,
            bet_units=bet,
            reasoning=reason,
        )

    def insurance_advised(self, decks_remaining: float | None = None) -> bool:
        """True when the count justifies taking insurance (TC >= 3)."""
        return self.counter.true_count_int(decks_remaining) >= 3

    def __repr__(self) -> str:
        return (
            f"BlackjackAdvisor(decks={self.num_decks}, "
            f"das={self.das}, s17={self.s17}, {self.counter})"
        )
