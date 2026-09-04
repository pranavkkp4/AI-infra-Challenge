#!/usr/bin/env python3
import argparse
import csv
import json
from pathlib import Path

import matplotlib.pyplot as plt
from app.evaluation.calibration import calibration_bins, evaluate_predictions


def read_labels(source: Path) -> list[tuple[float, int]]:
    with source.open(newline="", encoding="utf-8") as handle:
        rows = csv.DictReader(handle)
        return [
            (float(row["confidence"]), int(row["actual_correct"]))
            for row in rows
            if row["actual_correct"].strip() in {"0", "1"}
        ]


def save_plot(predictions: list[tuple[float, int]], destination: Path) -> None:
    bins = calibration_bins(predictions)
    destination.parent.mkdir(parents=True, exist_ok=True)
    figure, axis = plt.subplots(figsize=(6, 6))
    axis.plot(
        [0, 1], [0, 1], linestyle="--", color="#6f7779", label="Perfect calibration"
    )
    axis.plot(
        [item.mean_confidence for item in bins],
        [item.observed_accuracy for item in bins],
        marker="o",
        color="#ff7a1a",
        label="CivicOps confidence",
    )
    axis.set(
        xlim=(0, 1), ylim=(0, 1), xlabel="Mean confidence", ylabel="Observed accuracy"
    )
    axis.legend()
    axis.grid(alpha=0.2)
    figure.tight_layout()
    figure.savefig(destination, dpi=160)
    plt.close(figure)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Evaluate manually labeled confidence predictions"
    )
    parser.add_argument("--input", type=Path, default=Path("data/audit_sample.csv"))
    parser.add_argument("--output-dir", type=Path, default=Path("data/calibration"))
    args = parser.parse_args()
    predictions = read_labels(args.input)
    if not predictions:
        parser.error(
            "No labels found. Set actual_correct to 0 or 1 in the audit sample"
        )
    metrics = evaluate_predictions(predictions)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    report_path = args.output_dir / "metrics.json"
    report_path.write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    save_plot(predictions, args.output_dir / "calibration.png")
    print(json.dumps(metrics, indent=2))
