# CivicOps AI Submission Checklist

This checklist maps the challenge rubric and required deliverables to repository evidence. It keeps synthetic/demo evidence, official Cityworks evidence, engineering validation, and future manual calibration separate.

## Provenance Rules

| Artifact or result | Provenance | Allowed claim |
| --- | --- | --- |
| `data/demo/**` | Bundled synthetic/demo fixture | Reproducible software behavior and source-level examples. |
| `data/raw/**` | Git-ignored authorized starter or Cityworks CSVs | Local integration only; do not commit or present as bundled data. |
| `docs/screenshots/**` and `docs/demo/**` | Product captures with dataset provenance labeled in `README.md`; the bundled path uses synthetic data and separate official validation remains outside Git | Product-surface evidence; not raw source or model-performance evidence. |
| `docs/EVALUATION.md` engineering audit | Automated invariant review workflow over a deterministic 50-row sample | Engineering quality evidence; not manual calibration or accuracy. |
| `data/audit_sample.csv` and `data/calibration/**` | Generated audit artifacts; the bundled path uses reproducible contract labels while official calibration requires human labels; ignored from version control | Software-validation evidence for the synthetic path; operational calibration evidence only when the manual label protocol and metrics are present. |

Never call the bundled fixture official. Never present deterministic row counts as accuracy. Never fabricate manual labels, calibration metrics, PM interval changes, or field outcomes.

## Fast Verification

### Safe synthetic/demo path

```bash
python scripts/run_pipeline.py --source data/demo
python -m pytest
```

The current default demo run retains 222 unique work orders from 224 source rows, 74 composite asset keys, and 119 incident groups. It uses the offline TF-IDF backend, produced 30 recurring groups, routed 76 findings to review, and applies the checked-in synthetic contract calibration artifact. These are smoke-test counts only.

### Official Cityworks path

Use only an authorized local copy of the official starter repository or export:

```bash
python scripts/import_starter_data.py --starter ../ai4infra-starter
python scripts/run_pipeline.py --source data/raw
```

Then run the full-corpus contract test:

```powershell
$env:CIVICOPS_RUN_STARTER_SMOKE = "1"
python -m pytest tests/test_starter_compatibility.py
```

The documented local official smoke run retained 27,605 work orders, 26,413 non-catch-all composite assets, 23,744 note-backed maintenance work orders, 23,062 bounded episodes, 77 recurring episodes, and 22,935 findings routed to review. These counts are documented in [STARTER_TEMPLATE.md](STARTER_TEMPLATE.md) and do not measure field performance.

## Rubric Map

| Rubric item | Weight | Repository artifact | What to show | Caveat to state |
| --- | ---: | --- | --- | --- |
| ALP Logic Depth | 30 | `backend/app/alp/rules.yaml`, `alp/engine.py`, `alp/observations.py`, `alp/interpretations.py`, `alp/actions.py`, `data/feature_engineering.py`, notebook Sections 3 to 6 | Corpus-grounded issue families, trigger method/exemplar/score, episode observations, cautious cause support, and preventive actions. | Starter rotating-equipment phrases are not treated as the municipal trigger list; the corpus supplies the wording. |
| Architectural Integrity | 30 | `docs/ARCHITECTURE.md`, `data/loader.py`, `data/normalizer.py`, `retrieval/embeddings.py`, `retrieval/candidates.py`, `incidents/grouping.py`, `models/repository.py`, `pipeline.py` | Projected ingestion, bounded retrieval, weighted graph, transactional persistence, optional generation, API, and UI. | DuckDB is a single-service demo adapter; production needs PostgreSQL staging and identity-aware deployment. |
| Explainability | 20 | `rag/grounding.py`, `rag/prompts.py`, `models/domain.py`, `analytics/report.py`, `docs/API.md`, `screenshots/investigation-desktop.png`, `tests/test_reasoning.py`, `tests/test_api.py` | Exact `WorkOrderId` citations, evidence and inference lanes, contradiction handling, edge reasons, confidence breakdown, review record, and grounded report. | Engineering audit checks invariants; it is not a manual accuracy or calibration study. |
| Data Normalization | 10 | `data/validators.py`, `data/normalizer.py`, `data/cleaner.py`, `data/pii.py`, `scripts/import_starter_data.py`, `docs/STARTER_TEMPLATE.md`, `tests/test_data_pipeline.py`, `tests/test_starter_compatibility.py` | Unique job grain, `EntityType:EntityUid`, relationship roles, sentinel-date rejection, bulk/catch-all isolation, boilerplate removal, and redaction. | Raw official CSVs remain outside Git; authenticated operator output can retain operational site and asset identifiers. |
| Operational Impact | 10 | `frontend/src/pages/`, `frontend/src/api.ts`, `backend/app/api/router.py`, `backend/app/api/query_service.py`, `analytics/report.py`, screenshots, walkthrough | Dashboard, incidents, asset intelligence, investigation, human review, search, Markdown/JSON briefing, and pending authorization. | Recommendations remain decision support; risk is not a failure probability and PM intervals remain unconfirmed. |

## Required Deliverables Map

