from dataclasses import dataclass


@dataclass(frozen=True)
class CalibrationBin:
    lower: float
    upper: float
    mean_confidence: float
    observed_accuracy: float
    count: int


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
