from __future__ import annotations
from dataclasses import dataclass

RANKS = ['2', '3', '4', '5', '6', '7', '8', '9', '10', 'J', 'Q', 'K', 'A']
SUITS = ['h', 'd', 'c', 's']

RANK_VALUES: dict[str, int] = {
    '2': 2, '3': 3, '4': 4, '5': 5, '6': 6, '7': 7, '8': 8, '9': 9,
    '10': 10, 'J': 10, 'Q': 10, 'K': 10, 'A': 11,
}

_SUIT_SYMBOLS = {'h': '♥', 'd': '♦', 'c': '♣', 's': '♠'}


@dataclass(frozen=True)
class Card:
    rank: str  # '2'-'9', '10', 'J', 'Q', 'K', 'A'
    suit: str  # 'h', 'd', 'c', 's'

    def __post_init__(self) -> None:
        if self.rank not in RANKS:
            raise ValueError(f"Invalid rank: {self.rank!r}")
        if self.suit not in SUITS:
            raise ValueError(f"Invalid suit: {self.suit!r}")

    @property
    def value(self) -> int:
        return RANK_VALUES[self.rank]

    @property
    def is_ace(self) -> bool:
        return self.rank == 'A'

    @property
    def is_ten_value(self) -> bool:
        return self.value == 10

    def __str__(self) -> str:
        return f"{self.rank}{_SUIT_SYMBOLS[self.suit]}"

    def __repr__(self) -> str:
        return f"Card('{self.rank}', '{self.suit}')"


def parse_card(token: str) -> Card:
    """Parse a card token like 'As', 'Kh', '10d', '7c'."""
    token = token.strip()
    if len(token) < 2:
        raise ValueError(f"Cannot parse card: {token!r}")
    suit = token[-1].lower()
    rank = token[:-1].upper()
    if rank == '1':
        rank = 'A'
    return Card(rank, suit)


class Hand:
    """A blackjack hand — ordered list of cards with computed totals."""

    def __init__(self, cards: list[Card] | None = None) -> None:
        self.cards: list[Card] = list(cards) if cards else []

    def add(self, card: Card) -> Hand:
        self.cards.append(card)
        return self

    @property
    def total(self) -> int:
        """Best non-busting total; aces counted as 11 or 1 as needed."""
        t = sum(c.value for c in self.cards)
        aces = sum(1 for c in self.cards if c.is_ace)
        while t > 21 and aces:
            t -= 10
            aces -= 1
        return t

    @property
    def is_soft(self) -> bool:
        """True when at least one ace is still counted as 11."""
        t = sum(c.value for c in self.cards)
        aces = sum(1 for c in self.cards if c.is_ace)
        while t > 21 and aces:
            t -= 10
            aces -= 1
        return aces > 0 and t <= 21

    @property
    def is_bust(self) -> bool:
        return self.total > 21

    @property
    def is_blackjack(self) -> bool:
        return len(self.cards) == 2 and self.total == 21

    @property
    def is_pair(self) -> bool:
        """True for exactly two cards with the same point value (splittable)."""
        return len(self.cards) == 2 and self.cards[0].value == self.cards[1].value

    @property
    def pair_value(self) -> int | None:
        """Value of the paired card, or None if not a pair."""
        return self.cards[0].value if self.is_pair else None

    @property
    def ace_count(self) -> int:
        return sum(1 for c in self.cards if c.is_ace)

    def __len__(self) -> int:
        return len(self.cards)

    def __str__(self) -> str:
        cards_str = ' '.join(str(c) for c in self.cards)
        label = 'soft' if self.is_soft else 'hard'
        return f"[{cards_str}] ({label} {self.total})"

    def __repr__(self) -> str:
        return f"Hand({self.cards!r})"
