from frontend.server import BlackjackSimulation, SimHand
from src.decision.hand import Card


def test_split_creates_two_playable_hands_and_advances_between_them():
    sim = BlackjackSimulation()
    sim.start({"starting_units": 100})
    sim.phase = "player"
    sim.hands = [SimHand([Card("8", "h"), Card("8", "s")], bet=1)]
    sim.dealer_cards = [Card("10", "h"), Card("Q", "s")]
    sim.dealer_revealed = False
    sim.active_hand_index = 0
    sim.shoe = [Card("3", "s"), Card("2", "s")]

    split_state = sim.player_action({"action": "SPLIT"})

    assert len(split_state["hands"]) == 2
    assert all(hand["from_split"] for hand in split_state["hands"])
    assert [hand["status"] for hand in split_state["hands"]] == ["active", "active"]
    assert split_state["active_hand_index"] == 0

    first_stand_state = sim.player_action({"action": "STAND"})

    assert first_stand_state["phase"] == "player"
    assert first_stand_state["active_hand_index"] == 1
    assert first_stand_state["hands"][0]["status"] == "stand"
    assert first_stand_state["hands"][1]["status"] == "active"

    final_state = sim.player_action({"action": "STAND"})

    assert final_state["phase"] == "round_over"
    assert len(final_state["hands"]) == 2
    assert all(hand["result"] is not None for hand in final_state["hands"])
