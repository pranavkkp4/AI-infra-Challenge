#!/usr/bin/env python3
import argparse
import csv
import json
import sys
from hashlib import sha256
from pathlib import Path

import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.evaluation.calibration import (
    calibration_bins,
    evaluate_predictions,
    fit_calibrator,
    save_calibration_artifact,
    threshold_analysis,
)

COMPONENT_FIELDS = (
    "grouping_correct",
    "issue_family_correct",
    "citations_sufficient",
    "interpretation_supported",
    "recommendation_appropriate",
)


def read_labeled_rows(source: Path) -> list[dict[str, str]]:
    with source.open(newline="", encoding="utf-8") as handle:
        rows = csv.DictReader(handle)
        labeled = []
        for row in rows:
            if row["actual_correct"].strip() not in {"0", "1"}:
                continue
            for field in COMPONENT_FIELDS:
                if row.get(field, "").strip() not in {"0", "1"}:
                    raise ValueError(
                        f"Labeled row {row['incident_id']} has an invalid {field}"
                    )
            expected = int(all(row[field] == "1" for field in COMPONENT_FIELDS))
            if int(row["actual_correct"]) != expected:
                raise ValueError(
                    f"Labeled row {row['incident_id']} has inconsistent actual_correct"
                )
            labeled.append(row)
    return labeled


def split_by_asset(
    rows: list[dict[str, str]], holdout_fraction: float
) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    if not 0 < holdout_fraction < 1:
        raise ValueError("holdout_fraction must be between 0 and 1")
    assets = sorted({row.get("asset_key", "") for row in rows})
    if len(assets) < 2:
        raise ValueError("At least two assets are required for a grouped holdout")
    holdout_count = max(1, round(len(assets) * holdout_fraction))
    ranked_assets = sorted(
        assets,
        key=lambda asset: sha256(asset.encode("utf-8")).hexdigest(),
    )
    holdout_assets = set(ranked_assets[:holdout_count])
    train = [row for row in rows if row.get("asset_key") not in holdout_assets]
    holdout = [row for row in rows if row.get("asset_key") in holdout_assets]
    if not train or not holdout:
        raise ValueError("Grouped holdout split produced an empty partition")
    return train, holdout


def prediction_pairs(rows: list[dict[str, str]]) -> list[tuple[float, int]]:
    return [(float(row["confidence"]), int(row["actual_correct"])) for row in rows]


def declared_value(rows: list[dict[str, str]], field: str, default: str) -> str:
    values = {row.get(field, "").strip() for row in rows if row.get(field, "").strip()}
    if len(values) > 1:
        raise ValueError(f"Labeled sample contains multiple {field} values")
    return next(iter(values), default)


def save_plot(
    raw_predictions: list[tuple[float, int]],
    calibrated_predictions: list[tuple[float, int]],
    destination: Path,
) -> None:
    raw_bins = calibration_bins(raw_predictions)
    calibrated_bins = calibration_bins(calibrated_predictions)
    destination.parent.mkdir(parents=True, exist_ok=True)
    figure, axis = plt.subplots(figsize=(6, 6))
    axis.plot(
        [0, 1], [0, 1], linestyle="--", color="#6f7779", label="Perfect calibration"
    )
    axis.plot(
        [item.mean_confidence for item in raw_bins],
        [item.observed_accuracy for item in raw_bins],
        marker="o",
        color="#ff7a1a",
        label="Raw confidence",
    )
    axis.plot(
        [item.mean_confidence for item in calibrated_bins],
        [item.observed_accuracy for item in calibrated_bins],
        marker="o",
        color="#008f95",
        label="Calibrated confidence",
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
    parser.add_argument("--minimum-labels", type=int, default=50)
    parser.add_argument("--holdout-fraction", type=float, default=0.2)
    parser.add_argument(
        "--allow-synthetic-contract-labels",
        action="store_true",
        help="Permit fixture contract labels; these are not human maintenance judgments",
    )
    args = parser.parse_args()
    rows = read_labeled_rows(args.input)
    if len(rows) < args.minimum_labels:
        parser.error(
            f"At least {args.minimum_labels} labels are required; found {len(rows)}"
        )
    label_source = declared_value(rows, "label_source", "manual_reviewer")
    synthetic = label_source.startswith("synthetic_")
    if synthetic and not args.allow_synthetic_contract_labels:
        parser.error(
            "Synthetic contract labels require --allow-synthetic-contract-labels and remain "
            "non-human validation evidence"
        )
    train_rows, holdout_rows = split_by_asset(rows, args.holdout_fraction)
    train_predictions = prediction_pairs(train_rows)
    holdout_predictions = prediction_pairs(holdout_rows)
    dataset_id = declared_value(
        rows,
        "dataset_id",
        f"audit-file:{sha256(args.input.read_bytes()).hexdigest()[:16]}",
    )
    label_policy = declared_value(rows, "label_policy", "actual_correct")
    artifact = fit_calibrator(
        train_predictions,
        source=f"{label_source}:{dataset_id}",
        synthetic=synthetic,
        dataset_id=dataset_id,
        label_source=label_source,
        label_policy=label_policy,
        split="grouped_train",
    )
    calibrated_holdout = [
        (artifact.transform(score), label) for score, label in holdout_predictions
    ]
    train_metrics = evaluate_predictions(train_predictions)
    holdout_metrics = evaluate_predictions(holdout_predictions)
    calibrated_holdout_metrics = evaluate_predictions(calibrated_holdout)
    artifact = artifact.model_copy(
        update={
            "metrics": {
                **artifact.metrics,
                "total_labeled_rows": len(rows),
                "train_rows": len(train_rows),
                "holdout_rows": len(holdout_rows),
                "holdout_raw_brier_score": holdout_metrics["brier_score"],
                "holdout_calibrated_brier_score": calibrated_holdout_metrics[
                    "brier_score"
                ],
            }
        }
    )
    args.output_dir.mkdir(parents=True, exist_ok=True)
    save_calibration_artifact(artifact, args.output_dir / "calibration.json")
    metrics = {
        "label_source": label_source,
        "label_policy": label_policy,
        "dataset_id": dataset_id,
        "score_space": "raw",
        "train": train_metrics,
        "holdout_raw": holdout_metrics,
        "holdout_calibrated": calibrated_holdout_metrics,
        "threshold_analysis": threshold_analysis(calibrated_holdout),
        "calibration_artifact": artifact.provenance(),
    }
    report_path = args.output_dir / "metrics.json"
    report_path.write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    save_plot(
        holdout_predictions, calibrated_holdout, args.output_dir / "calibration.png"
    )
    print(json.dumps(metrics, indent=2))
