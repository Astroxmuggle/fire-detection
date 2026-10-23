"""Reproducible evaluation harness.

Three measurements, all written to ``evaluation/reports/``:

1. **Labelled metrics** — precision / recall / mAP@50 / mAP@50-95 on a labelled
   split via the Ultralytics validator.
2. **False-positive scan** — every image of a negative set (no fire, no smoke) is
   run through the model, once raw and once through the application's detection
   manager, at several thresholds.
3. **Negative video sequences** — sampled frames are pushed sequentially through
   the confirmation engine, which is the only way to measure whether a false
   positive survives temporal confirmation.

Usage
-----
    python evaluation/run_eval.py --data "C:\\Users\\manna_2c83x\\fire-detection-ai\\dataset-raw\\data.yaml" \
                                  --negatives "C:\\Users\\manna_2c83x\\fire-detection-ai\\evaluation"
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import cv2
import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

DEFAULT_MODEL = PROJECT_ROOT / "models" / "best.pt"
DEFAULT_OUT = PROJECT_ROOT / "evaluation" / "reports"


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="FireWatch AI evaluation harness")
    parser.add_argument("--model", default=str(DEFAULT_MODEL))
    parser.add_argument("--data", default=None, help="Labelled data.yaml (enables mAP validation)")
    parser.add_argument("--split", default="test")
    parser.add_argument("--negatives", default=None, help="Folder containing negative sets")
    parser.add_argument("--thresholds", default="0.50,0.40,0.30")
    parser.add_argument("--video-fps", type=float, default=1.0, help="Frames sampled per second")
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    parser.add_argument("--max-images", type=int, default=0, help="Limit the negative scan (0 = all)")
    parser.add_argument("--skip-video", action="store_true")
    return parser.parse_args(argv)


# --------------------------------------------------------------------- helpers
def load_model(model_path: Path):
    from ultralytics import YOLO

    if not model_path.is_file():
        raise SystemExit(f"error: model not found at {model_path}")
    return YOLO(str(model_path))


def extract_detections(result):
    boxes = result.boxes
    if boxes is None:
        return []
    names = getattr(result, "names", {}) or {}
    detections = []
    for box in boxes:
        detections.append({
            "class_name": str(names.get(int(box.cls[0]), int(box.cls[0]))).lower(),
            "confidence": float(box.conf[0]),
            "bbox": box.xyxy[0].tolist(),
        })
    return detections


def make_manager(threshold: float):
    from detection.manager import DetectionManager

    return DetectionManager(
        confidence_threshold=threshold,
        class_thresholds={"fire": threshold, "smoke": threshold},
        required_frames=1,
        release_frames=1,
        cooldown_seconds=0,
    )


# ----------------------------------------------------------------- validation
def resolve_data_yaml(data_path: Path, out_dir: Path) -> Path:
    """Rewrite a data.yaml with absolute paths so the validator can find the images.

    Ultralytics resolves a relative ``path`` against the working directory, which
    breaks when the dataset lives somewhere else. The resolved copy is written to
    the report folder and used for validation.
    """
    import yaml

    spec = yaml.safe_load(data_path.read_text(encoding="utf-8")) or {}
    base = data_path.parent.resolve()

    dataset_root = spec.get("path")
    if dataset_root:
        candidate = Path(dataset_root)
        if not candidate.is_absolute():
            candidate = (base / candidate).resolve()
    else:
        candidate = base
    spec["path"] = str(candidate)

    resolved = out_dir / "_resolved_data.yaml"
    resolved.write_text(yaml.safe_dump(spec, sort_keys=False), encoding="utf-8")
    return resolved


def run_validation(model, data_path: Path, split: str, out_dir: Path) -> dict:
    print(f"[1/3] validating on {data_path} (split={split})", flush=True)
    started = time.perf_counter()
    resolved_data = resolve_data_yaml(data_path, out_dir)
    metrics = model.val(
        data=str(resolved_data),
        split=split,
        imgsz=640,
        # Absolute: Ultralytics otherwise resolves a relative project against its
        # global runs directory, which may not be writable.
        project=str((out_dir / "runs").resolve()),
        name="validation",
        exist_ok=True,
        plots=True,
        # workers=0: the validator's multiprocessing loader needs named pipes,
        # which restricted/sandboxed environments deny. Single-process is fine.
        workers=0,
        verbose=False,
    )
    box = metrics.box
    report = {
        "split": split,
        "precision": round(float(box.mp), 4),
        "recall": round(float(box.mr), 4),
        "map50": round(float(box.map50), 4),
        "map50_95": round(float(box.map), 4),
        "elapsed_seconds": round(time.perf_counter() - started, 1),
    }

    try:
        names = getattr(metrics, "names", {}) or {}
        per_class = {}
        class_indices = list(getattr(box, "ap_class_index", []))
        for position, class_index in enumerate(class_indices):
            per_class[str(names.get(int(class_index), int(class_index)))] = {
                "precision": round(float(box.p[position]), 4),
                "recall": round(float(box.r[position]), 4),
                "map50": round(float(box.ap50[position]), 4),
                "map50_95": round(float(box.ap[position]), 4),
            }
        if per_class:
            report["per_class"] = per_class
    except Exception as exc:  # noqa: BLE001 - optional detail
        report["per_class_error"] = f"{type(exc).__name__}: {exc}"

    print(f"      mAP50={report['map50']:.4f}  P={report['precision']:.4f}  R={report['recall']:.4f}", flush=True)
    return report


# --------------------------------------------------------------- negative scan
def run_negative_scan(model, negatives_root: Path, thresholds, max_images: int) -> dict:
    image_dir = negatives_root / "negative-dfire" / "images"
    images = sorted(image_dir.glob("*.jpg")) + sorted(image_dir.glob("*.png"))
    if max_images:
        images = images[:max_images]

    print(f"[2/3] scanning {len(images)} negative images from {image_dir}", flush=True)
    if not images:
        return {"error": f"no negative images found under {image_dir}"}

    buckets = {
        str(threshold): {
            "raw_images_with_detection": 0,
            "raw_detections": 0,
            "guarded_images_with_detection": 0,
            "guarded_detections": 0,
            "max_confidence": 0.0,
            "examples": [],
        }
        for threshold in thresholds
    }
    guarded_managers = {str(threshold): make_manager(threshold) for threshold in thresholds}
    started = time.perf_counter()

    for index, path in enumerate(images, 1):
        frame = cv2.imread(str(path))
        if frame is None:
            continue

        result = model(frame, conf=min(thresholds), imgsz=640, verbose=False)[0]
        detections = extract_detections(result)

        for threshold in thresholds:
            bucket = buckets[str(threshold)]
            raw = [d for d in detections if d["confidence"] >= threshold]
            if raw:
                bucket["raw_images_with_detection"] += 1
                bucket["raw_detections"] += len(raw)
                bucket["max_confidence"] = max(bucket["max_confidence"], max(d["confidence"] for d in raw))

            manager = guarded_managers[str(threshold)]
            manager.reset()
            guarded = manager.process_detections(detections, frame_shape=frame.shape)
            if guarded:
                bucket["guarded_images_with_detection"] += 1
                bucket["guarded_detections"] += len(guarded)
                if len(bucket["examples"]) < 3:
                    bucket["examples"].append({
                        "image": path.name,
                        "detections": [
                            {"class": item["class_name"], "confidence": round(item["confidence"], 3)}
                            for item in guarded
                        ],
                    })

        if index % 25 == 0:
            print(f"      {index}/{len(images)}", flush=True)

    total = len(images)
    for threshold in thresholds:
        bucket = buckets[str(threshold)]
        bucket["raw_false_positive_rate"] = round(bucket["raw_images_with_detection"] / total, 4)
        bucket["guarded_false_positive_rate"] = round(bucket["guarded_images_with_detection"] / total, 4)
        bucket["max_confidence"] = round(bucket["max_confidence"], 4)

    print(
        "      FP rate at 0.50: raw {:.1%} -> guarded {:.1%}".format(
            buckets["0.5"]["raw_false_positive_rate"], buckets["0.5"]["guarded_false_positive_rate"]
        ),
        flush=True,
    )
    return {
        "image_count": total,
        "thresholds": {k: v for k, v in buckets.items()},
        "elapsed_seconds": round(time.perf_counter() - started, 1),
    }


# ------------------------------------------------------------------- negatives
def run_negative_video(model, video_path: Path, fps_sample: float) -> dict:
    capture = cv2.VideoCapture(str(video_path))
    if not capture.isOpened():
        return {"error": f"could not open {video_path}"}

    fps = capture.get(cv2.CAP_PROP_FPS) or 25.0
    step = max(1, int(round(fps / fps_sample)))
    manager = make_manager(0.5)
    manager.confirmation.required_frames = 2
    manager.confirmation.release_frames = 3

    sampled = raw = 0
    raw_by_class = Counter()
    confirmed_by_class = Counter()
    index = 0
    max_confidence = 0.0
    try:
        while True:
            ok, frame = capture.read()
            if not ok:
                break
            if index % step:
                index += 1
                continue

            sampled += 1
            result = model(frame, conf=0.5, imgsz=640, verbose=False)[0]
            detections = extract_detections(result)
            raw += len(detections)
            raw_by_class.update(d["class_name"] for d in detections)
            if detections:
                max_confidence = max(max_confidence, max(d["confidence"] for d in detections))

            for item in manager.process_detections(detections, frame_shape=frame.shape):
                confirmed_by_class[item["class_name"]] += 1
            index += 1
    finally:
        capture.release()

    return {
        "sampled_frames": sampled,
        "raw_detections": raw,
        "raw_by_class": dict(raw_by_class),
        "max_confidence": round(max_confidence, 4),
        "confirmed_events": sum(confirmed_by_class.values()),
        "confirmed_by_class": dict(confirmed_by_class),
    }


# ----------------------------------------------------------------------- blank
def run_blank_frame_probe(model) -> dict:
    from detection.frame_guard import frame_detail_score, is_informative_frame

    probe = {}
    for label, value in (("white", 245), ("light_grey", 200), ("mid_grey", 128), ("black", 5)):
        frame = np.full((480, 640, 3), value, dtype=np.uint8)
        informative = is_informative_frame(frame, 6.0)
        detections = []
        if informative:  # exactly what the live pipeline does
            detections = extract_detections(model(frame, conf=0.3, imgsz=640, verbose=False)[0])
        probe[label] = {
            "detail_score": round(frame_detail_score(frame), 2),
            "sent_to_model": informative,
            "detections": [
                {"class": d["class_name"], "confidence": round(d["confidence"], 3)} for d in detections
            ],
        }
    return probe


# ---------------------------------------------------------------------- report
def write_markdown(report: dict, path: Path) -> None:
    lines = ["# FireWatch AI — evaluation report", ""]
    lines.append(f"Generated: {report['generated_at']}")
    lines.append(f"Model: `{report['model']}`")
    lines.append("")

    validation = report.get("validation")
    if validation and "error" not in validation:
        lines += [
            "## Labelled metrics",
            "",
            "| Metric | Value |",
            "|---|---|",
            f"| Precision | {validation['precision']:.4f} |",
            f"| Recall | {validation['recall']:.4f} |",
            f"| mAP@50 | {validation['map50']:.4f} |",
            f"| mAP@50-95 | {validation['map50_95']:.4f} |",
            "",
        ]
        per_class = validation.get("per_class") or {}
        if per_class:
            lines += ["| Class | Precision | Recall | mAP@50 | mAP@50-95 |", "|---|---|---|---|---|"]
            for name, values in per_class.items():
                lines.append(
                    f"| {name} | {values['precision']:.4f} | {values['recall']:.4f} | "
                    f"{values['map50']:.4f} | {values['map50_95']:.4f} |"
                )
            lines.append("")

    negatives = report.get("negatives")
    if negatives and "error" not in negatives:
        lines += [
            "## False positives on negatives (no fire / no smoke)",
            "",
            f"{negatives['image_count']} images.",
            "",
            "| Threshold | Raw FP rate | With app guards | Guarded detections |",
            "|---|---|---|---|",
        ]
        for threshold, bucket in negatives["thresholds"].items():
            lines.append(
                f"| {threshold} | {bucket['raw_false_positive_rate']:.1%} | "
                f"{bucket['guarded_false_positive_rate']:.1%} | {bucket['guarded_detections']} |"
            )
        lines.append("")

    videos = report.get("negative_videos") or {}
    if videos:
        lines += ["## Negative video sequences (confirmed events)", "", "| Clip | Sampled frames | Raw detections | Confirmed events |", "|---|---|---|---|"]
        for name, values in videos.items():
            if "error" in values:
                lines.append(f"| {name} | — | — | error |")
            else:
                lines.append(
                    f"| {name} | {values['sampled_frames']} | {values['raw_detections']} | {values['confirmed_events']} |"
                )
        lines.append("")

    blank = report.get("blank_frames") or {}
    if blank:
        lines += ["## Blank-frame guard", "", "| Frame | Detail score | Sent to model | Detections |", "|---|---|---|---|"]
        for label, values in blank.items():
            detections = ", ".join(
                f"{d['class']} {d['confidence']:.2f}" for d in values["detections"]
            ) or "—"
            lines.append(
                f"| {label} | {values['detail_score']} | {values['sent_to_model']} | {detections} |"
            )
        lines.append("")

    path.write_text("\n".join(lines), encoding="utf-8")


def main(argv=None) -> int:
    args = parse_args(argv)
    out_dir = Path(args.out).expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    model_path = Path(args.model).expanduser().resolve()
    thresholds = [float(item) for item in str(args.thresholds).split(",") if item.strip()]
    model = load_model(model_path)

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "model": str(model_path),
        "thresholds": thresholds,
    }

    if args.data:
        data_path = Path(args.data).expanduser()
        if data_path.is_file():
            try:
                report["validation"] = run_validation(model, data_path, args.split, out_dir)
            except Exception as exc:  # noqa: BLE001 - keep the other measurements
                report["validation"] = {"error": f"{type(exc).__name__}: {exc}"}
                print(f"      validation failed: {exc}", flush=True)
        else:
            report["validation"] = {"error": f"data.yaml not found: {data_path}"}

    if args.negatives:
        negatives_root = Path(args.negatives).expanduser()
        report["negatives"] = run_negative_scan(model, negatives_root, thresholds, args.max_images)

        if not args.skip_video:
            clips = negatives_root / "firesense-negative" / "clips"
            videos = {}
            for name in ("fire_negative.avi", "smoke_negative.avi"):
                clip = clips / name
                if clip.is_file():
                    print(f"[3/3] negative clip {name}", flush=True)
                    videos[name] = run_negative_video(model, clip, args.video_fps)
            if videos:
                report["negative_videos"] = videos

    report["blank_frames"] = run_blank_frame_probe(model)

    json_path = out_dir / "evaluation_report.json"
    json_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    write_markdown(report, out_dir / "evaluation_report.md")

    print(f"\nreport written to {json_path}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
