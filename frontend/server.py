"""Local web MVP for the blackjack advisor."""
from __future__ import annotations

import argparse
import json
import mimetypes
import random
import sys
from dataclasses import dataclass, field
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
FRONTEND_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from src.decision.engine import BlackjackAdvisor, bet_units_for_true_count  # noqa: E402
from src.decision.hand import Card, Hand, parse_card  # noqa: E402


RANKS = {"2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K", "A"}
SUITS = {"h", "d", "c", "s"}
RANK_ORDER = ["A", "2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K"]
SUIT_ORDER = ["h", "d", "c", "s"]
SUIT_SYMBOLS = {"h": "♥", "d": "♦", "c": "♣", "s": "♠"}


def normalize_rank(token: str) -> str:
    rank = token.strip().upper()
    if rank == "T":
        rank = "10"
    if rank not in RANKS:
        raise ValueError(f"Invalid rank: {token!r}")
    return rank


def parse_card_token(token: str) -> Card:
    token = token.strip()
    if not token:
        raise ValueError("Card token cannot be empty")
    if len(token) >= 2 and token[-1].lower() in SUITS:
        return parse_card(token)
    return Card(normalize_rank(token), "s")


def split_cards(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str):
        cleaned = value.replace(",", " ")
        return [part.strip() for part in cleaned.split() if part.strip()]
    raise ValueError("Cards must be a list or whitespace-separated string")


def card_label(card: Card) -> str:
    return card.rank


def card_payload(card: Card | None, hidden: bool = False) -> dict:
    if hidden or card is None:
        return {"label": "?", "rank": None, "suit": None, "hidden": True}
    return {
        "label": f"{card.rank}{SUIT_SYMBOLS[card.suit]}",
        "rank": card.rank,
        "suit": card.suit,
        "hidden": False,
    }


def recommendation_payload(recommendation) -> dict:
    return {
        "action": recommendation.action,
        "raw_code": recommendation.raw_code,
        "is_deviation": recommendation.is_deviation,
        "true_count": recommendation.true_count,
        "bet_units": recommendation.bet_units,
        "reasoning": recommendation.reasoning,
    }


def count_payload(counter) -> dict:
    return {
        "running_count": counter.running_count,
        "true_count": counter.true_count(),
        "true_count_int": counter.true_count_int(),
        "decks_remaining": counter.decks_remaining(),
        "cards_seen": counter.cards_seen,
        "aces_seen": counter.aces_seen,
        "deck_penetration": counter.deck_penetration,
        "ace_neutral_true_count": counter.ace_neutral_tc(),
    }


def betting_payload(counter) -> dict:
    true_count = counter.true_count()
    return {
        "recommended_units": bet_units_for_true_count(true_count),
        "true_count": true_count,
        "running_count": counter.running_count,
        "decks_remaining": counter.decks_remaining(),
    }


@dataclass
class TableRules:
    num_decks: int = 6
    das: bool = True
    s17: bool = True
    surrender: bool = True


