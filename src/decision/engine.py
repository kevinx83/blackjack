"""
BlackjackAdvisor — unified advantage play engine.

Integrates every module:
  BasicStrategy      → mathematically correct play lookup
  MultiCounter       → Hi-Lo + 4 alternate counting systems
  BetSpreader        → 1:12 Kelly-based bet sizing + wonging
  IndexPlays         → Illustrious 18 + Sweet 16 (I18+S16)
  BankrollManager    → Kelly criterion + risk-of-ruin
  ShoeEvaluator      → penetration + CSM detection
  HeatManager        → casino heat score + camouflage
  TableSelector      → rule scoring
  SideBetEvaluator   → count-dependent side bet edge
  ExploitEngine      → EXPLOIT_CLASS (simulation research only)

Public interface:
  advisor = BlackjackAdvisor(num_decks=6, das=True, s17=True, surrender=True)
  advisor.observe(*cards)          # update count
  rec = advisor.recommend(hand, dealer_upcard)  # get Recommendation
  advisor.insurance_advised()      # check insurance index
  advisor.new_shoe()               # reset counter
  advisor.expected_value()         # current player edge
"""
from __future__ import annotations
from dataclasses import dataclass, field

from .hand import Hand, Card
from .basic_strategy import get_basic_action, get_hard_fallback
from .deviations import check_deviation, insurance_index
from .count import MultiCounter
from .bet_spreader import BetSpreader, bet_units_for_true_count
from .bankroll_manager import BankrollManager, edge_at_tc
from .shoe_evaluator import ShoeEvaluator
from .heat_manager import HeatManager
from .table_selector import TableSelector, TableProfile
from .side_bet_evaluator import SideBetEvaluator

# ---------------------------------------------------------------------------
# Action constants (public API)
# ---------------------------------------------------------------------------
HIT       = 'HIT'
STAND     = 'STAND'
DOUBLE    = 'DOUBLE'
SPLIT     = 'SPLIT'
SURRENDER = 'SURRENDER'
INSURANCE = 'INSURANCE'


# ---------------------------------------------------------------------------
# Recommendation dataclass
# ---------------------------------------------------------------------------

@dataclass
class Recommendation:
    """Complete recommendation for one playing decision."""
    action:       str     # HIT / STAND / DOUBLE / SPLIT / SURRENDER
    raw_code:     str     # raw strategy code before resolution (e.g. 'Rh', 'Ds')
    is_deviation: bool    # True when an index play overrides basic strategy
    true_count:   float   # current Hi-Lo true count
    bet_units:    int     # suggested bet size in units (1–12)
    bet_dollars:  float   # suggested bet in dollars (if bankroll known)
    player_edge:  float   # current player edge as a fraction
    reasoning:    str     # human-readable explanation

    # Extended fields (optional, filled when available)
    heat_level:    str   = 'cool'
    should_wong_out: bool = False
    side_bets:     list  = field(default_factory=list)


# ---------------------------------------------------------------------------
# Action resolver
# ---------------------------------------------------------------------------

def _resolve(
    code: str,
    can_double: bool,
    can_split: bool,
    can_surrender: bool,
) -> str:
    """Map a raw strategy code to a final action given current table options."""
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
        return f"{base} [INDEX PLAY TC{tc:+.1f}, code={raw_code}]"
    return f"{base} [basic strategy, code={raw_code}]"


# ---------------------------------------------------------------------------
# BlackjackAdvisor
# ---------------------------------------------------------------------------

