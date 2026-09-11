# Official Starter Template Integration

CivicOps AI extends the University of Colorado Denver
[`ai4infraChallengeStudentStarterPack1`](https://github.com/cudenver-ai/ai4infraChallengeStudentStarterPack1)
starter. The original brief, output-cleared notebook, notebook requirements, and procedure PDFs are retained
at the repository root so the supplied exploration path remains available.

## Safe Data Setup

The starter repository publishes a real Cityworks export. It contains employee names and free-text
locations, so this submission does not duplicate the CSVs or `secrets.json` in Git.

```bash
git clone https://github.com/cudenver-ai/ai4infraChallengeStudentStarterPack1.git ../ai4infra-starter
python scripts/import_starter_data.py --starter ../ai4infra-starter
python scripts/run_pipeline.py --source data/raw
```

The importer accepts either the starter repository root or its `data/` folder and handles both
`data.zip` and already-expanded CSVs. The pipeline also accepts a starter root directly:

```bash
python scripts/run_pipeline.py --source ../ai4infra-starter
```

Use `secrets.example.json` only when running the optional Gemini notebook cells. Never commit the
resulting `secrets.json`.

## Verified Source Contract

| Source | Starter rows | CivicOps handling |
| --- | ---: | --- |
| `WORKORDER.csv` | 37,778 | Projected read; `InitiateDate`, `Shop`, `AssetGroup`, site, reactive state, status, and priority normalized |
| `WOENTITY.csv` | 867,448 | Composite `EntityType:EntityUid`; equipment/location class retained; inventory sweeps and catch-all entities isolated |
| `WOCOMMENT.csv` | 33,572 | Numeric `CommentId` ordering; dispatcher scaffold removal; raw, cleaned, and redacted forms kept separately |

The full local smoke test produced:

- 27,605 work orders retained after invalid-date, distinct-asset bulk-inventory, and unusable-asset exclusions.
- 26,413 non-catch-all composite assets: 16,899 equipment records and 9,514 location records.
- 23,744 note-backed maintenance work orders eligible for analysis; 57 explicit administrative or supply-order records remain searchable but are excluded from reasoning.
- 23,062 bounded same-primary-asset incident episodes, including 77 recurring episodes with at least three semantically linked jobs.
- 22,935 newly generated findings routed to human review under the conservative, explicitly uncalibrated default policy.
- 22,174 retained source comments redacted for official Cityworks name patterns.
- 711,362 blocked candidate pairs scored instead of a 281,876,896-pair full similarity matrix.

These are deterministic pipeline counts, not field-performance or model-accuracy claims.

## Challenge Mapping

| Scoring area | CivicOps implementation |
| --- | --- |
| ALP logic depth | Mined crew-language trigger exemplars, exact and embedding-based trigger retrieval, `backend/app/alp/rules.yaml`, observation/interpretation/cause/action separation |
| Architectural integrity | Projected Polars ingestion, bounded pair scoring, optional sentence-transformer/FAISS index, transactional persistence |
| Explainability | Evidence-bound work-order citations, confidence decomposition, grounding gate, review audit trail |
| Data normalization | Exact official aliases, composite assets, sentinel-date rejection, bulk/catch-all isolation, PII redaction |
| Operational impact | Risk register, recurring episodes, investigations, review decisions, note search, Markdown and JSON dispatcher reports |

## Validation

Run the ordinary suite without private data:

```bash
python -m pytest
```

After importing the starter CSVs, include the full-corpus contract test:

```bash
CIVICOPS_RUN_STARTER_SMOKE=1 python -m pytest tests/test_starter_compatibility.py
```

PowerShell equivalent:

```powershell
$env:CIVICOPS_RUN_STARTER_SMOKE = "1"
python -m pytest tests/test_starter_compatibility.py
```

## Data Boundaries

- Source descriptions remain metadata and are never presented as technician evidence.
- Search uses cleaned, employee-PII-redacted comments inside the authenticated operator boundary. External-model prompts apply an additional address-like location redaction.
- Work orders attached to more than ten assets are treated as inventory sweeps, matching the starter baseline.
- Known administrative assets and assets linked to at least 500 work orders are excluded as incident anchors.
- `appliesto` and explicit primary links outrank attached context; on mixed official rows without roles, equipment anchors the episode and locations remain context only.
- Shared context locations never merge work orders assigned to different primary equipment.
- Explicit administrative, training, and supply-order notes are retained for audit but do not enter incident generation.
- Recurrence requires at least three work orders in one semantically linked, 180-day-bounded episode.
- Starter-defined location entities remain available, but risk-register highlights prioritize physical equipment.
- Full-corpus incident, equipment, location, and review registers expose totals and offset pagination rather than silently truncating navigation.
- Numeric priority is retained but is not presented as calibrated failure severity.
- A generated recommendation always remains pending human authorization.
