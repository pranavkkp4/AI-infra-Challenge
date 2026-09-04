import pytest
from app.analytics import report
from app.evaluation.calibration import calibration_bins, evaluate_predictions


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


def test_report_skips_incidents_removed_during_snapshot_replacement(
    monkeypatch,
) -> None:
    monkeypatch.setattr(report, "incident_detail", lambda *_args: None)
    incidents = [{"incident_id": "INC-REMOVED"}]

    assert report._finding_lines(object(), incidents) == [
        "No findings in this section."
    ]
    assert report._recommendation_lines(object(), incidents) == [
        "No recommendations generated."
    ]
