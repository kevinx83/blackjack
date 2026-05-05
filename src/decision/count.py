"""Hi-Lo card counting system with ace side count."""
from __future__ import annotations


class HiLoCounter:
    """
    Maintains a Hi-Lo running count, true count, and ace side count.

    Hi-Lo values
    ------------
    +1 : 2, 3, 4, 5, 6
     0 : 7, 8, 9
    -1 : 10, J, Q, K, A
    """

    _VALUES: dict[str, int] = {
        '2': 1, '3': 1, '4': 1, '5': 1, '6': 1,
        '7': 0, '8': 0, '9': 0,
        '10': -1, 'J': -1, 'Q': -1, 'K': -1, 'A': -1,
    }

    def __init__(self, num_decks: int = 6) -> None:
        self.num_decks = num_decks
        self.running_count: int = 0
        self.cards_seen: int = 0
        self.aces_seen: int = 0

    # ------------------------------------------------------------------
    # Mutation
    # ------------------------------------------------------------------

    def add_card(self, rank: str) -> None:
        """Update counts for a newly observed card rank."""
        if rank not in self._VALUES:
            raise ValueError(f"Unknown rank: {rank!r}")
        self.running_count += self._VALUES[rank]
        self.cards_seen += 1
        if rank == 'A':
            self.aces_seen += 1

    def add_hand(self, ranks: list[str]) -> None:
        for r in ranks:
            self.add_card(r)

    def reset(self) -> None:
        self.running_count = 0
        self.cards_seen = 0
        self.aces_seen = 0

    # ------------------------------------------------------------------
    # Query
    # ------------------------------------------------------------------

    def decks_remaining(self) -> float:
        """Estimated decks left based on cards seen."""
        remaining = self.num_decks * 52 - self.cards_seen
        return max(remaining / 52, 0.5)  # floor at half a deck to avoid division issues

    def true_count(self, decks_rem: float | None = None) -> float:
        """Running count divided by decks remaining (rounded to 1 decimal)."""
        dr = decks_rem if decks_rem is not None else self.decks_remaining()
        return self.running_count / dr

    def true_count_int(self, decks_rem: float | None = None) -> int:
        """True count floored to integer (standard for index play lookup)."""
        import math
        return math.floor(self.true_count(decks_rem))

    def ace_neutral_tc(self, decks_rem: float | None = None) -> float:
        """
        Ace-adjusted true count for betting decisions.

        When more aces remain than expected, add to the true count.
        When fewer remain, subtract. Adjustment = (remaining - expected) / decks_rem.
        """
        dr = decks_rem if decks_rem is not None else self.decks_remaining()
        expected_aces = dr * 4  # 4 aces per deck
        actual_remaining = self.num_decks * 4 - self.aces_seen
        adjustment = (actual_remaining - expected_aces) / dr
        return self.true_count(dr) + adjustment

    @property
    def deck_penetration(self) -> float:
        """Fraction of the shoe that has been dealt (0.0 – 1.0)."""
        return self.cards_seen / (self.num_decks * 52)

    def __repr__(self) -> str:
        return (
            f"HiLoCounter(rc={self.running_count}, "
            f"tc={self.true_count():.1f}, "
            f"seen={self.cards_seen}, "
            f"aces={self.aces_seen})"
        )
