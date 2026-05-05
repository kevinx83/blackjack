"""
Basic strategy tables for 6-deck blackjack, S17 (dealer stands on soft 17),
DAS (double after split allowed), late surrender available.

Action codes
------------
H   Hit
S   Stand
D   Double (else Hit)
Ds  Double (else Stand)
Rh  Surrender (else Hit)
Rs  Surrender (else Stand)
Rp  Surrender (else Split)
P   Split
"""
from __future__ import annotations
from .hand import Hand

# Dealer upcard column index: 2→0, 3→1, … 10→8, A(11)→9
_DI = {2: 0, 3: 1, 4: 2, 5: 3, 6: 4, 7: 5, 8: 6, 9: 7, 10: 8, 11: 9}

# ---------------------------------------------------------------------------
# Hard totals  (rows: player total 8–17;  below 8 always H, above 17 always S)
# ---------------------------------------------------------------------------
_HARD: dict[int, list[str]] = {
    #       2     3     4     5     6     7     8     9    10     A
    8:  ['H',  'H',  'H',  'H',  'H',  'H',  'H',  'H',  'H',  'H'],
    9:  ['H',  'D',  'D',  'D',  'D',  'H',  'H',  'H',  'H',  'H'],
    10: ['D',  'D',  'D',  'D',  'D',  'D',  'D',  'D',  'H',  'H'],
    11: ['D',  'D',  'D',  'D',  'D',  'D',  'D',  'D',  'D',  'H'],  # S17: H vs A
    12: ['H',  'H',  'S',  'S',  'S',  'H',  'H',  'H',  'H',  'H'],
    13: ['S',  'S',  'S',  'S',  'S',  'H',  'H',  'H',  'H',  'H'],
    14: ['S',  'S',  'S',  'S',  'S',  'H',  'H',  'H',  'H',  'H'],
    15: ['S',  'S',  'S',  'S',  'S',  'H',  'H',  'H',  'Rh', 'Rh'],
    16: ['S',  'S',  'S',  'S',  'S',  'H',  'H',  'Rh', 'Rh', 'Rh'],
    17: ['S',  'S',  'S',  'S',  'S',  'S',  'S',  'S',  'S',  'S'],
}

# H17 override: hard 11 vs A becomes Double instead of Hit
_HARD_H17_OVERRIDES: dict[tuple[int, int], str] = {
    (11, 11): 'D',   # 11 vs A: Double in H17
}

# ---------------------------------------------------------------------------
# Soft totals  (rows: non-ace card value 2–9, giving soft 13–20)
# ---------------------------------------------------------------------------
_SOFT: dict[int, list[str]] = {
    #       2     3     4     5     6     7     8     9    10     A
    2:  ['H',  'H',  'D',  'D',  'D',  'H',  'H',  'H',  'H',  'H'],  # A,2 = soft 13
    3:  ['H',  'H',  'D',  'D',  'D',  'H',  'H',  'H',  'H',  'H'],  # A,3 = soft 14
    4:  ['H',  'H',  'D',  'D',  'D',  'H',  'H',  'H',  'H',  'H'],  # A,4 = soft 15
    5:  ['H',  'H',  'D',  'D',  'D',  'H',  'H',  'H',  'H',  'H'],  # A,5 = soft 16
    6:  ['H',  'D',  'D',  'D',  'D',  'H',  'H',  'H',  'H',  'H'],  # A,6 = soft 17
    7:  ['Ds', 'Ds', 'Ds', 'Ds', 'Ds', 'S',  'S',  'H',  'H',  'H'],  # A,7 = soft 18
    8:  ['S',  'S',  'S',  'S',  'Ds', 'S',  'S',  'S',  'S',  'S'],  # A,8 = soft 19
    9:  ['S',  'S',  'S',  'S',  'S',  'S',  'S',  'S',  'S',  'S'],  # A,9 = soft 20
}

# H17 overrides for soft hands (S17→H17 player strategy changes)
_SOFT_H17_OVERRIDES: dict[tuple[int, int], str] = {
    (7, 2): 'S',   # A,7 vs 2: S17=Ds, H17=S (doubling less valuable when dealer hits soft 17)
}

