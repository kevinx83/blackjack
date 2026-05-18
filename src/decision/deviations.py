"""
Index plays: Illustrious 18 + Sweet 16 surrender deviations.

Sources:
  Don Schlesinger, *Blackjack Attack* 3rd ed. (I18 + Sweet 16)
  Snyder, *Blackbelt in Blackjack* (surrender indices)

Each deviation specifies a true-count index. Depending on whether the play
fires ABOVE or BELOW the index, the engine substitutes the deviation action
for the basic-strategy code.

Notation
--------
'hard'  — keyed by player total (8-17)
'soft'  — keyed by the non-ace card value (2-9); soft 13=2, soft 20=9
'pair'  — keyed by pair card point value (2-11)
'ins'   — insurance side bet

Deviation action codes: same vocabulary as basic_strategy.py.
  'S'  Stand        'H'  Hit        'D'/'Dh' Double/Hit
  'Rh' Surrender/Hit  'Rp' Surrender/Split  'P' Split  'I' Insurance
"""
from __future__ import annotations
from .hand import Hand

# ---------------------------------------------------------------------------
# Deviation table
#
# Schema: (situation, dealer_upcard, index, action, fires_below)
#   situation    — classification key (see above)
#   dealer_upcard— integer 2-10 or 11 for ace, or None for insurance
#   index        — true-count threshold
#   action       — raw action code to return when deviation fires
#   fires_below  — True  → fire when TC < index  (negative-index plays)
#                  False → fire when TC >= index  (positive-index plays)
# ---------------------------------------------------------------------------

_DEVIATIONS: list[tuple] = [
    # ====================================================================
    # INSURANCE — single most valuable index play (~0.1–0.15% EV swing)
    # ====================================================================
    ('ins', None, 3, 'I', False),      # take insurance at TC >= +3

    # ====================================================================
    # ILLUSTRIOUS 18 (Schlesinger) — ordered by approximate EV contribution
    # ====================================================================

    # --- Hard hand deviations ---
    (('hard', 16), 10,  0,  'S',  False),  # 16 vs 10: STAND at TC >= 0      (basic: Rh)
    (('hard', 15), 10,  4,  'S',  False),  # 15 vs 10: STAND at TC >= +4     (basic: Rh)
    (('hard', 10), 10,  4,  'D',  False),  # 10 vs 10: DOUBLE at TC >= +4    (basic: H)
    (('hard', 10), 11,  4,  'D',  False),  # 10 vs A:  DOUBLE at TC >= +4    (basic: H)
    (('hard', 12),  3,  2,  'S',  False),  # 12 vs 3:  STAND at TC >= +2     (basic: H)
    (('hard', 12),  2,  3,  'S',  False),  # 12 vs 2:  STAND at TC >= +3     (basic: H)
    (('hard', 11), 11,  1,  'D',  False),  # 11 vs A:  DOUBLE at TC >= +1    (basic: H)
    (('hard',  9),  2,  1,  'D',  False),  # 9 vs 2:   DOUBLE at TC >= +1    (basic: H)
    (('hard',  9),  7,  3,  'D',  False),  # 9 vs 7:   DOUBLE at TC >= +3    (basic: H)
    (('hard', 16),  9,  5,  'S',  False),  # 16 vs 9:  STAND at TC >= +5     (basic: Rh)
    (('hard', 13),  2, -1,  'H',  True),   # 13 vs 2:  HIT at TC < -1        (basic: S)
    (('hard', 12),  4,  0,  'H',  True),   # 12 vs 4:  HIT at TC < 0         (basic: S)
    (('hard', 12),  5, -2,  'H',  True),   # 12 vs 5:  HIT at TC < -2        (basic: S)
    (('hard', 12),  6, -1,  'H',  True),   # 12 vs 6:  HIT at TC < -1        (basic: S)
    (('hard', 13),  3, -2,  'H',  True),   # 13 vs 3:  HIT at TC < -2        (basic: S)

    # --- Pair deviations ---
    (('pair', 10),  5,  5,  'P',  False),  # T,T vs 5: SPLIT at TC >= +5     (basic: S)
    (('pair', 10),  6,  4,  'P',  False),  # T,T vs 6: SPLIT at TC >= +4     (basic: S)

    # ====================================================================
    # SWEET 16 — surrender index plays (partial list; highest-value entries)
    #
    # Basic strategy (S17 6-deck):
    #   15 vs 10 = Rh, 16 vs 8/9/10 = Rh, 15/16 vs A = H
    #
    # At very negative TCs the deck is small-card-rich; hitting stiff hands
    # becomes less suicidal (you draw small cards more often). These plays
    # switch AWAY from surrender (Rh) back to Hit when TC drops below the
    # threshold.
    # ====================================================================

    # Negative-index surrenders: hit instead of surrender at low TCs
    (('hard', 16), 10, -1,  'H',  True),  # 16 vs 10: HIT at TC < -1  (basic: Rh → I18 at>=0 → S)
    (('hard', 16),  9,  0,  'H',  True),  # 16 vs 9:  HIT at TC < 0   (basic: Rh → I18 at>=5 → S)
    (('hard', 15), 10,  0,  'H',  True),  # 15 vs 10: HIT at TC < 0   (basic: Rh → I18 at>=4 → S)

    # Positive-index surrenders: surrender vs Ace when TC is high enough
    # (basic strategy for S17 is H for these, since EV(hit) > −0.5 at neutral)
    (('hard', 16), 11,  3,  'Rh', False), # 16 vs A:  SURRENDER at TC >= +3  (basic: H)
    (('hard', 15), 11,  5,  'Rh', False), # 15 vs A:  SURRENDER at TC >= +5  (basic: H)
]

# ---------------------------------------------------------------------------
# Build O(1) lookup
# Key:  (situation, dealer_upcard)
# Value: list of (index, action, fires_below) sorted by priority
#        Multiple deviations can apply to the same hand/upcard; the one
#        with the tightest matching condition wins (checked in order).
# ---------------------------------------------------------------------------

_LOOKUP: dict[tuple, list[tuple[int, str, bool]]] = {}

for _entry in _DEVIATIONS:
    _sit, _du, _idx, _act, _below = _entry
    _key = (_sit, _du)
    _LOOKUP.setdefault(_key, []).append((_idx, _act, _below))


def check_deviation(hand: Hand, dealer_upcard: int, true_count: float) -> str | None:
    """
    Return a deviation action code when a count-based index play applies,
    or None to fall back to basic strategy.

    Insurance is handled separately via BlackjackAdvisor.insurance_advised();
    the 'ins' entry exists only for completeness and is excluded here.

    dealer_upcard: 2–10, or 11 for ace.
    true_count:   current Hi-Lo true count (float).
    """
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

    entries = _LOOKUP.get((sit, dealer_upcard))
    if entries is None:
        return None

    # Multiple entries for the same (sit, dealer): evaluate all; first match wins.
    # Positive-index plays are checked in TC-descending order so the highest
    # threshold takes priority (e.g. I18 Stand overrides Sweet 16 Surrender).
    for idx, act, fires_below in entries:
        if fires_below:
            if true_count < idx:
                return act
        else:
            if true_count >= idx:
                return act

    return None


def insurance_index(true_count: float) -> bool:
    """True when the count justifies taking insurance (Hi-Lo TC >= +3)."""
    return true_count >= 3
