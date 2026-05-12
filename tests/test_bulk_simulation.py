import pytest

from frontend.server import BulkStrategySimulation, TableRules, run_bulk_strategy_simulation


def test_bulk_strategy_simulation_runs_requested_rounds():
    result = run_bulk_strategy_simulation({"hands": 50, "seed": 123, "unit_value": 5})

    assert result["rounds"] == 50
    assert result["simulations"] == 1
    assert result["requested_hands"] == 50
    assert result["hands_played"] >= 50
    assert result["net_money"] == result["net_units"] * 5
    assert result["total_wagered_units"] >= 50
    assert "insurance_bets" in result
    assert "insurance_wins" in result


def test_bulk_strategy_simulation_runs_multiple_independent_simulations():
    result = run_bulk_strategy_simulation({"hands": 25, "simulations": 3, "seed": 500})

    assert result["simulations"] == 3
    assert result["rounds"] == 75
    assert result["total_requested_hands"] == 75
    assert len(result["runs"]) == 3
    assert [run["seed"] for run in result["runs"]] == [500, 501, 502]
    assert result["net_units"] == sum(run["net_units"] for run in result["runs"])


def test_bulk_strategy_simulation_rejects_too_many_hands():
    with pytest.raises(ValueError, match="Hands must be between"):
        run_bulk_strategy_simulation({"hands": 1_000_001})


def test_bulk_strategy_simulation_rejects_too_many_total_hands():
    with pytest.raises(ValueError, match="Total simulated hands"):
        run_bulk_strategy_simulation({"hands": 1_000_000, "simulations": 6})


def test_bulk_strategy_simulation_uses_fixed_75_percent_penetration():
    sim = BulkStrategySimulation(TableRules(num_decks=6), seed=123)

    assert sim.shuffle_at_cards_seen == 234