class GameSession:
    def __init__(self) -> None:
        self.rules = TableRules()
        self.advisor = BlackjackAdvisor(
            num_decks=self.rules.num_decks,
            das=self.rules.das,
            s17=self.rules.s17,
            surrender=self.rules.surrender,
        )
        self.observed_cards: list[str] = []

    def start(self, payload: dict) -> dict:
        decks = int(payload.get("num_decks", self.rules.num_decks))
        if decks < 1 or decks > 8:
            raise ValueError("Number of decks must be between 1 and 8")

        self.rules = TableRules(
            num_decks=decks,
            das=bool(payload.get("das", True)),
            s17=bool(payload.get("s17", True)),
            surrender=bool(payload.get("surrender", True)),
        )
        self.advisor = BlackjackAdvisor(
            num_decks=self.rules.num_decks,
            das=self.rules.das,
            s17=self.rules.s17,
            surrender=self.rules.surrender,
        )
        self.observed_cards = []
        return self.state()

    def observe(self, raw_cards: list[str]) -> dict:
        cards = [parse_card_token(token) for token in raw_cards]
        self.advisor.observe(*cards)
        self.observed_cards.extend(card_label(card) for card in cards)
        return self.state()

    def recommend(self, payload: dict) -> dict:
        player_tokens = split_cards(payload.get("player"))
        dealer_tokens = split_cards(payload.get("dealer"))
        if not player_tokens:
            raise ValueError("Player hand is required")
        if len(dealer_tokens) != 1:
            raise ValueError("Exactly one dealer upcard is required")

        player_cards = [parse_card_token(token) for token in player_tokens]
        dealer_card = parse_card_token(dealer_tokens[0])
        hand = Hand(player_cards)
        can_double = bool(payload.get("can_double", len(player_cards) == 2))
        can_split = bool(payload.get("can_split", len(player_cards) == 2))
        recommendation = self.advisor.recommend(
            hand,
            dealer_card,
            can_double=can_double,
            can_split=can_split,
        )

        return {
            "recommendation": recommendation_payload(recommendation),
            "hand": {
                "cards": [card_label(card) for card in player_cards],
                "total": hand.total,
                "is_soft": hand.is_soft,
                "is_pair": hand.is_pair,
                "is_blackjack": hand.is_blackjack,
                "is_bust": hand.is_bust,
            },
            "dealer": card_label(dealer_card),
            "state": self.state(),
        }

    def count_and_recommend(self, payload: dict) -> dict:
        pre_round_betting = betting_payload(self.advisor.counter)
        player_tokens = split_cards(payload.get("player"))
        dealer_tokens = split_cards(payload.get("dealer"))
        if not player_tokens:
            raise ValueError("Player hand is required")
        if len(dealer_tokens) != 1:
            raise ValueError("Exactly one dealer upcard is required")

        self.observe([dealer_tokens[0], *player_tokens])
        result = self.recommend(payload)
        result["pre_round_betting"] = pre_round_betting
        return result

    def state(self) -> dict:
        counter = self.advisor.counter
        return {
            "rules": {
                "num_decks": self.rules.num_decks,
                "das": self.rules.das,
                "s17": self.rules.s17,
                "surrender": self.rules.surrender,
            },
            "count": count_payload(counter),
            "betting": betting_payload(counter),
            "observed_cards": self.observed_cards[-40:],
        }


SESSION = GameSession()


@dataclass
class SimHand:
    cards: list[Card]
    bet: float = 1.0
    status: str = "active"
    result: str | None = None
    payout: float = 0.0
    from_split: bool = False

    def as_hand(self) -> Hand:
        return Hand(list(self.cards))


@dataclass
class SimStats:
    rounds: int = 0
    hands: int = 0
    wins: int = 0
    losses: int = 0
    pushes: int = 0
    blackjacks: int = 0
    surrendered: int = 0
    bankroll: float = 0.0


