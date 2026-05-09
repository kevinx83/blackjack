# Blackjack Advisor

Educational blackjack strategy and Hi-Lo counting simulator.

## CLI

```bash
python3 main.py
```

## Web MVP

```bash
python3 frontend/server.py
```

Then open `http://127.0.0.1:8000`.

The web MVP serves a small React UI and uses the existing Python decision engine through local API endpoints.

The home screen has two modes:

- Simulation: deal from a shuffled shoe and play hands while watching the count, stats, and live recommendation.
- Solver: manually enter dealer/player cards and extra observed cards.
