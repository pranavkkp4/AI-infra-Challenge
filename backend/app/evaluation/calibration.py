import json
from bisect import bisect_right
from dataclasses import dataclass
from pathlib import Path

from pydantic import BaseModel, Field, model_validator


@dataclass(frozen=True)
class CalibrationBin:
    lower: float
    upper: float
    mean_confidence: float
    observed_accuracy: float
    count: int


class CalibrationArtifact(BaseModel):
    """Versioned, portable isotonic calibration artifact."""

    artifact_version: str = "1.0"
    artifact_id: str
    method: str = "isotonic"
    source: str
    synthetic: bool = False
    score_space: str = "raw"
    dataset_id: str = "unknown"
    label_source: str = "manual_reviewer"
    label_policy: str = "actual_correct"
    split: str = "train"
    sample_count: int = Field(ge=1)
    x_values: list[float] = Field(min_length=1)
    y_values: list[float] = Field(min_length=1)
    metrics: dict[str, float | int] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_curve(self) -> "CalibrationArtifact":
        if len(self.x_values) != len(self.y_values):
            raise ValueError("Calibration curve x_values and y_values must have equal length")
        if any(not 0 <= value <= 1 for value in self.x_values + self.y_values):
            raise ValueError("Calibration curve values must be in [0, 1]")
        if any(left > right for left, right in zip(self.x_values, self.x_values[1:], strict=False)):
            raise ValueError("Calibration x_values must be sorted")
        if any(left > right for left, right in zip(self.y_values, self.y_values[1:], strict=False)):
            raise ValueError("Isotonic y_values must be monotonic")
        return self

    @property
    def version(self) -> str:
        return self.artifact_version

    def transform(self, score: float) -> float:
        if not 0 <= score <= 1:
            raise ValueError("Confidence must be in [0, 1]")
        index = max(0, bisect_right(self.x_values, score) - 1)
        return self.y_values[index]

    def transform_scores(self, scores: list[float]) -> list[float]:
        return [self.transform(score) for score in scores]

    def provenance(self) -> dict[str, object]:
        return {
            "applied": True,
            "artifact_id": self.artifact_id,
            "artifact_version": self.artifact_version,
            "method": self.method,
            "source": self.source,
            "synthetic": self.synthetic,
            "score_space": self.score_space,
            "dataset_id": self.dataset_id,
            "label_source": self.label_source,
            "label_policy": self.label_policy,
            "split": self.split,
            "sample_count": self.sample_count,
            "metrics": self.metrics,
        }


def default_demo_calibration_path() -> Path:
    """Return the checked-in, provisional curve used only by the safe demo mode."""

    return Path(__file__).with_name("demo_calibration.json")


def fit_calibrator(
    predictions: list[tuple[float, int]] | list[float],
    labels: list[int] | None = None,
    *,
    artifact_id: str = "calibration-isotonic-v1",
    source: str = "explicit_labeled_audit",
    synthetic: bool = False,
    dataset_id: str = "unknown",
    label_source: str = "manual_reviewer",
    label_policy: str = "actual_correct",
    split: str = "train",
) -> CalibrationArtifact:
    """Fit a deterministic isotonic transform using labeled audit predictions."""

    pairs = _prediction_pairs(predictions, labels)
    metrics = evaluate_predictions(pairs)
    blocks: list[dict[str, float | int]] = []
    for score, label in sorted(pairs, key=lambda item: item[0]):
        blocks.append({"x_min": score, "y_sum": label, "count": 1})
        while len(blocks) > 1 and (
            blocks[-2]["x_min"] == blocks[-1]["x_min"]
            or _block_mean(blocks[-2], "y_sum") > _block_mean(blocks[-1], "y_sum")
        ):
            right = blocks.pop()
            left = blocks.pop()
            blocks.append(
                {
                    "x_min": left["x_min"],
                    "y_sum": left["y_sum"] + right["y_sum"],
                    "count": left["count"] + right["count"],
                }
            )
    x_values = [float(block["x_min"]) for block in blocks]
    y_values = [float(block["y_sum"] / block["count"]) for block in blocks]
    calibrated = [(_transform_curve(x_values, y_values, score), label) for score, label in pairs]
    metrics.update(
        {
            "calibrated_brier_score": round(
                sum((score - label) ** 2 for score, label in calibrated) / len(calibrated), 6
            )
        }
    )
    return CalibrationArtifact(
        artifact_id=artifact_id,
        source=source,
        synthetic=synthetic,
        dataset_id=dataset_id,
        label_source=label_source,
        label_policy=label_policy,
        split=split,
        sample_count=len(pairs),
        x_values=x_values,
        y_values=y_values,
        metrics=metrics,
    )


