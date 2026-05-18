"""
TableSelector: score and rank blackjack tables by rule quality.

Uses the edge contributions from basic_strategy.RULE_EDGES.
Target: 6-deck, S17, DAS, RSA, late surrender, 3:2 BJ, ≥75% penetration.

NEVER play 6:5 blackjack — the 1.39% penalty makes it completely
unbeatable regardless of counting skill or penetration.
"""
from __future__ import annotations
from dataclasses import dataclass
from .basic_strategy import score_table_rules


@dataclass
class TableProfile:
    """Full description of a blackjack table's rules and conditions."""
    name: str = 'Unknown'
    num_decks: int = 6
    blackjack_pays: str = '3:2'      # '3:2' or '6:5'
    s17: bool = True                  # dealer stands/hits soft 17
    das: bool = True                  # double after split
    rsa: bool = False                 # re-split aces
    late_surrender: bool = True
    early_surrender: bool = False
    resplit_4: bool = False
    enhc: bool = False               # European no hole card
    min_bet: float = 25.0
    max_bet: float = 10_000.0
    penetration: float = 0.75        # estimated fraction of shoe dealt
    csm: bool = False                # continuous shuffle machine


class TableSelector:
    """
    Scores and ranks table profiles; recommends the best available table.

    Usage
    -----
    selector = TableSelector()
    selector.add(TableProfile('Aria BJ', num_decks=6, s17=True, das=True, ...))
    best = selector.recommend()
    """

    # Baseline house edge at 6-deck S17 no-DAS no-surrender (all edges relative to this)
    _BASELINE_HOUSE_EDGE: float = 0.0064   # 0.64%

    # Minimum penetration to consider a shoe game
    _MIN_PENETRATION: float = 0.67

    # Penetration EV adjustment (linear interpolation between known points)
    _PEN_EV: list[tuple[float, float]] = [
        (0.83, 0.009), (0.75, 0.006), (0.67, 0.003), (0.50, -0.001),
    ]

    def __init__(self) -> None:
        self._tables: list[TableProfile] = []

    def add(self, profile: TableProfile) -> None:
        self._tables.append(profile)

    def remove(self, name: str) -> None:
        self._tables = [t for t in self._tables if t.name != name]

    def score(self, table: TableProfile) -> float:
        """
        Return the estimated player edge (as fraction) at this table,
        accounting for rules + penetration. Negative = house edge.

        Never returns a positive value for CSM or 6:5 tables.
        """
        if table.csm:
            return -0.005   # CSMs are unplayable via counting

        if table.blackjack_pays == '6:5':
            return -0.015   # 6:5 adds ~1.4% house edge — never play

        if table.penetration < self._MIN_PENETRATION:
            return -0.002   # too shallow to count profitably

        # Base rule adjustments vs baseline house edge
        rule_adj = score_table_rules(
            blackjack_pays=table.blackjack_pays,
            s17=table.s17,
            das=table.das,
            rsa=table.rsa,
            late_surrender=table.late_surrender,
            early_surrender=table.early_surrender,
            resplit_4=table.resplit_4,
            num_decks=table.num_decks,
            enhc=table.enhc,
        )

        # Base player edge from counting (at 75% pen, 1:12 spread, Hi-Lo)
        # Interpolate penetration bonus
        pen_ev = self._pen_ev(table.penetration)

        # Total player edge vs flat neutral game
        # (house edge baseline) + rule adjustments + counting EV at given penetration
        total = -self._BASELINE_HOUSE_EDGE + rule_adj + pen_ev
        return total

    def _pen_ev(self, pen: float) -> float:
        """Interpolate counting EV from penetration."""
        pts = self._PEN_EV
        for i in range(len(pts) - 1):
            p_hi, ev_hi = pts[i]
            p_lo, ev_lo = pts[i + 1]
            if pen >= p_lo:
                frac = (pen - p_lo) / (p_hi - p_lo)
                return ev_lo + frac * (ev_hi - ev_lo)
        return pts[-1][1]

    def rank(self) -> list[tuple[TableProfile, float]]:
        """Return all tables sorted by score descending."""
        scored = [(t, self.score(t)) for t in self._tables]
        return sorted(scored, key=lambda x: x[1], reverse=True)

    def recommend(self) -> TableProfile | None:
        """Return the highest-scoring table, or None if no tables are registered."""
        ranked = self.rank()
        if not ranked:
            return None
        best, best_score = ranked[0]
        if best_score <= 0:
            return None   # no profitable table available
        return best

    def disqualified(self) -> list[TableProfile]:
        """Tables that should never be played (6:5 or CSM)."""
        return [t for t in self._tables if t.blackjack_pays == '6:5' or t.csm]

    def expected_value(self) -> float:
        """EV of the best available table, or 0 if none."""
        ranked = self.rank()
        return ranked[0][1] if ranked else 0.0

    def __repr__(self) -> str:
        n = len(self._tables)
        best = self.recommend()
        best_name = best.name if best else 'none'
        return f"TableSelector({n} tables, best={best_name!r})"