class BlackjackAdvisor:
    """
    Stateful advantage play engine.

    Tracks the running count, manages bet sizing, fires index plays,
    and integrates all supporting modules into one unified interface.

    Parameters
    ----------
    num_decks     : decks in shoe (1, 2, 4, 6, 8)
    das           : double after split allowed
    s17           : dealer stands on soft 17 (False = H17)
    surrender     : late surrender available
    unit          : minimum bet in dollars (one unit)
    bankroll      : starting bankroll; enables Kelly sizing when set
    wonging       : enable Wonging (back-count, enter only on positive counts)
    wonging_entry : true count threshold to sit down / start betting
    wonging_exit  : true count threshold to leave table
    camouflage_variance : fraction of rounds to vary bet ±1 unit for cover
    kelly_divisor : 1=full Kelly, 2=half Kelly (recommended), 4=quarter Kelly
    """

    def __init__(
        self,
        num_decks: int = 6,
        das: bool = True,
        s17: bool = True,
        surrender: bool = True,
        unit: float = 25.0,
        bankroll: float | None = None,
        wonging: bool = True,
        wonging_entry: float = 2.0,
        wonging_exit: float = 0.0,
        camouflage_variance: float = 0.0,
        kelly_divisor: float = 2.0,
        min_penetration: float = 0.75,
    ) -> None:
        self.num_decks       = num_decks
        self.das             = das
        self.s17             = s17
        self.surrender       = surrender
        self.unit            = unit

        # Core counting engine
        self.counter = MultiCounter(num_decks)

        # Bet sizing
        self.bet_spreader = BetSpreader(
            unit=unit,
            max_spread=12,
            kelly_divisor=kelly_divisor,
            camouflage_variance=camouflage_variance,
            wonging_entry_tc=wonging_entry,
            wonging_exit_tc=wonging_exit,
            wonging_enabled=wonging,
        )

        # Bankroll management
        self.bankroll_manager = BankrollManager(
            bankroll=bankroll or (unit * 400),  # default: 400 units
            unit=unit,
            kelly_divisor=kelly_divisor,
        ) if bankroll is not None else None

        # Shoe / penetration tracking
        self.shoe_evaluator = ShoeEvaluator(
            num_decks=num_decks,
            min_penetration=min_penetration,
        )

        # Heat management
        self.heat_manager = HeatManager()

        # Side bet evaluation
        self.side_bet_evaluator = SideBetEvaluator()

    # ------------------------------------------------------------------
    # Count maintenance
    # ------------------------------------------------------------------

    def observe(self, *cards: Card) -> None:
        """Record visible cards; updates running count for all systems."""
        for card in cards:
            self.counter.add_card(card.rank)
        self.shoe_evaluator.observe_cards(len(cards))

    def new_shoe(self) -> None:
        """Reset all counters for a new shoe."""
        self.counter.reset()
        self.shoe_evaluator.observe_shuffle()

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

        can_double / can_split reflect current table options and hand state
        (e.g. False after hitting, or when table rules prohibit it).
        """
        dealer_val   = dealer_upcard.value   # 2–11
        tc           = self.counter.true_count(decks_remaining)
        tc_int       = self.counter.true_count_int(decks_remaining)
        can_surr     = self.surrender

        # --- Deviation check first (I18 + Sweet 16) ---
        raw          = check_deviation(player_hand, dealer_val, tc_int)
        is_deviation = raw is not None
        if raw is None:
            raw = get_basic_action(player_hand, dealer_val, self.das, self.s17)

        # --- Restrict options not currently available ---
        if not can_double and raw in ('D', 'Dh', 'Ds'):
            raw = 'S' if raw == 'Ds' else 'H'
        if not can_split:
            if raw == 'P':
                raw = get_hard_fallback(player_hand.total, dealer_val, self.s17)
            elif raw == 'Rp':
                raw = 'Rh'   # 8,8 vs A treated as hard 16 vs A

        final  = _resolve(raw, can_double, can_split, can_surr)

        # --- Bet sizing ---
        bet_tc = self.counter.betting_tc(decks_remaining)
        units  = self.bet_spreader.recommend_units(bet_tc)
        dollars = (
            self.bankroll_manager.kelly_bet(bet_tc)
            if self.bankroll_manager
            else units * self.unit
        )

        # --- Player edge ---
        edge = edge_at_tc(tc)

        # --- Wonging ---
        wong_out = self.bet_spreader.should_leave(tc)

        # --- Heat ---
        heat_label = self.heat_manager.heat_label()

        # --- Side bets ---
        recs = self.side_bet_evaluator.recommended_bets(tc)
        side_bet_names = [r.name for r in recs]

        reason = _explain(player_hand, dealer_upcard, raw, final, is_deviation, tc)

        return Recommendation(
            action        = final,
            raw_code      = raw,
            is_deviation  = is_deviation,
            true_count    = tc,
            bet_units     = units,
            bet_dollars   = dollars,
            player_edge   = edge,
            reasoning     = reason,
            heat_level    = heat_label,
            should_wong_out = wong_out,
            side_bets     = side_bet_names,
        )

    def insurance_advised(self, decks_remaining: float | None = None) -> bool:
        """True when the count justifies taking insurance (Hi-Lo TC >= +3)."""
        tc = self.counter.insurance_tc(decks_remaining)
        return insurance_index(tc)

    # ------------------------------------------------------------------
    # Pre-round bet recommendation (before cards are dealt)
    # ------------------------------------------------------------------

    def recommend_bet(self, decks_remaining: float | None = None) -> dict:
        """
        Pre-round bet recommendation before any cards are dealt.

        Returns a dict with:
          units          : suggested bet in units (1–12)
          dollars        : suggested dollar bet
          should_play    : False if wonging and TC below entry threshold
          should_leave   : True if TC dropped below exit threshold
          true_count     : current Hi-Lo TC (ace-adjusted for betting)
          player_edge    : estimated player edge at this count
        """
        tc     = self.counter.betting_tc(decks_remaining)
        units  = self.bet_spreader.recommend_units(tc)
        dollars = (
            self.bankroll_manager.kelly_bet(tc)
            if self.bankroll_manager
            else units * self.unit
        )
        return {
            'units':        units,
            'dollars':      dollars,
            'should_play':  self.bet_spreader.should_play(tc),
            'should_leave': self.bet_spreader.should_leave(tc) or self.shoe_evaluator.should_leave(),
            'true_count':   tc,
            'player_edge':  edge_at_tc(tc),
            'penetration':  self.shoe_evaluator.penetration,
            'heat':         self.heat_manager.heat_label(),
        }

    # ------------------------------------------------------------------
    # Session management
    # ------------------------------------------------------------------

    def settle(self, net_units: float) -> None:
        """Record the result of a hand for bankroll tracking."""
        if self.bankroll_manager:
            self.bankroll_manager.settle(net_units)
        self.heat_manager.record_hand()

    def start_session(self, casino_name: str = 'default') -> None:
        self.heat_manager.select_casino(casino_name)
        if self.bankroll_manager:
            self.bankroll_manager.new_session()

    def end_session(self) -> None:
        self.heat_manager.end_session()

    # ------------------------------------------------------------------
    # Overall expected value
    # ------------------------------------------------------------------

    def expected_value(self) -> float:
        """
        Current player edge as a fraction (positive = player advantage).
        Accounts for TC, penetration, and camouflage costs.
        """
        tc = self.counter.true_count()
        base_ev = edge_at_tc(tc)
        pen_ev   = self.shoe_evaluator.expected_ev() - 0.006  # pen adj vs baseline
        camo_cost = self.heat_manager.camouflage_ev_cost()
        return base_ev + pen_ev - camo_cost

    # ------------------------------------------------------------------
    # State snapshot (for web server / display)
    # ------------------------------------------------------------------

    def state(self) -> dict:
        """Full state snapshot for display or API responses."""
        tc = self.counter.true_count()
        bet_info = self.recommend_bet()
        return {
            'true_count':       tc,
            'running_count':    self.counter.running_count,
            'decks_remaining':  self.counter.decks_remaining(),
            'cards_seen':       self.counter.cards_seen,
            'aces_seen':        self.counter.aces_seen,
            'deck_penetration': self.counter.deck_penetration,
            'ace_adjusted_tc':  self.counter.betting_tc(),
            'player_edge':      self.expected_value(),
            'recommended_bet':  bet_info,
            'heat':             self.heat_manager.heat_label(),
            'shoe_rating':      self.shoe_evaluator.rating.label,
            'should_leave':     self.shoe_evaluator.should_leave(),
            'insurance_advised': self.insurance_advised(),
        }

    def __repr__(self) -> str:
        return (
            f"BlackjackAdvisor(decks={self.num_decks}, "
            f"das={self.das}, s17={self.s17}, "
            f"tc={self.counter.true_count():.1f}, "
            f"ev={self.expected_value():+.3f})"
        )