class BlackjackSimulation:
    def __init__(self) -> None:
        self.rules = TableRules()
        self.advisor = BlackjackAdvisor()
        self.shoe: list[Card] = []
        self.hands: list[SimHand] = []
        self.dealer_cards: list[Card] = []
        self.dealer_revealed = False
        self.active_hand_index = 0
        self.phase = "idle"
        self.message = "Start a game to deal the first round."
        self.observed_cards: list[str] = []
        self.stats = SimStats()
        self.round_betting: dict | None = None
        self.shuffle_shoe()

    def start(self, payload: dict) -> dict:
        decks = int(payload.get("num_decks", self.rules.num_decks))
        if decks < 1 or decks > 8:
            raise ValueError("Number of decks must be between 1 and 8")

        self.rules = TableRules(
            num_decks=decks,
            das=bool(payload.get("das", True)),
            s17=bool(payload.get("s17", True)),
            surrender=bool(payload.get("surrender", True)),
        )
        self.advisor = BlackjackAdvisor(
            num_decks=self.rules.num_decks,
            das=self.rules.das,
            s17=self.rules.s17,
            surrender=self.rules.surrender,
        )
        self.stats = SimStats()
        self.observed_cards = []
        self.hands = []
        self.dealer_cards = []
        self.dealer_revealed = False
        self.phase = "idle"
        self.message = "New simulated shoe started."
        self.round_betting = None
        self.shuffle_shoe()
        return self.state()

    def shuffle_shoe(self) -> None:
        self.shoe = [
            Card(rank, suit)
            for _ in range(self.rules.num_decks)
            for suit in SUIT_ORDER
            for rank in RANK_ORDER
        ]
        random.shuffle(self.shoe)

    def new_round(self) -> dict:
        if len(self.shoe) < 16:
            self.shuffle_shoe()
            self.advisor.new_shoe()
            self.observed_cards = []
            self.message = "Shoe was low and has been reshuffled."

        self.hands = []
        self.dealer_cards = []
        self.dealer_revealed = False
        self.active_hand_index = 0
        self.phase = "player"
        self.stats.rounds += 1
        self.round_betting = betting_payload(self.advisor.counter)
        round_units = self.round_betting["recommended_units"]

        player_cards = [self.draw_visible(), self.draw_visible()]
        dealer_upcard = self.draw_visible()
        dealer_hole = self.draw_hidden()
        self.hands = [SimHand(player_cards, bet=round_units)]
        self.dealer_cards = [dealer_upcard, dealer_hole]

        player_hand = self.hands[0].as_hand()
        dealer_hand = Hand(self.dealer_cards)
        dealer_has_blackjack = dealer_hand.is_blackjack
        player_has_blackjack = player_hand.is_blackjack

        if dealer_has_blackjack or player_has_blackjack:
            self.reveal_dealer()
            if dealer_has_blackjack and player_has_blackjack:
                self.finish_hand(self.hands[0], "push", 0.0)
                self.message = "Both player and dealer have blackjack."
            elif player_has_blackjack:
                self.finish_hand(self.hands[0], "blackjack", 1.5)
                self.stats.blackjacks += 1
                self.message = "Player blackjack pays 3:2."
            else:
                self.finish_hand(self.hands[0], "loss", -self.hands[0].bet)
                self.message = "Dealer has blackjack."
            self.phase = "round_over"
        else:
            self.message = "Player turn."

        return self.state()

    def player_action(self, payload: dict) -> dict:
        action = str(payload.get("action", "")).upper()
        if self.phase != "player":
            raise ValueError("No active player decision")
        if not self.hands:
            raise ValueError("Deal a round first")

        hand = self.hands[self.active_hand_index]
        if hand.status != "active":
            raise ValueError("Selected hand is not active")

        if action == "HIT":
            hand.cards.append(self.draw_visible())
            current = hand.as_hand()
            if current.is_bust:
                hand.status = "bust"
                self.message = "Player hand busted."
                self.advance_turn()
            elif current.total == 21:
                hand.status = "stand"
                self.message = "Player reached 21."
                self.advance_turn()
            else:
                self.message = "Player hit."
        elif action == "STAND":
            hand.status = "stand"
            self.message = "Player stands."
            self.advance_turn()
        elif action == "DOUBLE":
            if not self.can_double(hand):
                raise ValueError("Double is only available on legal two-card hands")
            hand.bet *= 2
            hand.cards.append(self.draw_visible())
            hand.status = "bust" if hand.as_hand().is_bust else "stand"
            self.message = "Player doubled."
            self.advance_turn()
        elif action == "SURRENDER":
            if not self.can_surrender(hand):
                raise ValueError("Surrender is only available on the first two cards")
            hand.status = "surrender"
            self.finish_hand(hand, "surrender", -hand.bet / 2)
            self.stats.surrendered += 1
            self.message = "Player surrendered."
            self.advance_turn()
        elif action == "SPLIT":
            if not self.can_split(hand):
                raise ValueError("Split is only available for a legal pair")
            first_card, second_card = hand.cards
            split_aces = first_card.rank == "A" and second_card.rank == "A"
            self.hands[self.active_hand_index] = SimHand(
                [first_card, self.draw_visible()],
                bet=hand.bet,
                from_split=True,
                status="stand" if split_aces else "active",
            )
            self.hands.insert(
                self.active_hand_index + 1,
                SimHand(
                    [second_card, self.draw_visible()],
                    bet=hand.bet,
                    from_split=True,
                    status="stand" if split_aces else "active",
                ),
            )
            self.message = "Split aces receive one card each." if split_aces else "Hand split."
            if split_aces:
                self.advance_turn()
        else:
            raise ValueError("Unknown action")

        return self.state()

    def draw_visible(self) -> Card:
        card = self.draw_hidden()
        self.observe(card)
        return card

    def draw_hidden(self) -> Card:
        if not self.shoe:
            raise ValueError("The simulated shoe is empty")
        return self.shoe.pop()

    def observe(self, card: Card) -> None:
        self.advisor.observe(card)
        self.observed_cards.append(card_label(card))

    def reveal_dealer(self) -> None:
        if self.dealer_revealed:
            return
        if len(self.dealer_cards) > 1:
            self.observe(self.dealer_cards[1])
        self.dealer_revealed = True

    def can_double(self, hand: SimHand) -> bool:
        return hand.status == "active" and len(hand.cards) == 2 and (not hand.from_split or self.rules.das)

    def can_split(self, hand: SimHand) -> bool:
        return hand.status == "active" and len(hand.cards) == 2 and hand.as_hand().is_pair and not hand.from_split

    def can_surrender(self, hand: SimHand) -> bool:
        return self.rules.surrender and hand.status == "active" and len(hand.cards) == 2 and not hand.from_split

    def advance_turn(self) -> None:
        for index in range(self.active_hand_index, len(self.hands)):
            if self.hands[index].status == "active":
                self.active_hand_index = index
                return

        playable = [
            hand
            for hand in self.hands
            if hand.status in {"stand", "active"} and not hand.as_hand().is_bust
        ]
        if playable:
            self.play_dealer()
        else:
            for hand in self.hands:
                if hand.status == "bust":
                    self.finish_hand(hand, "loss", -hand.bet)
            self.phase = "round_over"
            self.message = "Round over."

    def play_dealer(self) -> None:
        self.reveal_dealer()
        while self.dealer_should_hit():
            self.dealer_cards.append(self.draw_visible())
        self.settle_round()

    def dealer_should_hit(self) -> bool:
        dealer = Hand(self.dealer_cards)
        return dealer.total < 17 or (dealer.total == 17 and dealer.is_soft and not self.rules.s17)

    def settle_round(self) -> None:
        dealer = Hand(self.dealer_cards)
        dealer_bust = dealer.is_bust
        dealer_total = dealer.total

        for hand in self.hands:
            player = hand.as_hand()
            if hand.result is not None:
                continue
            if player.is_bust:
                self.finish_hand(hand, "loss", -hand.bet)
            elif dealer_bust:
                self.finish_hand(hand, "win", hand.bet)
            elif player.total > dealer_total:
                self.finish_hand(hand, "win", hand.bet)
            elif player.total < dealer_total:
                self.finish_hand(hand, "loss", -hand.bet)
            else:
                self.finish_hand(hand, "push", 0.0)

        self.phase = "round_over"
        self.message = "Round over."

    def finish_hand(self, hand: SimHand, result: str, payout: float) -> None:
        hand.status = "done"
        hand.result = result
        hand.payout = payout
        self.stats.hands += 1
        self.stats.bankroll += payout
        if result in {"win", "blackjack"}:
            self.stats.wins += 1
        elif result == "loss":
            self.stats.losses += 1
        elif result == "push":
            self.stats.pushes += 1
        elif result == "surrender":
            self.stats.losses += 1

    def active_recommendation(self) -> dict | None:
        if self.phase != "player" or not self.hands:
            return None
        hand = self.hands[self.active_hand_index]
        if hand.status != "active":
            return None

        original_surrender = self.advisor.surrender
        self.advisor.surrender = self.can_surrender(hand)
        try:
            recommendation = self.advisor.recommend(
                hand.as_hand(),
                self.dealer_cards[0],
                can_double=self.can_double(hand),
                can_split=self.can_split(hand),
            )
        finally:
            self.advisor.surrender = original_surrender

        return recommendation_payload(recommendation)

    def hand_payload(self, hand: SimHand, index: int) -> dict:
        computed = hand.as_hand()
        return {
            "index": index,
            "cards": [card_payload(card) for card in hand.cards],
            "total": computed.total,
            "is_soft": computed.is_soft,
            "is_pair": computed.is_pair,
            "is_blackjack": computed.is_blackjack and not hand.from_split,
            "is_bust": computed.is_bust,
            "bet": hand.bet,
            "status": hand.status,
            "result": hand.result,
            "payout": hand.payout,
            "active": self.phase == "player" and index == self.active_hand_index and hand.status == "active",
        }

    def state(self) -> dict:
        counter = self.advisor.counter
        dealer_hand = Hand(self.dealer_cards) if self.dealer_cards else Hand([])
        dealer_cards = []
        if self.dealer_cards:
            dealer_cards.append(card_payload(self.dealer_cards[0]))
            if len(self.dealer_cards) > 1:
                dealer_cards.append(card_payload(self.dealer_cards[1], hidden=not self.dealer_revealed))
            dealer_cards.extend(card_payload(card) for card in self.dealer_cards[2:])

        return {
            "rules": {
                "num_decks": self.rules.num_decks,
                "das": self.rules.das,
                "s17": self.rules.s17,
                "surrender": self.rules.surrender,
            },
            "phase": self.phase,
            "message": self.message,
            "shoe_cards_remaining": len(self.shoe),
            "dealer": {
                "cards": dealer_cards,
                "revealed": self.dealer_revealed,
                "total": dealer_hand.total if self.dealer_revealed else None,
                "is_soft": dealer_hand.is_soft if self.dealer_revealed else False,
                "is_bust": dealer_hand.is_bust if self.dealer_revealed else False,
            },
            "hands": [self.hand_payload(hand, index) for index, hand in enumerate(self.hands)],
            "active_hand_index": self.active_hand_index,
            "recommendation": self.active_recommendation(),
            "legal_actions": self.legal_actions(),
            "count": count_payload(counter),
            "betting": {
                "next_hand": betting_payload(counter),
                "round": self.round_betting,
            },
            "stats": {
                "rounds": self.stats.rounds,
                "hands": self.stats.hands,
                "wins": self.stats.wins,
                "losses": self.stats.losses,
                "pushes": self.stats.pushes,
                "blackjacks": self.stats.blackjacks,
                "surrendered": self.stats.surrendered,
                "bankroll": self.stats.bankroll,
            },
            "observed_cards": self.observed_cards[-40:],
        }

    def legal_actions(self) -> list[str]:
        if self.phase != "player" or not self.hands:
            return []
        hand = self.hands[self.active_hand_index]
        if hand.status != "active":
            return []
        actions = ["HIT", "STAND"]
        if self.can_double(hand):
            actions.append("DOUBLE")
        if self.can_split(hand):
            actions.append("SPLIT")
        if self.can_surrender(hand):
            actions.append("SURRENDER")
        return actions


