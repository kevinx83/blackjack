"""
Card counting systems: Hi-Lo, KO, Omega II, Zen Count, Wong Halves.

All balanced systems maintain a running count that is divided by decks remaining
to produce the true count. KO is unbalanced (no TC conversion needed).

Typical use: instantiate MultiCounter, call add_card() on every seen card,
query true_count() for betting/playing decisions.
"""
from __future__ import annotations
import math


# ---------------------------------------------------------------------------
# Point-value tables
# ---------------------------------------------------------------------------

_HILO: dict[str, float] = {
    '2': 1, '3': 1, '4': 1, '5': 1, '6': 1,
    '7': 0, '8': 0, '9': 0,
    '10': -1, 'J': -1, 'Q': -1, 'K': -1, 'A': -1,
}

_KO: dict[str, float] = {   # Knock-Out (unbalanced): 2-7 = +1
    '2': 1, '3': 1, '4': 1, '5': 1, '6': 1, '7': 1,
    '8': 0, '9': 0,
    '10': -1, 'J': -1, 'Q': -1, 'K': -1, 'A': -1,
}

_OMEGA2: dict[str, float] = {   # Omega II (balanced, level-2), highest PE
    '2': 1, '3': 1, '4': 2, '5': 2, '6': 2, '7': 1,
    '8': 0, '9': -1,
    '10': -2, 'J': -2, 'Q': -2, 'K': -2, 'A': 0,
}

_ZEN: dict[str, float] = {   # Zen Count (balanced, level-2)
    '2': 1, '3': 1, '4': 2, '5': 2, '6': 2, '7': 1,
    '8': 0, '9': 0,
    '10': -2, 'J': -2, 'Q': -2, 'K': -2, 'A': -1,
}

_WONG_HALVES: dict[str, float] = {   # Wong Halves (balanced, level-3), highest BC
    '2': 0.5, '3': 1.0, '4': 1.0, '5': 1.5, '6': 1.0, '7': 0.5,
    '8': 0,   '9': -0.5,
    '10': -1.0, 'J': -1.0, 'Q': -1.0, 'K': -1.0, 'A': -1.0,
}

SYSTEM_TABLES = {
    'hilo':        _HILO,
    'ko':          _KO,
    'omega2':      _OMEGA2,
    'zen':         _ZEN,
    'wong_halves': _WONG_HALVES,
}

# Betting Correlation / Playing Efficiency / Insurance Correlation
SYSTEM_STATS = {
    'hilo':        {'BC': 0.97, 'PE': 0.51, 'IC': 0.76},
    'ko':          {'BC': 0.98, 'PE': 0.55, 'IC': 0.78},
    'omega2':      {'BC': 0.92, 'PE': 0.67, 'IC': 0.85},
    'zen':         {'BC': 0.96, 'PE': 0.63, 'IC': 0.85},
    'wong_halves': {'BC': 0.99, 'PE': 0.57, 'IC': 0.72},
}


# ---------------------------------------------------------------------------
# Single-system counter
# ---------------------------------------------------------------------------

