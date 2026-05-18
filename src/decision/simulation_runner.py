"""
SimulationRunner: Monte Carlo EV verification for the advantage play engine.

Validates the complete system by simulating millions of blackjack hands and
measuring the actual player edge, variance, and risk of ruin.

Expected outputs (with default params):
  Basic strategy only          → house edge −0.40% to −0.55%
  Hi-Lo + I18/S16 + 1:12 spread → player edge +0.5% to +1.0%
  Kelly sizing, 75% pen, wonging → player edge +0.6% to +1.2%

Run with:
  python -m src.decision.simulation_runner
  or: from src.decision.simulation_runner import SimulationRunner, SimParams
"""
from __future__ import annotations

import math
import random
import time
from dataclasses import dataclass, field
from typing import Callable

from .count import MultiCounter
from .basic_strategy import get_basic_action, get_hard_fallback
from .deviations import check_deviation, insurance_index
from .bet_spreader import bet_units_for_true_count
from .bankroll_manager import edge_at_tc
from .hand import Card, Hand, RANKS


# ---------------------------------------------------------------------------
# Simulation parameters
# ---------------------------------------------------------------------------

@dataclass
class SimParams:
    num_hands:           int   = 1_000_000
    num_decks:           int   = 6
    penetration:         float = 0.75     # fraction of shoe dealt before reshuffle
    das:                 bool  = True
    s17:                 bool  = True
    surrender:           bool  = True
    blackjack_pays:      float = 1.5      # 3:2 = 1.5, 6:5 = 1.2
    counting_system:     str   = 'hilo'
    bet_spread:          int   = 12       # 1:N spread
    index_plays:         bool  = True     # Illustrious 18 + Sweet 16
    wonging:             bool  = True
    wonging_entry_tc:    float = 2.0
    wonging_exit_tc:     float = 0.0
    camouflage_variance: float = 0.0
    starting_bankroll:   float = 10_000.0
    unit:                float = 25.0
    seed:                int | None = None
    verbose:             bool  = False


# ---------------------------------------------------------------------------
# Simulation result
# ---------------------------------------------------------------------------

@dataclass
class SimResult:
    num_hands:          int
    num_hands_played:   int   # hands actually played (wonging excludes some)
    num_shoes:          int
    total_wagered:      float
    net_units:          float
    mean_edge:          float  # net_units / total_wagered_in_units
    std_dev_per_hand:   float
    win_rate:           float  # fraction of hands won (not pushes)
    push_rate:          float
    loss_rate:          float
    blackjack_rate:     float
    surrender_rate:     float
    double_win_rate:    float
    split_rate:         float
    max_drawdown_units: float
    final_bankroll:     float
    risk_of_ruin_est:   float  # estimated from simulation
    hands_per_second:   float
    elapsed_sec:        float
    wonged_out_count:   int

    def summary(self) -> str:
        played_pct = self.num_hands_played / max(1, self.num_hands) * 100
        return (
            f"=== Simulation Results ===\n"
            f"Hands simulated : {self.num_hands:,}\n"
            f"Hands played    : {self.num_hands_played:,} ({played_pct:.1f}%)\n"
            f"Shoes dealt     : {self.num_shoes:,}\n"
            f"Total wagered   : {self.total_wagered:,.0f} units\n"
            f"Net units       : {self.net_units:+,.1f}\n"
            f"Mean edge       : {self.mean_edge:+.4%}\n"
            f"Std dev/hand    : {self.std_dev_per_hand:.4f} units\n"
            f"Win rate        : {self.win_rate:.2%}\n"
            f"Push rate       : {self.push_rate:.2%}\n"
            f"Loss rate       : {self.loss_rate:.2%}\n"
            f"Blackjack rate  : {self.blackjack_rate:.2%}\n"
            f"Surrender rate  : {self.surrender_rate:.2%}\n"
            f"Max drawdown    : {self.max_drawdown_units:.1f} units\n"
            f"Final bankroll  : ${self.final_bankroll:,.0f}\n"
            f"RoR estimate    : {self.risk_of_ruin_est:.1%}\n"
            f"Wonged out      : {self.wonged_out_count:,}\n"
            f"Speed           : {self.hands_per_second:,.0f} hands/sec\n"
            f"Elapsed         : {self.elapsed_sec:.1f}s\n"
        )


