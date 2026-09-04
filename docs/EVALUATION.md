# Evaluation Guide

## Purpose

The default confidence score is deterministic but uncalibrated. This workflow measures whether stated confidence aligns with manual correctness labels and avoids presenting the demo threshold as proven performance.

## Create the Sample

Run the pipeline, stop the API process, then create a deterministic sample:

```bash
python scripts/run_pipeline.py
python scripts/sample_audit.py --size 50 --seed 42
```

The output `data/audit_sample.csv` contains incident identity, asset, issue family, confidence, work-order count, and the complete citation set.

## Labeling Protocol

For each row, inspect the cited work orders in the Investigation view or API and set:

- `actual_correct=1` when grouping, issue interpretation, and recommendation are all supported by the cited evidence.
- `actual_correct=0` when the grouping is wrong, the interpretation exceeds evidence, citations are insufficient, or the recommendation does not follow from the records.

Use `reviewer_note` to record the first failure category. Do not infer correctness from confidence itself. If possible, use two reviewers and adjudicate disagreements.

A `REJECTED` decision removes the incident from operational lists, dashboard aggregates, active asset-risk calculations, search, and generated reports. The direct Investigation view and Review Queue retain the rejected finding for audit with a non-actionable warning.

## Evaluate

```bash
python scripts/evaluate_audit.py
```

The evaluator ignores unlabeled rows and emits:

- `labeled_rows`: number of usable `0` or `1` labels.
- `brier_score`: mean squared error between confidence and correctness. Lower is better.
- `accuracy`: correctness from a diagnostic 0.5 classification boundary.
- `calibration.png`: observed correctness against mean confidence by non-empty decile.

Outputs are stored under `data/calibration/` and excluded from version control.

## Recommended Acceptance Checks

- Review citation containment programmatically for every insight, not just the sample.
- Break down accuracy and Brier score by issue family, department, recurrence, and evidence count.
- Examine false positives separately from false negatives because unnecessary preventive work and missed failures have different costs.
- Tune grouping and review thresholds on a development label set, then report results on a held-out set.
- Record dataset date range and label policy with every reported metric.

## Synthetic Data Limitation

The bundled source is designed to exercise recurring episodes, duplicate records, invalid dates, PII, boilerplate, direct causes, and several infrastructure classes. Metrics computed from it validate software behavior only. They do not measure real-world maintenance performance.
