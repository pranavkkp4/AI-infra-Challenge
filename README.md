# CivicOps AI

Explainable infrastructure maintenance intelligence for municipal operations teams. CivicOps turns work-order history into bounded incident episodes, auditable confidence and asset-risk scores, evidence-linked preventive actions, and a human review queue.

This submission extends CU Denver's official
[`ai4infraChallengeStudentStarterPack1`](https://github.com/cudenver-ai/ai4infraChallengeStudentStarterPack1).
The supplied brief, output-cleared notebook, requirements, and procedure references remain in this
repository; [`docs/STARTER_TEMPLATE.md`](docs/STARTER_TEMPLATE.md) maps them to the production app.

![CivicOps executive dashboard](docs/screenshots/dashboard-desktop.png)

> The repository does not contain raw Cityworks CSVs. The bundled container demo runs on the safe synthetic fixture. The captures were also validated against a separately imported, Git-ignored official dataset and show derived operational identifiers with redacted notes. Findings are decision support, not work authorization, measured field outcomes, or production performance claims.

## Demo Walkthrough

[![CivicOps AI walkthrough scenes](docs/demo/civicops-ai-walkthrough-preview.jpg)](docs/demo/civicops-ai-walkthrough-final.mp4)

[Watch the full product walkthrough](docs/demo/civicops-ai-walkthrough-final.mp4). It demonstrates all six operating views, recurring-incident filtering, typed asset selection, evidence-grounded investigation, an authenticated review decision, redacted-note search, and Markdown/JSON report export. The bundled container path uses the synthetic fixture; official-data captures require the separate import described below.

## What It Does

- Normalizes `WORKORDER.csv`, `WOENTITY.csv`, and `WOCOMMENT.csv` without inflating job counts through many-to-many joins.
- Reads the starter root or `data/` directory directly, using projected official Cityworks columns at full source scale.
- Preserves asset identity as `EntityType:EntityUid`.
- Separates `appliesto`/primary equipment from attached location context and never merges different primary assets through a shared location.
- Isolates inventory sweeps, high-degree administrative catch-alls, and explicit non-maintenance notes before incident analysis.
- Retains raw comments while producing ordered, dispatcher-cleaned, employee-PII-redacted operator evidence and separately removes address-like locations before external model calls.
- Generates bounded asset, issue, and time-blocked candidates with vectorized TF-IDF similarity scoring; optional sentence-transformer and FAISS support remains available.
- Retrieves corpus-mined municipal trigger meanings, recording the matched exemplar and score instead of forcing below-threshold labels.
- Groups weighted edges into same-primary-asset, compatible-family incidents while enforcing a maximum full-episode span; recurrence requires at least three jobs supporting the selected family.
- Separates observations, interpretations, possible causes, and recommended actions through a configurable Agent Logic Package (ALP).
- Rejects any insight that cites a work order outside its retrieved evidence set.
- Routes findings below a policy threshold into persisted human review.
- Provides six responsive operating views, paged full-corpus registers, equipment/location selectors, redacted-note search, and Markdown plus structured JSON briefing exports.

## Quick Start

### Docker

```bash
docker compose up --build
```

Open `http://localhost:3000`. The API and interactive OpenAPI schema are available at `http://localhost:8000/api/v1/health` and `http://localhost:8000/docs`.

### Local Development

Requires Python 3.12-3.14 and Node.js 20 or newer.

```bash
python -m pip install -e "backend[dev]"
npm --prefix frontend install
python scripts/generate_demo_data.py
python scripts/run_pipeline.py
uvicorn app.main:app --app-dir backend --reload
```

In a second terminal:

```bash
npm --prefix frontend run dev
```

Open `http://localhost:5173`. Vite proxies `/api` to the service on port 8000.

## Verification

```bash
make test
make lint
make build
```

Equivalent commands on systems without Make:

```bash
python -m pytest tests
ruff check backend/app scripts tests
ruff format --check backend/app scripts tests
npm --prefix frontend run typecheck
npm --prefix frontend test
npm --prefix frontend run build
docker compose build
```

With the official CSVs imported, run the full starter contract test:

```powershell
$env:CIVICOPS_RUN_STARTER_SMOKE = "1"
python -m pytest tests/test_starter_compatibility.py
```

## Operations UI

1. **Executive**: system posture, incident cadence, issue mix, risk register, and cited pattern ledger.
2. **Incident Explorer**: server-filtered, paged incident table with risk, evidence window, confidence, recurrence, and resolution state.
3. **Asset Intelligence**: separate paged equipment and location registers with risk reasons, maintenance chronology, and linked incident intelligence.
4. **AI Investigation**: separate observed, interpreted, and recommended lanes; technician evidence; grouping reasons; confidence decomposition; grounding status.
5. **Review Queue**: paged pending, confirmed, rejected, and complete views for evidence hold or recorded decisions with reviewer notes.
6. **Reports + Search**: report readiness, emergent comment taxonomy, redacted-note retrieval, linked results, and Markdown/JSON downloads.

Additional captures are in [`docs/screenshots`](docs/screenshots).

## Data Input

Clone the official starter and import its archive into the ignored raw-data directory:

```bash
git clone https://github.com/cudenver-ai/ai4infraChallengeStudentStarterPack1.git ../ai4infra-starter
python scripts/import_starter_data.py --starter ../ai4infra-starter
```

The importer validates required headers and at least one data row before atomically replacing the resulting local files:

```text
data/raw/WORKORDER.csv
data/raw/WOENTITY.csv
data/raw/WOCOMMENT.csv
```

Then run:

```bash
python scripts/run_pipeline.py --source data/raw
```

Operational data fails closed. Set these values in `.env` before starting the API or UI:

```text
CIVICOPS_DEMO_MODE=false
CIVICOPS_OPERATOR_API_KEY=replace-with-a-long-random-secret
```

The UI prompts for the operator key and keeps it in browser session storage only. A production deployment should terminate authenticated access at an organizational gateway and inject `X-CivicOps-Key` upstream rather than distribute a shared key broadly.

The pipeline also accepts the starter repository path directly. Exact official fields including `InitiateDate`, `Shop`, `AssetGroup`, `WOAddress`, `Location`, `IsReactive`, `Comments`, and `DateCreated` are normalized. Missing required columns fail loudly; invalid dates, duplicate identifiers, bulk attachments, and catch-all exclusions are counted in the result.

`data/raw/**` is ignored except for `.gitkeep`. Do not commit private municipal records.

## Explainability Contract

Every generated finding contains:

- Exact supporting and contradicting `WorkOrderId` values.
- Claim-level evidence mappings that tie each conclusion to supplied `WorkOrderId` values.
- Measured observations distinct from rule-derived interpretation.
- A possible cause support level: `SUPPORTED`, `LIKELY`, `POSSIBLE`, or `UNKNOWN`.
- A versioned confidence score with component values, raw score, calibration provenance, and conflict penalty.
- A recommended action that is explicitly not an authorization.

Direct cause language is only marked `SUPPORTED` when a technician note contains cause evidence. Otherwise the ALP uses cautious language or states that evidence is insufficient.

See [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) for formulas and data flow.

## Audit and Calibration

Stop the API before using the local audit CLI because DuckDB permits only one process to own a writable database file.

```bash
python scripts/sample_audit.py --size 50 --seed 42
```

Review `data/audit_sample.csv`, label each reasoning component, and set `actual_correct` to `1` only when every component passes. Then run:

```bash
python scripts/evaluate_audit.py
```

The evaluator requires at least 50 completed labels and emits Brier score, calibration bins, threshold precision/coverage/review-load analysis, and a versioned `calibration.json` artifact. Outputs are written to `data/calibration/metrics.json`, `data/calibration/calibration.json`, and `data/calibration/calibration.png`. They are intentionally ignored because they represent evaluator-specific results. The bundled demo uses the checked-in synthetic contract artifact at `backend/app/evaluation/demo_calibration.json`; official data requires an explicitly supplied labeled artifact. Details are in [`docs/EVALUATION.md`](docs/EVALUATION.md).

## Configuration

Copy `.env.example` to `.env` if defaults need to change. Settings use the `CIVICOPS_` prefix.

| Variable | Default | Purpose |
| --- | --- | --- |
| `CIVICOPS_DATABASE_URL` | `duckdb:///./data/civicops.duckdb` | SQLAlchemy database URL |
| `CIVICOPS_DATA_DIR` | `./data` | Source data root |
| `CIVICOPS_DEMO_MODE` | `true` | Honest demo labeling |
| `CIVICOPS_EMBEDDING_MODEL` | `all-MiniLM-L6-v2` | Optional semantic model |
| `CIVICOPS_CONFIDENCE_REVIEW_THRESHOLD` | `0.72` | Review routing threshold |
| `CIVICOPS_LLM_PROVIDER` | `deterministic` | Provider selection for structured synthesis |
| `CIVICOPS_CALIBRATION_ENABLED` | `false` | Enable calibration; operational data always requires an explicit artifact, while demo mode loads its checked-in artifact |
| `CIVICOPS_CALIBRATION_ARTIFACT_PATH` | unset | Path to a labeled-audit calibration artifact |
| `CIVICOPS_CALIBRATION_DATASET_ID` | unset | Dataset identity bound to an operational calibration artifact |
| `CIVICOPS_OPERATOR_API_KEY` | unset | Required for operational data and API pipeline runs |
| `VITE_API_URL` | `/api/v1` locally | Browser API base URL |

OpenAI, Anthropic, and Ollama adapters exist behind the provider abstraction. The default pipeline executes the same retrieval, prompt, schema, and grounding contract through a deterministic offline provider; external providers are optional and need credentials. External prompts keep only typed asset keys needed by the structured contract, redact employee PII and address-like locations in notes, and fail closed when a known identifier pattern remains. External synthesis must pass Pydantic validation and citation grounding before persistence.

## Repository Layout

```text
backend/app/          FastAPI, ETL, retrieval, ALP, scoring, persistence
frontend/src/         React control-room application
scripts/              Demo generation, pipeline, audit, calibration
tests/                Backend unit and integration tests
data/demo/            Seeded synthetic source tables
data/raw/             Ignored private input location
docs/                 Architecture, evaluation, API, screenshots
aisa_challenge.ipynb  Output-cleared official starter notebook
challenge.md          Official challenge brief
pdfs/                 Official procedure references
data/demo/manifest.json  Synthetic scenario and dataset provenance manifest
```

## Scope Boundaries

- The 72% review threshold is an explicit demo policy. Replace it after manual audit and held-out calibration.
- The bundled demo applies a synthetic contract calibration artifact fitted from 50 traceable fixture labels; it does not measure official-data accuracy or human maintenance correctness.
- Risk is a transparent prioritization score, not a failure probability.
- Resolution is reported only from direct note signals; missing evidence remains `UNKNOWN`.
- Attached entities remain context only when primary equipment is present; they never merge different equipment histories and UID is never used without EntityType.
- Canonical snapshot replacement is transactional; review writes and pipeline replacement are serialized in-process.
- The deterministic pipeline is batch-first. Multi-process writes and larger deployments should move to PostgreSQL.
- Markdown and versioned JSON `PM_INSIGHT_REPORT` exports are implemented; PDF export is outside the MVP.