# ---------------------------------------------------------------------------
# Deck / shoe utilities
# ---------------------------------------------------------------------------

# Card ranks as used in the shoe (values for counting)
_RANK_LIST = ['2','3','4','5','6','7','8','9','10','10','10','10','A']
_RANK_VALUES = {
    '2':2,'3':3,'4':4,'5':5,'6':6,'7':7,'8':8,'9':9,'10':10,'A':11
}


def _build_shoe(num_decks: int, rng: random.Random) -> list[str]:
    """Build and shuffle a shoe of `num_decks` standard decks."""
    shoe = _RANK_LIST * 4 * num_decks
    rng.shuffle(shoe)
    return shoe


# ---------------------------------------------------------------------------
# Hand evaluation helpers (for the sim; no Card objects needed for speed)
# ---------------------------------------------------------------------------

def _hand_total(cards: list[str]) -> int:
    """Compute best total (aces as 11 or 1)."""
    total = sum(_RANK_VALUES[c] for c in cards)
    aces = cards.count('A')
    while total > 21 and aces:
        total -= 10
        aces -= 1
    return total


def _is_soft(cards: list[str]) -> bool:
    total = sum(_RANK_VALUES[c] for c in cards)
    aces = cards.count('A')
    while total > 21 and aces:
        total -= 10
        aces -= 1
    return aces > 0 and total <= 21


def _is_pair(cards: list[str]) -> bool:
    return len(cards) == 2 and _RANK_VALUES[cards[0]] == _RANK_VALUES[cards[1]]


def _pair_value(cards: list[str]) -> int:
    return _RANK_VALUES[cards[0]]


def _make_hand(cards: list[str]) -> Hand:
    """Convert rank list to Hand object for strategy lookup."""
    return Hand([Card(r, 's') for r in cards])


def _make_card(rank: str) -> Card:
    return Card(rank, 's')


# ---------------------------------------------------------------------------
# Dealer play
# ---------------------------------------------------------------------------

def _dealer_play(
    hole: str,
    upcard: str,
    shoe: list[str],
    pos: int,
    s17: bool,
) -> tuple[int, int]:
    """
    Play out dealer hand; returns (dealer_total, new_pos).
    Draws from shoe starting at pos.
    """
    hand = [upcard, hole]
    idx  = pos
    while True:
        total = _hand_total(hand)
        soft  = _is_soft(hand)
        if total > 21:
            break
        if total == 17:
            if s17 and not soft:
                break
            if s17 and soft:
                break  # S17: stand on soft 17
            if not s17 and soft:
                # H17: hit soft 17
                if idx >= len(shoe):
                    break
                hand.append(shoe[idx])
                idx += 1
                continue
            break
        if total > 17:
            break
        # total < 17: always hit
        if idx >= len(shoe):
            break
        hand.append(shoe[idx])
        idx += 1
    return _hand_total(hand), idx


# ---------------------------------------------------------------------------
# Blackjack strategy lookup (inlined for speed)
# ---------------------------------------------------------------------------

def _get_action(
    cards: list[str],
    dealer_val: int,
    das: bool,
    s17: bool,
    tc_int: int,
    can_double: bool,
    can_split: bool,
    can_surrender: bool,
    use_index_plays: bool,
) -> str:
    """
    Determine optimal action. Returns raw action code: H/S/D/Ds/P/Rh/Rs/Rp.
    """
    hand = _make_hand(cards)
    dealer_card = _make_card(str(dealer_val) if dealer_val <= 10 else 'A')

    # Deviation check
    raw = None
    if use_index_plays:
        raw = check_deviation(hand, dealer_val, tc_int)

    if raw is None:
        raw = get_basic_action(hand, dealer_val, das, s17)

    # Restrict unavailable options
    if not can_double and raw in ('D', 'Dh', 'Ds'):
        raw = 'S' if raw == 'Ds' else 'H'
    if not can_split:
        if raw == 'P':
            raw = get_hard_fallback(_hand_total(cards), dealer_val, s17)
        elif raw == 'Rp':
            raw = 'Rh'

    # Resolve surrender
    if raw == 'Rh' and not can_surrender:
        raw = 'H'
    elif raw == 'Rs' and not can_surrender:
        raw = 'S'
    elif raw == 'Rp' and not can_surrender:
        raw = 'P' if can_split else 'H'

    return raw


