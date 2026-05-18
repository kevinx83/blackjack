"""
Illustrious 18 index plays for Hi-Lo, 6-deck, S17.

Each entry specifies a breakeven true count (index). At or above the index,
play the deviation action; below it, fall back to basic strategy (returned
as None so the engine calls basic_strategy.get_basic_action).

Sources: Don Schlesinger, *Blackjack Attack*, 3rd ed.
"""
from __future__ import annotations
from .hand import Hand

# ---------------------------------------------------------------------------
# Deviation table
#
# Schema: (situation, dealer_upcard, index, action_at_or_above)
#
# situation:
#   ('hard', total)   — hard hand by total
#   ('soft', other)   — soft hand; other = non-ace card value (2–9)
#   ('pair', value)   — pair by card value
#   'insurance'       — insurance side bet
#
# action_at_or_above: raw action code (same vocabulary as basic_strategy.py)
#   None means "check this entry only when it overrides basic strategy"
#
# For negative-index entries (index < 0), the semantic is inverted:
#   if TC < index → override basic; else → basic applies.
#   These are encoded as (situation, dealer, index, action_BELOW_index).
#   The `_NEG_INDEX` set lists these.
# ---------------------------------------------------------------------------

_DEVIATIONS: list[tuple] = [
    # --- Insurance ---
    ('insurance', None, 3,  'I'),

    # --- Hard hand deviations ---
    (('hard', 16), 10,  0,  'S'),   # 16 vs 10: stand at TC >= 0  (basic: Rh)
    (('hard', 16),  9,  5,  'S'),   # 16 vs 9:  stand at TC >= 5  (basic: Rh)
    (('hard', 15), 10,  4,  'S'),   # 15 vs 10: stand at TC >= 4  (basic: Rh)
    (('hard', 13),  2, -1,  'H'),   # 13 vs 2:  hit   at TC < -1  (basic: S)
    (('hard', 12),  2,  3,  'S'),   # 12 vs 2:  stand at TC >= 3  (basic: H)
    (('hard', 12),  3,  2,  'S'),   # 12 vs 3:  stand at TC >= 2  (basic: H)
    (('hard', 12),  4,  0,  'H'),   # 12 vs 4:  hit   at TC < 0   (basic: S)
    (('hard', 12),  5, -2,  'H'),   # 12 vs 5:  hit   at TC < -2  (basic: S)
    (('hard', 12),  6, -1,  'H'),   # 12 vs 6:  hit   at TC < -1  (basic: S)
    (('hard', 13),  3, -2,  'H'),   # 13 vs 3:  hit   at TC < -2  (basic: S)
    (('hard', 10), 10,  4,  'D'),   # 10 vs 10: double at TC >= 4 (basic: H)
    (('hard', 10), 11,  4,  'D'),   # 10 vs A:  double at TC >= 4 (basic: H)
    (('hard',  9),  2,  1,  'D'),   # 9  vs 2:  double at TC >= 1 (basic: H)
    (('hard',  9),  7,  3,  'D'),   # 9  vs 7:  double at TC >= 3 (basic: H)

    # --- Pair deviations ---
    (('pair', 10),  5,  5,  'P'),   # T,T vs 5: split at TC >= 5 (basic: S)
    (('pair', 10),  6,  4,  'P'),   # T,T vs 6: split at TC >= 4 (basic: S)
]

# Entries where the override fires when TC is *below* the index.
# (The stored action is what to do when TC < index, overriding basic.)
_BELOW_INDEX: set[int] = {
    # indices into _DEVIATIONS that are negative-index / inverted plays
}

# Pre-build a lookup set for quick scanning.
# Key: (situation, dealer_upcard)  → (index, action_above, is_below_index)
_LOOKUP: dict[tuple, tuple[int, str, bool]] = {}

# Entries where action fires when TC < index (not >=)
_NEGATIVE_INDEX_SITUATIONS = {
    (('hard', 13), 2),
    (('hard', 12), 4),
    (('hard', 12), 5),
    (('hard', 12), 6),
    (('hard', 13), 3),
}

for _entry in _DEVIATIONS:
    _sit, _du, _idx, _act = _entry
    _key = (_sit, _du)
    _is_neg = _key in _NEGATIVE_INDEX_SITUATIONS
    _LOOKUP[_key] = (_idx, _act, _is_neg)


def check_deviation(hand: Hand, dealer_upcard: int, true_count: float) -> str | None:
    """
    Return a deviation action code if a count-based index play applies,
    or None to signal that basic strategy should be used.

    Insurance is a side-bet handled separately via BlackjackAdvisor.insurance_advised();
    it is intentionally excluded here so it never overrides the hand-play decision.

    dealer_upcard: 2–10, or 11 for ace.
    true_count:   current Hi-Lo true count (float).
    """
    # Determine situation key from hand
    sit: tuple | None = None
    if hand.is_pair and hand.pair_value != 5:
        sit = ('pair', hand.pair_value)
    elif hand.is_soft:
        other = max(2, min(9, hand.total - 11))
        sit = ('soft', other)
    else:
        total = hand.total
        if 8 <= total <= 17:
            sit = ('hard', total)

    if sit is None:
        return None

    entry = _LOOKUP.get((sit, dealer_upcard))
    if entry is None:
        return None

    idx, act, is_neg = entry
    if is_neg:
        # Negative-index play: override fires when TC is *below* the index
        return act if true_count < idx else None
    else:
        return act if true_count >= idx else None
