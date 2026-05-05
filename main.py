"""
BlackjackAI — interactive terminal advisor.

Usage:
    python main.py

Card notation: rank + suit, e.g. As (Ace of spades), Kh, 10d, 7c
"""
from __future__ import annotations
import sys

try:
    from src.decision.hand import Hand, parse_card
    from src.decision.engine import BlackjackAdvisor
except ImportError:
    print("Run from the project root: python main.py")
    sys.exit(1)

_COLORS = {
    'HIT':       '\033[92m',   # green
    'STAND':     '\033[91m',   # red
    'DOUBLE':    '\033[93m',   # yellow
    'SPLIT':     '\033[94m',   # blue
    'SURRENDER': '\033[95m',   # magenta
    'INSURANCE': '\033[96m',   # cyan
    'RESET':     '\033[0m',
}


def colorize(action: str) -> str:
    color = _COLORS.get(action, '')
    reset = _COLORS['RESET']
    return f"{color}{action}{reset}"


def parse_hand(prompt: str) -> Hand:
    while True:
        raw = input(prompt).strip()
        if not raw:
            continue
        try:
            cards = [parse_card(t) for t in raw.split()]
            return Hand(cards)
        except ValueError as e:
            print(f"  Error: {e}. Try again.")


def main() -> None:
    print("\n=== BlackjackAI Advisor ===")
    print("Card format: rank+suit  (e.g. As Kh 10d 7c)\n")

    num_decks = int(input("Number of decks [6]: ").strip() or "6")
    adv = BlackjackAdvisor(num_decks=num_decks)

    print(f"\nShoe: {num_decks} deck(s). Type 'new' to start a new shoe, 'quit' to exit.\n")

    while True:
        print("─" * 50)

        raw_dealer = input("Dealer upcard (e.g. Ah): ").strip()
        if raw_dealer.lower() == 'quit':
            break
        if raw_dealer.lower() == 'new':
            adv.new_shoe()
            print("New shoe started. Running count reset.\n")
            continue
        try:
            dealer_card = parse_card(raw_dealer)
        except ValueError as e:
            print(f"  Error: {e}")
            continue

        player_hand = parse_hand("Your hand (e.g. 9h 7s): ")

        # Observe all visible cards
        adv.observe(dealer_card, *player_hand.cards)

        rec = adv.recommend(player_hand, dealer_card)

        print(f"\n  Action : {colorize(rec.action)}")
        print(f"  Bet    : {rec.bet_units} unit(s)")
        print(f"  TC     : {rec.true_count:+.1f}")
        print(f"  {'[DEVIATION]' if rec.is_deviation else '[Basic strategy]'}")
        print(f"  {rec.reasoning}\n")

        # Option to record additional cards dealt this round
        extra = input("Other cards dealt this round (leave blank to skip): ").strip()
        if extra:
            try:
                for tok in extra.split():
                    adv.observe(parse_card(tok))
            except ValueError as e:
                print(f"  Warning: {e}")


if __name__ == '__main__':
    main()
