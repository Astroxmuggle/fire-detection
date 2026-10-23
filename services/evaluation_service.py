from __future__ import annotations


def compute_precision_recall_f1(true_positives, false_positives, false_negatives):
    precision = true_positives / (true_positives + false_positives) if (true_positives + false_positives) else 0.0
    recall = true_positives / (true_positives + false_negatives) if (true_positives + false_negatives) else 0.0
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0

    return {
        "true_positives": true_positives,
        "false_positives": false_positives,
        "false_negatives": false_negatives,
        "precision": precision,
        "recall": recall,
        "f1_score": f1,
    }


def summarize_predictions(predictions):
    total_predictions = len(predictions)
    high_confidence = sum(1 for item in predictions if float(item.get("confidence", 0.0)) >= 0.5)
    by_class = {}

    for item in predictions:
        class_name = str(item.get("class_name", "unknown")).lower()
        by_class[class_name] = by_class.get(class_name, 0) + 1

    return {
        "total_predictions": total_predictions,
        "high_confidence_predictions": high_confidence,
        "by_class": by_class,
    }