| Requirement | Artifact | Verification or demo proof |
| --- | --- | --- |
| RAG over work-order text | `aisa_challenge.ipynb` Sections 8 and 10; `backend/app/retrieval/`; `backend/app/rag/` | Show query -> retrieved context -> WorkOrderId citations -> structured synthesis boundary. Default product path remains deterministic and offline. |
| RAG over procedure material | `aisa_challenge.ipynb` Section 11; `pdfs/` | Show page-preserving chunks, 900-character chunks with 150 overlap, file/page citations, and the distinction between history and procedure evidence. |
| Privacy before external retrieval | `backend/app/data/cleaner.py`, `data/pii.py`, `rag/prompts.py`, `rag/providers.py`, `docs/ARCHITECTURE.md` | Explain raw, clean, redacted, and external-only redacted text. Show fail-closed behavior for detectable identifiers. |
| Grounded generation | `backend/app/rag/grounding.py`, `tests/test_reasoning.py` | Any cited supporting or contradicting work order outside the retrieved set raises a grounding error. |
| ALP expert heuristics | `backend/app/alp/rules.yaml`, `alp/engine.py`, notebook exploration, `docs/PRESENTATION.md` Slide 07 | Walk through observation -> interpretation -> possible cause -> action and support levels. |
| Sequence and recurrence reasoning | `retrieval/candidates.py`, `incidents/grouping.py`, `docs/ARCHITECTURE.md` | Explain composite primary assets, bounded candidates, weighted edges, 180-day span, and the three-work-order recurrence rule. |
| Auditable confidence | `confidence/engine.py`, `confidence/risk.py`, `docs/ARCHITECTURE.md` | Show component formula, conflict penalty, levels, review routing, and the separation between risk and correctness. |
| Calibration workflow | `scripts/sample_audit.py`, `scripts/label_synthetic_audit.py`, `scripts/evaluate_audit.py`, `evaluation/calibration.py`, `evaluation/demo_calibration.json`, `docs/EVALUATION.md`, `tests/test_evaluation.py` | Show the synthetic contract artifact, inspect its 50 traceable labels, and run grouped asset-held-out Brier/accuracy/bins/threshold analysis. Manual labels remain required for operations. |
| Structured `PM_INSIGHT_REPORT` | `analytics/report.py`, `analytics/schemas.py`, `docs/API.md`, `screenshots/reports-desktop.png` | Show schema `2.0`, complete-by-default findings, explicit selection/truncation fields, PM interval evidence, field-level citations, provenance, review state, and pending authorization. |
| Human review loop | `backend/app/api/router.py`, `api/schemas.py`, `frontend/src/pages/ReviewPage.tsx`, `docs/EVALUATION.md` | Confirm, reject, or edit a finding with a redacted reviewer note; rejected findings remain in audit views. |

## Synthetic Citation Examples

These IDs are real rows in `data/demo/` and are safe examples for the presentation:

| Story | IDs | Evidence location | Correct framing |
| --- | --- | --- | --- |
| Low-pressure sequence on `VALVE:0001` | `WO-10001` to `WO-10004` | `data/demo/WORKORDER.csv`, `data/demo/WOENTITY.csv`, `data/demo/WOCOMMENT.csv` | Synthetic observations include low pressure, below-range pressure, a returned issue, a corroded valve stem, and a later replacement. Keep cause language cautious. |
| Sewer-backup sequence on `SEWER_MAIN:0004` | `WO-10013` to `WO-10016` | Same three demo tables | Synthetic observations include a cleared blockage, recurrence, and root intrusion documented at joint 14. Treat contribution as a hypothesis unless the cause rule marks direct support. |
| PII redaction exercise | `WO-10002`, `WO-10046`, `WO-10090` | `data/demo/WOCOMMENT.csv` | Say the fixture contains synthetic test identifiers and the pipeline redacts them; do not repeat the identifiers in a demo narrative. |

## Short Demo Script

1. Start the safe path with `docker compose up --build` and open `http://localhost:3000`.
2. Open `/api/v1/health` and point out `Synthetic Demo Dataset` when the bundled fixture is loaded.
3. Show the Dashboard, then the Incident Explorer, Asset Intelligence, Investigation, Review Queue, and Reports/Search views.
4. In Investigation, show the separation between observations, interpretation, possible cause, action, citations, confidence components, and pending authorization.
5. Open the API documentation at `http://localhost:8000/docs`; show `/incidents/{incident_id}`, `/reviews`, `/search`, and both report endpoints. Non-health endpoints require `X-CivicOps-Key` as documented in `API.md`.
6. Open `data/demo/WOCOMMENT.csv` and walk through `WO-10013` to `WO-10016` as the synthetic evidence example. Call every conclusion synthetic/demo.
7. Download `maintenance.json` and point to `REPORT_TYPE`, `SCHEMA_VERSION`, `OBSERVATIONS`, `CAUSAL_SUPPORT_LEVEL`, citations, confidence components, `PM_INTERVAL_RECOMMENDATION`, and `DISPATCH_STATUS`.
8. If authorized official data is available, import it into ignored `data/raw/`, rerun the pipeline, and show the UI's official dataset label. Do not mix official-derived screenshots with bundled demo claims.
9. Close on calibration: the 50-row label workflow exists, but no manual labels or production threshold are claimed until reviewers complete it.

## Judge-Facing Links

- [Presentation](PRESENTATION.md)
- [Architecture](ARCHITECTURE.md)
- [API guide](API.md)
- [Evaluation and calibration](EVALUATION.md)
- [Official starter integration](STARTER_TEMPLATE.md)
- [Challenge brief](../challenge.md)
- [Exploration notebook](../aisa_challenge.ipynb)
- [Dashboard capture](screenshots/dashboard-desktop.png)
- [Investigation capture](screenshots/investigation-desktop.png)
- [Reports capture](screenshots/reports-desktop.png)
- [Full walkthrough](demo/civicops-ai-walkthrough-final.mp4)
