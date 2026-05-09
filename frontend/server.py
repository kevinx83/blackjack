"""Local web MVP for the blackjack advisor."""
from __future__ import annotations

import argparse
import json
import mimetypes
import sys
from dataclasses import dataclass
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
FRONTEND_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from src.decision.engine import BlackjackAdvisor  # noqa: E402
from src.decision.hand import Card, Hand, parse_card  # noqa: E402


RANKS = {"2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K", "A"}
SUITS = {"h", "d", "c", "s"}


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
            "recommendation": {
                "action": recommendation.action,
                "raw_code": recommendation.raw_code,
                "is_deviation": recommendation.is_deviation,
                "true_count": recommendation.true_count,
                "bet_units": recommendation.bet_units,
                "reasoning": recommendation.reasoning,
            },
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

    def state(self) -> dict:
        counter = self.advisor.counter
        return {
            "rules": {
                "num_decks": self.rules.num_decks,
                "das": self.rules.das,
                "s17": self.rules.s17,
                "surrender": self.rules.surrender,
            },
            "count": {
                "running_count": counter.running_count,
                "true_count": counter.true_count(),
                "true_count_int": counter.true_count_int(),
                "decks_remaining": counter.decks_remaining(),
                "cards_seen": counter.cards_seen,
                "aces_seen": counter.aces_seen,
                "deck_penetration": counter.deck_penetration,
                "ace_neutral_true_count": counter.ace_neutral_tc(),
            },
            "observed_cards": self.observed_cards[-40:],
        }


SESSION = GameSession()


class BlackjackRequestHandler(BaseHTTPRequestHandler):
    server_version = "BlackjackMVP/0.1"

    def do_GET(self) -> None:
        route = urlparse(self.path).path
        if route == "/api/state":
            self.send_json(SESSION.state())
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
