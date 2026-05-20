## CLI

```bash
python3 main.py
```

## Webcam CV + Counting

Uses the bundled model at `detect/weights/best.pt` by default, reads from the
webcam, identifies visible cards, and feeds newly confirmed cards into the
running card counter/advisor.

```bash
python3 -m src.vision.pipeline --camera 0
```

Controls:

- `r`: reset the visible round, keeping the shoe count
- `n`: start a new shoe, resetting the count
- `q`: quit

## Web MVP

```bash
python3 frontend/server.py
```
