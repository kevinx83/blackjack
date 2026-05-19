"""
Basic strategy tables for 6-deck blackjack.

Supports S17 (dealer stands on soft 17) and H17 (dealer hits soft 17),
DAS (double after split) and no-DAS, late surrender.

Action codes
------------
H   Hit
S   Stand
D   Double (else Hit)
Dh  Double (else Hit)   [synonym for D]
Ds  Double (else Stand)
Rh  Surrender (else Hit)
Rs  Surrender (else Stand)
Rp  Surrender (else Split)
P   Split

Sources: Griffin "Theory of Blackjack", Schlesinger "Blackjack Attack",
         Wizard of Odds 6-deck strategy calculator.
"""
from __future__ import annotations
from .hand import Hand

# Dealer upcard column index: 2→0, 3→1, … 10→8, A(11)→9
_DI = {2: 0, 3: 1, 4: 2, 5: 3, 6: 4, 7: 5, 8: 6, 9: 7, 10: 8, 11: 9}

# ---------------------------------------------------------------------------
# Hard totals — 6-deck S17, DAS, late surrender
# Row key: player total (8–17); below 8 → H; above 17 → S
# ---------------------------------------------------------------------------
_HARD: dict[int, list[str]] = {
    #       2     3     4     5     6     7     8     9    10     A
    8:  ['H',  'H',  'H',  'H',  'H',  'H',  'H',  'H',  'H',  'H'],
    9:  ['H',  'D',  'D',  'D',  'D',  'H',  'H',  'H',  'H',  'H'],
    10: ['D',  'D',  'D',  'D',  'D',  'D',  'D',  'D',  'H',  'H'],
    11: ['D',  'D',  'D',  'D',  'D',  'D',  'D',  'D',  'D',  'D'],
    12: ['H',  'H',  'S',  'S',  'S',  'H',  'H',  'H',  'H',  'H'],
    13: ['S',  'S',  'S',  'S',  'S',  'H',  'H',  'H',  'H',  'H'],
    14: ['S',  'S',  'S',  'S',  'S',  'H',  'H',  'H',  'H',  'H'],
    15: ['S',  'S',  'S',  'S',  'S',  'H',  'H',  'H',  'Rh', 'H'],
    #    ^stand vs 2-6   ^hit vs 7,8,9   ^surrender vs 10  ^hit vs A (S17)
    16: ['S',  'S',  'S',  'S',  'S',  'H',  'Rh', 'Rh', 'Rh', 'H'],
    #    ^stand vs 2-6   ^H vs 7  ^Rh vs 8,9,10             ^H vs A (S17)
    17: ['S',  'S',  'S',  'S',  'S',  'S',  'S',  'S',  'S',  'S'],
}

# S17 note: hard 15 vs A and hard 16 vs A are HIT (not surrender) because:
#   EV(hit 15 vs A, S17) ≈ −0.475 > −0.500 = EV(surrender)
#   EV(hit 16 vs A, S17) ≈ −0.492 > −0.500 = EV(surrender)
# At positive true counts (TC ≥ +3 for 16vA, TC ≥ +5 for 15vA) Sweet 16
# index plays switch these to surrender (handled in deviations.py).
# For H17 these EVs cross below −0.5 so basic strategy there is Rh.

# H17 hard overrides (only the cells that differ from S17)
_HARD_H17_OVERRIDES: dict[tuple[int, int], str] = {
    (15, 11): 'Rh',  # hard 15 vs A: S17=H, H17=Rh (hit EV ≈ −0.51 in H17)
    (16, 11): 'Rh',  # hard 16 vs A: S17=H, H17=Rh (hit EV ≈ −0.53 in H17)
    (17, 11): 'Rs',  # hard 17 vs A: S17=S, H17=Rs  (dealer can improve soft 17)
}

# ---------------------------------------------------------------------------
# Soft totals — non-ace card value 2–9 (giving soft 13–soft 20)
# ---------------------------------------------------------------------------
_SOFT: dict[int, list[str]] = {
    #       2     3     4     5     6     7     8     9    10     A
    2:  ['H',  'H',  'D',  'D',  'D',  'H',  'H',  'H',  'H',  'H'],  # A,2=soft 13
    3:  ['H',  'H',  'D',  'D',  'D',  'H',  'H',  'H',  'H',  'H'],  # A,3=soft 14
    4:  ['H',  'H',  'D',  'D',  'D',  'H',  'H',  'H',  'H',  'H'],  # A,4=soft 15
    5:  ['H',  'H',  'D',  'D',  'D',  'H',  'H',  'H',  'H',  'H'],  # A,5=soft 16
    6:  ['H',  'D',  'D',  'D',  'D',  'H',  'H',  'H',  'H',  'H'],  # A,6=soft 17
    7:  ['Ds', 'Ds', 'Ds', 'Ds', 'Ds', 'S',  'S',  'H',  'H',  'H'],  # A,7=soft 18
    8:  ['S',  'S',  'S',  'S',  'Ds', 'S',  'S',  'S',  'S',  'S'],  # A,8=soft 19
    9:  ['S',  'S',  'S',  'S',  'S',  'S',  'S',  'S',  'S',  'S'],  # A,9=soft 20
}