def _transform_curve(x_values: list[float], y_values: list[float], score: float) -> float:
    return y_values[max(0, bisect_right(x_values, score) - 1)]


def _block_mean(block: dict[str, float | int], key: str) -> float:
    return float(block[key] / block["count"])


def _prediction_pairs(
    predictions: list[tuple[float, int]] | list[float], labels: list[int] | None
) -> list[tuple[float, int]]:
    if labels is None:
        pairs = []
        for item in predictions:
            if not isinstance(item, (tuple, list)) or len(item) != 2:
                raise ValueError("Labeled predictions must contain (confidence, label) pairs")
            score, label = item
            pairs.append((float(score), int(label)))
    else:
        if len(predictions) != len(labels):
            raise ValueError("Scores and labels must have equal length")
        pairs = [
            (float(score), int(label)) for score, label in zip(predictions, labels, strict=True)
        ]
    if not pairs:
        raise ValueError("At least one labeled prediction is required")
    if any(label not in {0, 1} or not 0 <= score <= 1 for score, label in pairs):
        raise ValueError("Confidence must be in [0, 1] and labels must be 0 or 1")
    return pairs


def save_calibration_artifact(artifact: CalibrationArtifact, destination: Path | str) -> None:
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(artifact.model_dump_json(indent=2), encoding="utf-8")


def load_calibration_artifact(source: Path | str) -> CalibrationArtifact:
    source = Path(source)
    return CalibrationArtifact.model_validate(json.loads(source.read_text(encoding="utf-8")))


def transform_score(artifact: CalibrationArtifact, score: float) -> float:
    return artifact.transform(score)


def transform_scores(artifact: CalibrationArtifact, scores: list[float]) -> list[float]:
    return artifact.transform_scores(scores)


fit_isotonic = fit_calibrator
load_calibrator = load_calibration_artifact


def evaluate_predictions(predictions: list[tuple[float, int]]) -> dict[str, float | int]:
    if not predictions:
        raise ValueError("At least one labeled prediction is required")
    if any(label not in {0, 1} or not 0 <= confidence <= 1 for confidence, label in predictions):
        raise ValueError("Confidence must be in [0, 1] and labels must be 0 or 1")
    count = len(predictions)
    brier = sum((confidence - label) ** 2 for confidence, label in predictions) / count
    accuracy = sum((confidence >= 0.5) == bool(label) for confidence, label in predictions) / count
    return {"labeled_rows": count, "brier_score": round(brier, 6), "accuracy": round(accuracy, 6)}


def calibration_bins(
    predictions: list[tuple[float, int]], bin_count: int = 10
) -> list[CalibrationBin]:
    if bin_count < 1:
        raise ValueError("bin_count must be positive")
    bins: list[CalibrationBin] = []
    for index in range(bin_count):
        lower, upper = index / bin_count, (index + 1) / bin_count
        members = [
            item
            for item in predictions
            if lower <= item[0] < upper or (index == bin_count - 1 and item[0] == 1)
        ]
        if members:
            bins.append(
                CalibrationBin(
                    lower=lower,
                    upper=upper,
                    mean_confidence=sum(item[0] for item in members) / len(members),
                    observed_accuracy=sum(item[1] for item in members) / len(members),
                    count=len(members),
                )
            )
    return bins


def threshold_analysis(
    predictions: list[tuple[float, int]], thresholds: tuple[float, ...] = (0.5, 0.6, 0.7, 0.8, 0.9)
) -> list[dict[str, float | int]]:
    if not predictions:
        raise ValueError("At least one labeled prediction is required")
    rows = []
    for threshold in thresholds:
        accepted = [label for confidence, label in predictions if confidence >= threshold]
        rows.append(
            {
                "threshold": threshold,
                "auto_accept_count": len(accepted),
                "auto_accept_precision": round(sum(accepted) / len(accepted), 6)
                if accepted
                else 0.0,
                "review_load": sum(confidence < threshold for confidence, _ in predictions),
                "coverage": round(len(accepted) / len(predictions), 6),
            }
        )
    return rows
