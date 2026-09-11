import pytest
from app.analytics import report
from app.evaluation.calibration import (
    calibration_bins,
    evaluate_predictions,
    threshold_analysis,
)


def test_evaluation_calculates_brier_score_and_accuracy() -> None:
    metrics = evaluate_predictions([(0.9, 1), (0.8, 1), (0.2, 0), (0.6, 0)])

    assert metrics == {"labeled_rows": 4, "brier_score": 0.1125, "accuracy": 0.75}


def test_calibration_bins_preserve_all_predictions() -> None:
    bins = calibration_bins([(0.0, 0), (0.45, 1), (1.0, 1)], bin_count=5)

    assert sum(item.count for item in bins) == 3
    assert bins[-1].mean_confidence == 1.0


def test_evaluation_requires_valid_labels() -> None:
    with pytest.raises(ValueError):
        evaluate_predictions([(0.5, 2)])


def test_threshold_analysis_reports_precision_coverage_and_review_load() -> None:
    rows = threshold_analysis([(0.9, 1), (0.8, 0), (0.4, 1)], thresholds=(0.8,))

    assert rows == [
        {
            "threshold": 0.8,
            "auto_accept_count": 2,
            "auto_accept_precision": 0.5,
            "review_load": 1,
            "coverage": 0.666667,
        }
    ]


def test_report_handles_an_empty_atomic_snapshot() -> None:
    assert report._finding_lines([]) == ["No findings in this section."]
    assert report._recommendation_lines([]) == ["No recommendations generated."]