# H17 soft overrides
_SOFT_H17_OVERRIDES: dict[tuple[int, int], str] = {
    (7, 2):  'S',   # A,7 vs 2:  S17=Ds → H17=S
    (8, 6):  'S',   # A,8 vs 6:  S17=Ds → H17=S
    (6, 2):  'D',   # A,6 vs 2:  S17=H  → H17=D (more aggressive when dealer hits s17)
    (7, 11): 'H',   # A,7 vs A:  S17=H  → H17=H (same, listed for clarity)
}

# ---------------------------------------------------------------------------
# Pairs — DAS variant (rows: pair card value 2–11)
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
    11: ['P',  'P',  'P',  'P',  'P',  'P',  'P',  'P',  'P',  'P'],  # A,A always split
}

# No-DAS: 2s/3s don't split vs 2-3; 4s never split; 6s don't split vs 2
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

# ---------------------------------------------------------------------------
# Rule edge contributions (for TableSelector)
# ---------------------------------------------------------------------------
RULE_EDGES: dict[str, float] = {
    'blackjack_3_2':          +0.0,    # baseline: 3:2 pays
    'blackjack_6_5':          -1.394,  # devastating: never play 6:5
    's17':                    +0.0,    # baseline
    'h17':                    -0.22,   # dealer hits soft 17 costs player
    'das':                    +0.14,   # double after split
    'rsa':                    +0.08,   # re-split aces
    'late_surrender':         +0.08,   # late surrender
    'early_surrender':        +0.62,   # extremely rare and valuable
    'resplit_4_hands':        +0.05,   # up to 4 splits
    '6_deck_vs_8_deck':       +0.02,   # fewer decks slightly better
    'single_deck_vs_6_deck':  +0.58,   # but only fair with deep pen
    'no_hole_card_enhc':      -0.11,   # European no hole card
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

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

    # --- Pair (except 5s which fall through to hard 10) ---
    if hand.is_pair and hand.pair_value != 5:
        pv = hand.pair_value   # 2-10 or 11 for aces
        table = _PAIRS_DAS if das else _PAIRS_NO_DAS
        return table[pv][di]

    # --- Soft hand ---
    if hand.is_soft:
        other = total - 11
        other = max(2, min(9, other))
        action = _SOFT[other][di]
        if not s17:
            action = _SOFT_H17_OVERRIDES.get((other, dealer_upcard), action)
        return action

    # --- Hard hand ---
    if total < 8:
        return 'H'
    if total > 17:
        return 'S'
    capped = max(8, min(17, total))
    action = _HARD[capped][di]
    if not s17:
        action = _HARD_H17_OVERRIDES.get((capped, dealer_upcard), action)
    return action


def get_hard_fallback(total: int, dealer_upcard: int, s17: bool = True) -> str:
    """Hard-total-only lookup used when a pair cannot be split."""
    di = _DI[dealer_upcard]
    if total < 8:
        return 'H'
    if total > 17:
        return 'S'
    capped = max(8, min(17, total))
    action = _HARD[capped][di]
    if not s17:
        action = _HARD_H17_OVERRIDES.get((capped, dealer_upcard), action)
    return action


def score_table_rules(
    blackjack_pays: str = '3:2',
    s17: bool = True,
    das: bool = True,
    rsa: bool = False,
    late_surrender: bool = True,
    early_surrender: bool = False,
    resplit_4: bool = False,
    num_decks: int = 6,
    enhc: bool = False,
) -> float:
    """
    Compute cumulative player edge from rule variations vs a 6-deck S17
    no-DAS baseline (house edge ≈ 0.64%).

    Returns total player edge adjustment as a fraction (e.g. +0.14% = 0.0014).
    """
    edge = 0.0
    if blackjack_pays == '6:5':
        edge += RULE_EDGES['blackjack_6_5']
    if not s17:        # H17 is the disadvantageous variant
        edge += RULE_EDGES['h17']
    if das:
        edge += RULE_EDGES['das']
    if rsa:
        edge += RULE_EDGES['rsa']
    if late_surrender:
        edge += RULE_EDGES['late_surrender']
    if early_surrender:
        edge += RULE_EDGES['early_surrender']
    if resplit_4:
        edge += RULE_EDGES['resplit_4_hands']
    if num_decks == 1:
        edge += RULE_EDGES['single_deck_vs_6_deck']
    elif num_decks <= 6:
        edge += RULE_EDGES['6_deck_vs_8_deck'] * (8 - num_decks) / 2
    if enhc:
        edge += RULE_EDGES['no_hole_card_enhc']
    return edge
