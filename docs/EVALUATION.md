# Evaluation Guide

## Purpose

The confidence score is deterministic and auditable. Demo mode applies a checked-in synthetic contract artifact fitted from traceable fixture labels; official data requires an artifact fitted from completed manual labels. The synthetic labels test software-contract correctness only and cannot stand in for maintenance expertise, real-world correctness, or official-data calibration.

## Create the Sample

Run the pipeline, stop the API process, then create a deterministic sample:

```bash
python scripts/run_pipeline.py
python scripts/sample_audit.py --size 50 --seed 42
```

The output `data/audit_sample.csv` is selected from a stable incident ordering with a fixed seed. Its `confidence` column contains the raw pre-calibration score and `reported_confidence` contains the stored score. It contains incident identity, asset, issue family, work-order count, supporting and contradicting citations, component-label columns, and a failure category.

For the bundled fixture only, generate reproducible contract labels and evaluate them with a grouped asset holdout:

```bash
python scripts/label_synthetic_audit.py
python scripts/evaluate_audit.py --input data/audit_sample_labeled.csv --allow-synthetic-contract-labels
```

The labeler reads scenario membership from `data/demo/manifest.json` and records
`synthetic_contract_oracle` in every row. It never claims that a human reviewer judged the finding.

## Labeling Protocol

For each row, inspect the cited work orders in the Investigation view or API and set:

- Label `grouping_correct`, `issue_family_correct`, `citations_sufficient`, `interpretation_supported`, and `recommendation_appropriate` as `1` or `0`.
- Set `actual_correct=1` only when every component is `1`; otherwise set it to `0`.

Use `reviewer_note` to record the first failure category. Do not infer correctness from confidence itself. If possible, use two reviewers and adjudicate disagreements.

A `REJECTED` decision removes the incident from operational lists, dashboard aggregates, active asset-risk calculations, search, and generated reports. The direct Investigation view and Review Queue retain the rejected finding for audit with a non-actionable warning.

## Evaluate

```bash
python scripts/evaluate_audit.py
```

The evaluator refuses to publish metrics until at least 50 rows are labeled, validates that all five
component labels agree with `actual_correct`, fits only on raw scores, and emits:

- `labeled_rows`: number of usable `0` or `1` labels.
- `brier_score`: mean squared error between confidence and correctness. Lower is better.
- `accuracy`: correctness from a diagnostic 0.5 classification boundary.
- `threshold_analysis`: auto-accept precision, coverage, and review load at candidate thresholds.
- `calibration.json`: versioned isotonic artifact used by later pipeline runs when explicitly configured.
- `calibration.png`: observed correctness against mean confidence by non-empty decile.
- `holdout_calibrated`: metrics after applying the fitted artifact to asset-held-out rows.

Outputs are stored under `data/calibration/` and excluded from version control. The generated artifact carries score space, dataset ID, label source, label policy, and split provenance. Operational runs must set `CIVICOPS_CALIBRATION_DATASET_ID` to the exact dataset ID in the manually labeled artifact; synthetic contract results are for software validation and cannot satisfy that requirement.

## Independent Engineering Audit

The repository's automated tests check common-primary-asset containment, same-family grouping,
episode span limits, exact citation grounding, evidence/inference separation, conservative causes,
action fit, redaction, and transactional persistence. Run the full suite after each pipeline change.

The authenticated operator response intentionally retains sites and asset identifiers. Before an
external model call, a second privacy boundary removes address-like locations as well as employee
PII. Detector coverage is not proof that every possible identifier has been found; external calls
still fail closed when a known identifier pattern remains.

These automated checks validate engineering invariants only. They are not a manual label set, do
not calibrate confidence, and must not justify an automatic-accept threshold.

## Recommended Acceptance Checks

- Review citation containment programmatically for every insight, not just the sample.
- Break down accuracy and Brier score by issue family, department, recurrence, and evidence count.
- Examine false positives separately from false negatives because unnecessary preventive work and missed failures have different costs.
- Tune grouping and review thresholds on a development label set, then report results on a held-out set.
- Record dataset date range and label policy with every reported metric.

## Synthetic Data Limitation

The bundled source is designed to exercise recurring episodes, duplicate records, invalid dates, PII, boilerplate, direct causes, and several infrastructure classes. Metrics computed from it validate software behavior only. They do not measure real-world maintenance performance.