# ---------------------------------------------------------------------------
# Pairs  (DAS; rows: pair card value 2–11)
# 5,5 is listed here but the engine never reaches it — it falls through to hard 10.
# ---------------------------------------------------------------------------
_PAIRS_DAS: dict[int, list[str]] = {
    #       2     3     4     5     6     7     8     9    10     A
    2:  ['P',  'P',  'P',  'P',  'P',  'P',  'H',  'H',  'H',  'H'],
    3:  ['P',  'P',  'P',  'P',  'P',  'P',  'H',  'H',  'H',  'H'],
    4:  ['H',  'H',  'H',  'P',  'P',  'H',  'H',  'H',  'H',  'H'],
    5:  ['D',  'D',  'D',  'D',  'D',  'D',  'D',  'D',  'H',  'H'],  # treat as hard 10
    6:  ['P',  'P',  'P',  'P',  'P',  'H',  'H',  'H',  'H',  'H'],
    7:  ['P',  'P',  'P',  'P',  'P',  'P',  'H',  'H',  'H',  'H'],
    8:  ['P',  'P',  'P',  'P',  'P',  'P',  'P',  'P',  'P',  'Rp'],
    9:  ['P',  'P',  'P',  'P',  'P',  'S',  'P',  'P',  'S',  'S'],
    10: ['S',  'S',  'S',  'S',  'S',  'S',  'S',  'S',  'S',  'S'],
    11: ['P',  'P',  'P',  'P',  'P',  'P',  'P',  'P',  'P',  'P'],  # A,A
}

# Without DAS: 2s/3s don't split vs 2-3; 4s never split; 6s don't split vs 2
_PAIRS_NO_DAS: dict[int, list[str]] = {
    2:  ['H',  'H',  'P',  'P',  'P',  'P',  'H',  'H',  'H',  'H'],
    3:  ['H',  'H',  'P',  'P',  'P',  'P',  'H',  'H',  'H',  'H'],
    4:  ['H',  'H',  'H',  'H',  'H',  'H',  'H',  'H',  'H',  'H'],
    5:  ['D',  'D',  'D',  'D',  'D',  'D',  'D',  'D',  'H',  'H'],
    6:  ['H',  'P',  'P',  'P',  'P',  'H',  'H',  'H',  'H',  'H'],
    7:  ['P',  'P',  'P',  'P',  'P',  'P',  'H',  'H',  'H',  'H'],
    8:  ['P',  'P',  'P',  'P',  'P',  'P',  'P',  'P',  'P',  'Rp'],
    9:  ['P',  'P',  'P',  'P',  'P',  'S',  'P',  'P',  'S',  'S'],
    10: ['S',  'S',  'S',  'S',  'S',  'S',  'S',  'S',  'S',  'S'],
    11: ['P',  'P',  'P',  'P',  'P',  'P',  'P',  'P',  'P',  'P'],
}


def get_basic_action(
    hand: Hand,
    dealer_upcard: int,
    das: bool = True,
    s17: bool = True,
) -> str:
    """
    Return the raw strategy code for the given hand vs dealer upcard.

    dealer_upcard: integer 2–10 or 11 (ace).
    """
    di = _DI[dealer_upcard]
    total = hand.total

    # Pair check first (except 5s — fall through to hard 10)
    if hand.is_pair and hand.pair_value != 5:
        pv = hand.pair_value  # 2-10 or 11 for aces
        table = _PAIRS_DAS if das else _PAIRS_NO_DAS
        return table[pv][di]

    # Soft hand
    if hand.is_soft:
        # Map soft total to non-ace key: soft 13→2, soft 20→9
        other = total - 11
        other = max(2, min(9, other))  # clamp to table range
        action = _SOFT[other][di]
        # Apply H17 override if needed
        if not s17:
            action = _SOFT_H17_OVERRIDES.get((other, dealer_upcard), action)
        return action

    # Hard hand
    capped = max(8, min(17, total))
    if total < 8:
        return 'H'
    if total > 17:
        return 'S'
    action = _HARD[capped][di]
    if not s17:
        action = _HARD_H17_OVERRIDES.get((capped, dealer_upcard), action)
    return action