class SingleCounter:
    """
    Tracks one counting system's running count and ace side count.
    """

    def __init__(self, system: str, num_decks: int = 6) -> None:
        if system not in SYSTEM_TABLES:
            raise ValueError(f"Unknown system: {system!r}. Choose from {list(SYSTEM_TABLES)}")
        self.system = system
        self.num_decks = num_decks
        self._values = SYSTEM_TABLES[system]
        self.running_count: float = 0.0
        self.cards_seen: int = 0
        self.aces_seen: int = 0
        # KO starts at IRC = -4 × num_decks
        if system == 'ko':
            self.running_count = -4.0 * num_decks

    def add_card(self, rank: str) -> None:
        if rank not in self._values:
            raise ValueError(f"Unknown rank: {rank!r}")
        self.running_count += self._values[rank]
        self.cards_seen += 1
        if rank == 'A':
            self.aces_seen += 1

    def add_hand(self, ranks: list[str]) -> None:
        for r in ranks:
            self.add_card(r)

    def reset(self) -> None:
        self.running_count = 0.0 if self.system != 'ko' else -4.0 * self.num_decks
        self.cards_seen = 0
        self.aces_seen = 0

    def decks_remaining(self) -> float:
        remaining_cards = self.num_decks * 52 - self.cards_seen
        # Round to nearest 0.5 for accuracy; floor at 0.5
        dr = max(remaining_cards / 52, 0.5)
        return round(dr * 2) / 2

    def true_count(self, decks_rem: float | None = None) -> float:
        """Running count / decks remaining. Not meaningful for KO."""
        dr = decks_rem if decks_rem is not None else self.decks_remaining()
        return self.running_count / dr

    def true_count_int(self, decks_rem: float | None = None) -> int:
        return math.floor(self.true_count(decks_rem))

    @property
    def deck_penetration(self) -> float:
        return self.cards_seen / (self.num_decks * 52)

    # ------------------------------------------------------------------
    # KO-specific: pivot count and equivalent running-count threshold
    # ------------------------------------------------------------------

    def ko_key_count(self) -> float:
        """
        KO key count = IRC + 4 × num_decks. When RC >= key count, approximate
        TC >= +2 in Hi-Lo. Used for bet spreading without TC conversion.
        """
        irc = -4.0 * self.num_decks
        return irc + 4 * self.num_decks  # = 0 for any deck count

    def ko_preferred_count(self) -> float:
        """KO 'preferred betting count': pivot point where RC ≈ TC=+4."""
        return 4.0 * self.num_decks

    # ------------------------------------------------------------------
    # Ace side count adjustments
    # ------------------------------------------------------------------

    def ace_excess(self, decks_rem: float | None = None) -> float:
        """
        Aces remaining minus expected aces remaining.
        Positive = more aces than expected → increase bet.
        """
        dr = decks_rem if decks_rem is not None else self.decks_remaining()
        aces_remaining = self.num_decks * 4 - self.aces_seen
        expected_aces = dr * 4
        return aces_remaining - expected_aces

    def ace_adjusted_tc(self, decks_rem: float | None = None) -> float:
        """
        Betting TC adjusted for ace density.
        ±0.5 units per excess ace per deck remaining.
        """
        dr = decks_rem if decks_rem is not None else self.decks_remaining()
        base_tc = self.true_count(dr)
        adjustment = self.ace_excess(dr) / dr * 0.5
        return base_tc + adjustment

    def expected_value(self) -> float:
        """
        Approximate current player edge (fraction) using the standard formula:
        edge ≈ −0.5% + TC × 0.5% for Hi-Lo, 6-deck S17.
        Returns 0.0 for KO (use true_count approximation instead).
        """
        if self.system == 'ko':
            return 0.0
        tc = self.true_count()
        return (-0.005 + tc * 0.005)

    def __repr__(self) -> str:
        return (
            f"SingleCounter({self.system!r}, rc={self.running_count:.1f}, "
            f"tc={self.true_count():.2f}, seen={self.cards_seen}, aces={self.aces_seen})"
        )


# ---------------------------------------------------------------------------
# Multi-system counter (tracks all 5 simultaneously)
# ---------------------------------------------------------------------------