SIMULATION = BlackjackSimulation()


class BlackjackRequestHandler(BaseHTTPRequestHandler):
    server_version = "BlackjackMVP/0.1"

    def do_GET(self) -> None:
        route = urlparse(self.path).path
        if route == "/api/state":
            self.send_json(SESSION.state())
            return
        if route == "/api/sim/state":
            self.send_json(SIMULATION.state())
            return
        self.serve_static(route)

    def do_POST(self) -> None:
        route = urlparse(self.path).path
        try:
            payload = self.read_json()
            if route == "/api/start":
                self.send_json(SESSION.start(payload))
            elif route == "/api/observe":
                self.send_json(SESSION.observe(split_cards(payload.get("cards"))))
            elif route == "/api/recommend":
                self.send_json(SESSION.recommend(payload))
            elif route == "/api/count-recommend":
                self.send_json(SESSION.count_and_recommend(payload))
            elif route == "/api/sim/start":
                self.send_json(SIMULATION.start(payload))
            elif route == "/api/sim/new-round":
                self.send_json(SIMULATION.new_round())
            elif route == "/api/sim/action":
                self.send_json(SIMULATION.player_action(payload))
            else:
                self.send_error(HTTPStatus.NOT_FOUND, "Unknown API route")
        except ValueError as exc:
            self.send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
        except json.JSONDecodeError:
            self.send_json({"error": "Invalid JSON body"}, HTTPStatus.BAD_REQUEST)

    def read_json(self) -> dict:
        length = int(self.headers.get("Content-Length", "0"))
        if length == 0:
            return {}
        body = self.rfile.read(length)
        parsed = json.loads(body.decode("utf-8"))
        if not isinstance(parsed, dict):
            raise ValueError("JSON body must be an object")
        return parsed

    def send_json(self, payload: dict, status: HTTPStatus = HTTPStatus.OK) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def serve_static(self, route: str) -> None:
        rel = "index.html" if route in ("", "/") else route.lstrip("/")
        target = (FRONTEND_DIR / rel).resolve()
        if target.is_dir():
            target = (target / "index.html").resolve()
        if FRONTEND_DIR not in target.parents and target != FRONTEND_DIR:
            self.send_error(HTTPStatus.FORBIDDEN)
            return
        if not target.exists() or not target.is_file():
            self.send_error(HTTPStatus.NOT_FOUND)
            return

        body = target.read_bytes()
        content_type = mimetypes.guess_type(str(target))[0] or "application/octet-stream"
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt: str, *args: object) -> None:
        return


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the blackjack web MVP")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()

    server = ThreadingHTTPServer((args.host, args.port), BlackjackRequestHandler)
    print(f"Blackjack web MVP running at http://{args.host}:{args.port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nServer stopped")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