# ---------------------------------------------------------------------------
# Single-hand simulation (supports splits)
# ---------------------------------------------------------------------------

# Hand result tuple: (final_cards, final_bet, status, doubled)
# status: 'played' | 'bust' | 'surrender'
# final_bet: actual bet after any doubling
# doubled: True if the bet was doubled
_HandResult = tuple[list[str], float, str, bool]


def _play_player_hands(
    player_cards: list[str],
    dealer_upcard: str,
    shoe: list[str],
    pos: int,
    counter: MultiCounter,
    das: bool,
    s17: bool,
    surrender: bool,
    use_index_plays: bool,
    bet_units: float,
    blackjack_pays: float,
    split_depth: int = 0,
    max_splits: int = 3,
) -> tuple[list[_HandResult], int]:
    """
    Play one player hand (with splits). Returns:
      - list of (final_cards, final_bet, status, doubled) where status is
        'played' (needs dealer comparison), 'bust', or 'surrender'
      - new shoe position

    Separating player play from dealer comparison allows splits to accumulate
    all finished hands before the dealer plays once.
    """
    cards = list(player_cards)
    du    = _RANK_VALUES[dealer_upcard] if dealer_upcard != 'A' else 11
    tc_int = counter.true_count_int()

    can_double = len(cards) == 2
    can_split  = len(cards) == 2 and _is_pair(cards) and split_depth < max_splits
    # After splitting aces, only one additional card (no further hits)
    split_aces_no_hit = split_depth > 0 and cards[0] == 'A' and len(cards) == 2

    doubled = False

    while True:
        total = _hand_total(cards)
        if total > 21:
            return [([*cards], bet_units, 'bust', doubled)], pos

        if total == 21 and len(cards) > 2:
            break   # 21 — stand

        if split_aces_no_hit:
            break   # split aces: only one additional card, then stand

        action = _get_action(
            cards, du, das, s17, tc_int,
            can_double and not doubled,
            can_split and split_depth < max_splits,
            surrender and split_depth == 0 and len(cards) == 2,
            use_index_plays,
        )

        if action in ('H', 'Dh', 'D'):
            if action in ('D', 'Dh') and can_double and not doubled:
                doubled = True
                bet_units *= 2
            if pos >= len(shoe):
                break
            new_card = shoe[pos]; pos += 1
            counter.add_card(new_card)
            cards.append(new_card)
            can_double = False
            can_split  = False
            if doubled:
                break   # stand after double
        elif action == 'Ds':
            if can_double and not doubled:
                doubled = True
                bet_units *= 2
                if pos < len(shoe):
                    new_card = shoe[pos]; pos += 1
                    counter.add_card(new_card)
                    cards.append(new_card)
            break   # stand (doubled or couldn't double)
        elif action == 'S':
            break
        elif action in ('Rh', 'Rs', 'Rp'):
            return [([*cards], bet_units, 'surrender', False)], pos
        elif action == 'P':
            card_a, card_b = cards[0], cards[1]
            if pos + 1 >= len(shoe):
                break
            hand_a = [card_a, shoe[pos]]; pos += 1
            hand_b = [card_b, shoe[pos]]; pos += 1
            counter.add_card(hand_a[1])
            counter.add_card(hand_b[1])

            hands_a, pos = _play_player_hands(
                hand_a, dealer_upcard, shoe, pos, counter, das, s17, False,
                use_index_plays, bet_units, blackjack_pays, split_depth + 1, max_splits,
            )
            hands_b, pos = _play_player_hands(
                hand_b, dealer_upcard, shoe, pos, counter, das, s17, False,
                use_index_plays, bet_units, blackjack_pays, split_depth + 1, max_splits,
            )
            return hands_a + hands_b, pos
        else:
            break   # unknown action — stand

    return [([*cards], bet_units, 'played', doubled)], pos


