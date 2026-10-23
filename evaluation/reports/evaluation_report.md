# FireWatch AI — evaluation report

Generated: 2026-10-23T01:54:44+00:00
Model: `C:\Users\manna_2c83x\fire-detection-ai\firedetec2\fire-detection-ai\models\best.pt`

## Labelled metrics

| Metric | Value |
|---|---|
| Precision | 0.7121 |
| Recall | 0.6908 |
| mAP@50 | 0.6854 |
| mAP@50-95 | 0.3279 |

| Class | Precision | Recall | mAP@50 | mAP@50-95 |
|---|---|---|---|---|
| fire | 0.8753 | 0.9019 | 0.9370 | 0.4997 |
| smoke | 0.5490 | 0.4796 | 0.4338 | 0.1561 |

## False positives on negatives (no fire / no smoke)

50 images.

| Threshold | Raw FP rate | With app guards | Guarded detections |
|---|---|---|---|
| 0.5 | 4.0% | 4.0% | 2 |
| 0.4 | 6.0% | 6.0% | 3 |
| 0.3 | 14.0% | 14.0% | 7 |

## Negative video sequences (confirmed events)

| Clip | Sampled frames | Raw detections | Confirmed events |
|---|---|---|---|
| fire_negative.avi | 16 | 7 | 1 |
| smoke_negative.avi | 46 | 0 | 0 |

## Blank-frame guard

| Frame | Detail score | Sent to model | Detections |
|---|---|---|---|
| white | 0.0 | False | — |
| light_grey | 0.0 | False | — |
| mid_grey | 0.0 | False | — |
| black | 0.0 | False | — |
