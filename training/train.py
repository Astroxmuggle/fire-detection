"""Train the fire/smoke detector.

The dataset is not shipped with the repository (it is ~400 MB). Point ``--data``
at a YOLO ``data.yaml``; the Roboflow export used for the shipped checkpoint is
documented in the README.

Example
-------
    python training/train.py --data "C:\\Users\\manna_2c83x\\fire-detection-ai\\dataset-raw\\data.yaml"

On CPU this takes tens of hours for 50 epochs; a GPU is strongly recommended.
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Train the FireWatch AI detector")
    parser.add_argument("--data", required=True, help="Path to the dataset data.yaml")
    parser.add_argument("--base-model", default="yolo11n.pt", help="Starting weights")
    parser.add_argument("--epochs", type=int, default=50)
    parser.add_argument("--imgsz", type=int, default=640)
    parser.add_argument("--batch", type=int, default=16)
    parser.add_argument("--device", default="", help="'' = auto, 'cpu', '0' = first GPU")
    parser.add_argument("--project", default=str(PROJECT_ROOT / "runs" / "detect"))
    parser.add_argument("--name", default="fire_smoke_detector")
    parser.add_argument(
        "--copy-to-models",
        action="store_true",
        help="Copy the best checkpoint to models/best.pt when training finishes",
    )
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)

    data_path = Path(args.data).expanduser()
    if not data_path.is_file():
        print(f"error: data.yaml not found at {data_path}", file=sys.stderr)
        return 2

    from ultralytics import YOLO

    print(f"Training {args.base_model} on {data_path}")
    model = YOLO(args.base_model)
    results = model.train(
        data=str(data_path),
        epochs=args.epochs,
        imgsz=args.imgsz,
        batch=args.batch,
        device=args.device,
        project=args.project,
        name=args.name,
        exist_ok=True,
    )

    save_dir = Path(getattr(results, "save_dir", Path(args.project) / args.name))
    best = save_dir / "weights" / "best.pt"
    print(f"Training finished. Best checkpoint: {best}")

    if args.copy_to_models and best.is_file():
        destination = PROJECT_ROOT / "models" / "best.pt"
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(best, destination)
        print(f"Copied checkpoint to {destination}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