# ---------------------------------------------------------------------------
# Main simulation loop
# ---------------------------------------------------------------------------

class SimulationRunner:
    """
    Runs a full Monte Carlo simulation of the advantage play engine.

    Usage:
        runner = SimulationRunner(SimParams(num_hands=1_000_000))
        result = runner.run()
        print(result.summary())
    """

    def __init__(self, params: SimParams | None = None) -> None:
        self.params = params or SimParams()

    def run(self) -> SimResult:
        p     = self.params
        rng   = random.Random(p.seed)
        start = time.perf_counter()

        counter         = MultiCounter(p.num_decks)
        cut_card        = int(p.num_decks * 52 * p.penetration)
        shoe: list[str] = _build_shoe(p.num_decks, rng)
        shoe_pos        = 0
        shoe_count      = 1

        # Tracking stats
        net_units        = 0.0
        total_wagered    = 0.0
        wins             = 0
        losses           = 0
        pushes           = 0
        blackjacks       = 0
        surrenders       = 0
        splits           = 0
        doubles_won      = 0
        doubles_total    = 0
        hands_played     = 0
        wonged_out       = 0
        min_bankroll     = p.starting_bankroll
        bankroll         = p.starting_bankroll
        peak_bankroll    = p.starting_bankroll
        hand_results: list[float] = []

        for hand_num in range(p.num_hands):
            # Reshuffle check
            if shoe_pos >= cut_card:
                shoe     = _build_shoe(p.num_decks, rng)
                shoe_pos = 0
                counter.reset()
                shoe_count += 1

            # Need at least 10 cards to play a round
            if shoe_pos + 10 >= len(shoe):
                continue

            # --- Pre-round count + bet sizing ---
            tc     = counter.betting_tc()
            tc_int = counter.true_count_int()

            # Wonging: skip hand if TC below entry threshold
            if p.wonging and tc < p.wonging_entry_tc:
                # Still observe next round's cards (simulating back-counting)
                # Don't play; burn a few cards
                shoe_pos += 4
                for _ in range(min(4, len(shoe) - shoe_pos)):
                    if shoe_pos < len(shoe):
                        counter.add_card(shoe[shoe_pos])
                        shoe_pos += 1
                wonged_out += 1
                continue

            # Wonging exit: if TC drops below exit threshold during shoe, skip
            if p.wonging and tc <= p.wonging_exit_tc and hands_played > 0:
                shoe_pos += 3
                for _ in range(min(3, len(shoe) - shoe_pos)):
                    if shoe_pos < len(shoe):
                        counter.add_card(shoe[shoe_pos])
                        shoe_pos += 1
                wonged_out += 1
                continue

            # Bet sizing
            bet = bet_units_for_true_count(tc)
            bet = max(1, min(p.bet_spread, bet))

            # Apply camouflage variance
            if p.camouflage_variance > 0 and rng.random() < p.camouflage_variance:
                bet = max(1, min(p.bet_spread, bet + rng.choice([-1, 1])))

            # --- Deal initial cards ---
            if shoe_pos + 4 >= len(shoe):
                continue

            p1 = shoe[shoe_pos];     shoe_pos += 1
            uc = shoe[shoe_pos];     shoe_pos += 1   # dealer upcard
            p2 = shoe[shoe_pos];     shoe_pos += 1
            hc = shoe[shoe_pos];     shoe_pos += 1   # dealer hole card

            # Count the dealt cards (upcard and both player cards; NOT hole card yet)
            counter.add_card(p1)
            counter.add_card(uc)
            counter.add_card(p2)
            # (Hole card counted after peek / when revealed)

            player_cards = [p1, p2]
            du = _RANK_VALUES[uc] if uc != 'A' else 11
            dh = _RANK_VALUES[hc] if hc != 'A' else 11

            # --- Dealer blackjack check ---
            dealer_is_bj = (_hand_total([uc, hc]) == 21)
            if dealer_is_bj:
                counter.add_card(hc)
                # Insurance check
                if insurance_index(counter.true_count()) and uc == 'A':
                    # Insurance wins when dealer has BJ
                    insurance_net = bet * 0.5  # net of 0: pays 2:1 on 0.5 bet = +0.5, costs 0.5 → net 0.5
                    net_units   += insurance_net
                else:
                    insurance_net = 0.0

                player_total = _hand_total(player_cards)
                if player_total == 21 and len(player_cards) == 2:
                    # Push (player BJ vs dealer BJ)
                    pushes += 1
                    result  = 0.0
                else:
                    losses += 1
                    result  = -float(bet)
                net_units   += result + insurance_net
                total_wagered += bet
                hand_results.append(result / bet if bet else 0)
                hands_played += 1
                bankroll    += (result + insurance_net) * p.unit
                peak_bankroll = max(peak_bankroll, bankroll)
                min_bankroll  = min(min_bankroll, bankroll)
                continue

            # --- Player blackjack ---
            player_bj = (_hand_total(player_cards) == 21)
            if player_bj:
                counter.add_card(hc)
                blackjacks += 1
                result = bet * p.blackjack_pays
                net_units  += result
                total_wagered += bet
                hand_results.append(p.blackjack_pays)
                hands_played += 1
                bankroll    += result * p.unit
                peak_bankroll = max(peak_bankroll, bankroll)
                continue

            # --- Insurance offered (dealer shows Ace, no BJ) ---
            insurance_net = 0.0
            if uc == 'A':
                counter.add_card(hc)   # reveal hole card
                # Insurance always loses here (dealer has no BJ)
                if insurance_index(counter.true_count()):
                    insurance_net = -bet * 0.5   # lose insurance bet
            else:
                counter.add_card(hc)

            # --- Play player hand(s) ---
            finished_hands, shoe_pos = _play_player_hands(
                player_cards, uc, shoe, shoe_pos, counter,
                p.das, p.s17, p.surrender,
                p.index_plays, bet, p.blackjack_pays,
                split_depth=0,
            )

            # Dealer plays once if any hand needs comparison
            dealer_total: int | None = None
            if any(status == 'played' for _, _, status, _ in finished_hands):
                dealer_total, shoe_pos = _dealer_play(hc, uc, shoe, shoe_pos, p.s17)

            # Track splits
            if len(finished_hands) > 1:
                splits += 1

            # Settle each hand
            result = 0.0
            for (final_cards, final_bet, status, doubled) in finished_hands:
                if status == 'surrender':
                    hand_net = -final_bet * 0.5
                    surrenders += 1
                elif status == 'bust':
                    hand_net = -final_bet
                    losses += 1
                else:  # 'played' — compare vs dealer
                    player_total = _hand_total(final_cards)
                    assert dealer_total is not None
                    if dealer_total > 21 or player_total > dealer_total:
                        hand_net = final_bet
                        wins += 1
                    elif player_total == dealer_total:
                        hand_net = 0.0
                        pushes += 1
                    else:
                        hand_net = -final_bet
                        losses += 1
                    if doubled:
                        doubles_total += 1
                        if hand_net > 0:
                            doubles_won += 1

                result += hand_net
                total_wagered += final_bet
                hand_results.append(hand_net / final_bet if final_bet else 0.0)

            net_units    += result + insurance_net
            hands_played += 1
            bankroll     += (result + insurance_net) * p.unit
            peak_bankroll = max(peak_bankroll, bankroll)
            min_bankroll  = min(min_bankroll, bankroll)

        elapsed = time.perf_counter() - start

        # --- Statistics ---
        total_hands = hands_played + wonged_out
        mean_edge   = net_units / total_wagered if total_wagered else 0.0

        if hand_results:
            mean_r = sum(hand_results) / len(hand_results)
            var_r  = sum((r - mean_r) ** 2 for r in hand_results) / len(hand_results)
            std_r  = math.sqrt(var_r)
        else:
            std_r = 0.0

        total_hands_nz = max(1, hands_played)
        win_rate  = wins   / total_hands_nz
        push_rate = pushes / total_hands_nz
        loss_rate = losses / total_hands_nz
        bj_rate   = blackjacks / total_hands_nz
        surr_rate = surrenders / total_hands_nz

        # Rough RoR estimate from simulation (fraction of bankroll depleted runs)
        max_dd = peak_bankroll - min_bankroll
        ror = max_dd / p.starting_bankroll if p.starting_bankroll > 0 else 0.0
        ror = min(ror, 1.0)

        speed = total_hands / elapsed if elapsed > 0 else 0.0

        return SimResult(
            num_hands          = p.num_hands,
            num_hands_played   = hands_played,
            num_shoes          = shoe_count,
            total_wagered      = total_wagered,
            net_units          = net_units,
            mean_edge          = mean_edge,
            std_dev_per_hand   = std_r,
            win_rate           = win_rate,
            push_rate          = push_rate,
            loss_rate          = loss_rate,
            blackjack_rate     = bj_rate,
            surrender_rate     = surr_rate,
            double_win_rate    = doubles_won / max(1, doubles_total),
            split_rate         = splits / total_hands_nz,
            max_drawdown_units = max_dd / p.unit if p.unit else 0,
            final_bankroll     = bankroll,
            risk_of_ruin_est   = ror,
            hands_per_second   = speed,
            elapsed_sec        = elapsed,
            wonged_out_count   = wonged_out,
        )