class MultiCounter:
    """
    Runs all five counting systems in parallel so the engine can select
    the optimal system per decision type:
      - Betting:   use Wong Halves (BC=0.99) or Hi-Lo (BC=0.97)
      - Playing:   use Omega II (PE=0.67)
      - Insurance: use Hi-Lo (IC=0.76) or Omega II (IC=0.85)
    """

    def __init__(self, num_decks: int = 6) -> None:
        self.num_decks = num_decks
        self._counters: dict[str, SingleCounter] = {
            name: SingleCounter(name, num_decks) for name in SYSTEM_TABLES
        }

    # ------------------------------------------------------------------
    # Delegates — forwarded to all counters simultaneously
    # ------------------------------------------------------------------

    def add_card(self, rank: str) -> None:
        for c in self._counters.values():
            c.add_card(rank)

    def add_hand(self, ranks: list[str]) -> None:
        for r in ranks:
            self.add_card(r)

    def reset(self) -> None:
        for c in self._counters.values():
            c.reset()

    # ------------------------------------------------------------------
    # System-specific queries
    # ------------------------------------------------------------------

    def get(self, system: str) -> SingleCounter:
        return self._counters[system]

    @property
    def hilo(self) -> SingleCounter:
        return self._counters['hilo']

    @property
    def ko(self) -> SingleCounter:
        return self._counters['ko']

    @property
    def omega2(self) -> SingleCounter:
        return self._counters['omega2']

    @property
    def zen(self) -> SingleCounter:
        return self._counters['zen']

    @property
    def wong_halves(self) -> SingleCounter:
        return self._counters['wong_halves']

    # ------------------------------------------------------------------
    # Convenience — primary system delegates (Hi-Lo is default)
    # ------------------------------------------------------------------

    @property
    def running_count(self) -> float:
        return self.hilo.running_count

    @running_count.setter
    def running_count(self, value: float) -> None:
        self.hilo.running_count = value

    @property
    def cards_seen(self) -> int:
        return self.hilo.cards_seen

    @cards_seen.setter
    def cards_seen(self, value: int) -> None:
        for c in self._counters.values():
            c.cards_seen = value

    @property
    def aces_seen(self) -> int:
        return self.hilo.aces_seen

    @aces_seen.setter
    def aces_seen(self, value: int) -> None:
        self.hilo.aces_seen = value

    def decks_remaining(self) -> float:
        return self.hilo.decks_remaining()

    def true_count(self, decks_rem: float | None = None) -> float:
        """Hi-Lo true count (standard for index plays)."""
        return self.hilo.true_count(decks_rem)

    def true_count_int(self, decks_rem: float | None = None) -> int:
        return self.hilo.true_count_int(decks_rem)

    def ace_neutral_tc(self, decks_rem: float | None = None) -> float:
        return self.hilo.ace_adjusted_tc(decks_rem)

    @property
    def deck_penetration(self) -> float:
        return self.hilo.deck_penetration

    # ------------------------------------------------------------------
    # Optimal system selection per decision
    # ------------------------------------------------------------------

    def betting_tc(self, decks_rem: float | None = None) -> float:
        """Ace-adjusted Hi-Lo TC for bet sizing (high BC + ace adjustment)."""
        return self.hilo.ace_adjusted_tc(decks_rem)

    def playing_tc(self, decks_rem: float | None = None) -> float:
        """Hi-Lo TC for index play lookup (standard in literature)."""
        return self.hilo.true_count(decks_rem)

    def insurance_tc(self, decks_rem: float | None = None) -> float:
        """Hi-Lo TC for insurance (IC=0.76, threshold TC >= 3)."""
        return self.hilo.true_count(decks_rem)

    def expected_value(self) -> float:
        """Approximate current Hi-Lo player edge as a fraction."""
        return self.hilo.expected_value()

    def __repr__(self) -> str:
        hilo = self.hilo
        return (
            f"MultiCounter(rc={hilo.running_count:.1f}, "
            f"tc={hilo.true_count():.2f}, "
            f"seen={hilo.cards_seen}, pen={hilo.deck_penetration():.1%})"
        )


# ---------------------------------------------------------------------------
# Backwards-compatible alias
# ---------------------------------------------------------------------------

class HiLoCounter(SingleCounter):
    """Legacy alias — wraps SingleCounter('hilo') for existing callers."""

    def __init__(self, num_decks: int = 6) -> None:
        super().__init__('hilo', num_decks)

    def ace_neutral_tc(self, decks_rem: float | None = None) -> float:
        return self.ace_adjusted_tc(decks_rem)
