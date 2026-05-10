import pytest

from frontend.server import run_bulk_strategy_simulation


def test_bulk_strategy_simulation_runs_requested_rounds():
    result = run_bulk_strategy_simulation({"hands": 50, "seed": 123, "unit_value": 5})

    assert result["rounds"] == 50
    assert result["requested_hands"] == 50
    assert result["hands_played"] >= 50
    assert result["net_money"] == result["net_units"] * 5
    assert result["total_wagered_units"] >= 50


def test_bulk_strategy_simulation_rejects_too_many_hands():
    with pytest.raises(ValueError, match="Hands must be between"):
        run_bulk_strategy_simulation({"hands": 1_000_001})