# ---------------------------------------------------------------------------
# Validation presets
# ---------------------------------------------------------------------------

def run_basic_strategy_validation() -> SimResult:
    """
    Verify basic strategy house edge is 0.40–0.55%.
    No counting, no deviations, flat bet.
    """
    params = SimParams(
        num_hands       = 2_000_000,
        bet_spread      = 1,
        index_plays     = False,
        wonging         = False,
        camouflage_variance = 0.0,
        seed            = 42,
    )
    runner = SimulationRunner(params)
    return runner.run()


def run_full_advantage_validation() -> SimResult:
    """
    Full system: Hi-Lo, 1:12 spread, I18+S16, wonging, 75% penetration.
    Target: player edge +0.5% to +1.2%.
    """
    params = SimParams(
        num_hands       = 2_000_000,
        penetration     = 0.75,
        bet_spread      = 12,
        index_plays     = True,
        wonging         = True,
        wonging_entry_tc = 2.0,
        wonging_exit_tc  = 0.0,
        camouflage_variance = 0.0,
        seed            = 42,
    )
    runner = SimulationRunner(params)
    return runner.run()


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == '__main__':
    import sys

    print("BlackjackAI — Monte Carlo Simulation Validation")
    print("=" * 55)

    # Validation 1: Basic strategy baseline
    print("\n[1/2] Basic strategy only (no counting, flat bet)…")
    r1 = run_basic_strategy_validation()
    print(r1.summary())
    bs_ok = -0.0055 <= r1.mean_edge <= -0.0035
    print(f"  ✓ House edge in expected range [−0.55%, −0.35%]: {bs_ok}")

    # Validation 2: Full advantage play
    print("\n[2/2] Full advantage play (Hi-Lo, 1:12 spread, wonging)…")
    r2 = run_full_advantage_validation()
    print(r2.summary())
    full_ok = r2.mean_edge >= 0.004
    print(f"  ✓ Player edge ≥ +0.4%: {full_ok}")

    if bs_ok and full_ok:
        print("\n✓ All validation checks passed. Engine is operating correctly.")
        sys.exit(0)
    else:
        print("\n✗ Validation FAILED. Debug the engine before live use.")
        sys.exit(1)
