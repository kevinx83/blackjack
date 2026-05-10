"""
Train YOLOv8n on the playing cards dataset.

Usage:
    python train.py
    python train.py --epochs 50 --batch 8

Weights are saved to runs/train/cards/weights/best.pt
"""
from __future__ import annotations
import argparse
from ultralytics import YOLO


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--epochs', type=int, default=100)
    parser.add_argument('--batch', type=int, default=16)
    parser.add_argument('--imgsz', type=int, default=640)
    args = parser.parse_args()

    model = YOLO('yolov8n.pt')
    model.train(
        data='data/cards/data.yaml',
        epochs=args.epochs,
        batch=args.batch,
        imgsz=args.imgsz,
        project='runs/train',
        name='cards',
        exist_ok=True,
    )
    print("\nTraining complete. Weights saved to: runs/train/cards/weights/best.pt")


if __name__ == '__main__':
    main()
