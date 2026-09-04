# CivicOps AI Implementation Plan

## Objective

Deliver an end-to-end infrastructure intelligence MVP that converts municipal work-order history into explainable incident episodes, transparent asset risk, reviewable preventive-maintenance insights, and grounded reports. The system runs without a paid LLM and never treats generated interpretation as source evidence.

## Challenge Requirements Captured

The normal-track instructions in `AI4Infra Presentation.pdf` emphasize sequence-level reasoning, candidate incident grouping, an explicit Agent Logic Package (ALP), calibrated confidence, dispatcher-ready output, and a grounded `PM_INSIGHT_REPORT`. The judging rubric weights ALP logic depth (30), architecture (30), explainability (20), normalization (10), and operational impact (10).

Hard data rules:

- `WORKORDER` is one job; joined entity rows are never counted as jobs.
- Job statistics are deduplicated on `WorkOrderId`.
- Asset identity is `EntityType + ":" + EntityUid`; `EntityUid` alone is invalid.
- `ApplyToEntity` is not assumed to identify the actual asset.
- Descriptions aid retrieval/classification but are not displayed as factual technician evidence.
- Raw comments are retained; cleaning and PII redaction create separate derivatives.
- Invalid dates, null identifiers, boilerplate, and non-maintenance notes are filtered or flagged.
- Retrieval is bounded candidate search, not an O(n^2) similarity matrix.
- Every displayed conclusion cites exact retrieved `WorkOrderId` values.
- Confidence is deterministic and auditable; low-confidence results enter human review.
- Raw challenge data is private and excluded from version control.

## Architecture Decisions

1. **Monorepo**: React/Vite client and FastAPI service are independently containerized.
2. **Persistence boundary**: application services depend on a repository protocol. The local adapter uses SQLAlchemy with DuckDB; PostgreSQL can replace the engine and adapter without changing analytics contracts.
3. **Batch-first intelligence**: ETL, grouping, ALP, confidence, and risk run deterministically. Generative synthesis is optional and downstream.
4. **Embedding strategy**: `all-MiniLM-L6-v2` with normalized vectors and FAISS inner-product search. A TF-IDF fallback keeps demo/test operation lightweight and offline.
5. **Candidate blocking**: same asset, co-attached/related asset, issue family, and temporal window, capped at 12 forward neighbors per block. Only blocked pairs are scored in a vectorized pass, and grouping requires a shared or related asset.
6. **Grouping**: configurable weighted edges are connected with union-find. Edge explanations are persisted for investigation views.
7. **ALP**: YAML rules map measured observations to cautious interpretations and actions. Cause support is `SUPPORTED`, `LIKELY`, `POSSIBLE`, or `UNKNOWN` and direct-cause claims require note evidence.
8. **Grounding gate**: Pydantic output is rejected if any cited work order is outside the retrieved evidence set.
9. **Human feedback**: review decisions are persisted independently from immutable generated insight evidence.
10. **Demo honesty**: generated metrics and UI are labeled `Synthetic Demo Dataset`; no performance claims are made before audit.

## Data Flow

```text
CSV input -> schema mapping -> validation -> canonical normalization
  -> raw + clean + redacted comments -> taxonomy/features/embeddings
  -> blocked candidate retrieval -> weighted incident graph
  -> temporal observations -> ALP interpretation/action
  -> confidence + risk -> grounding gate -> persisted insight
  -> dashboard/search/assets/investigation/review/report APIs
```

## Canonical Database Schema

- `work_orders`: `work_order_id` PK, date, category, department, description, status, priority, issue family, resolution signal, metadata JSON.
- `assets`: `asset_key` PK, entity type, entity UID, department, risk score, risk reasons JSON.
- `work_order_assets`: composite PK (`work_order_id`, `asset_key`), relationship type.
- `comments`: `comment_id` PK, work order FK, timestamp, raw text, clean text, redacted text, redaction flag, meaningful flag, source type.
- `incidents`: incident ID PK, primary asset, issue family, first/last seen, recurring flag, resolution status, confidence, confidence level, review flag, risk score.
- `incident_work_orders`: composite PK (`incident_id`, `work_order_id`), sequence and retrieval explanation JSON.
- `insights`: insight ID PK, incident ID, structured observation/interpretation/action/cause, confidence components JSON, supporting and contradicting IDs JSON.
- `reviews`: review ID PK, logical insight ID, decision, edits, reviewer note, timestamp. The logical reference permits audit preservation when regenerated grouping changes.
- `pipeline_runs`: run ID PK, source, status, validation counts JSON, timestamps.

## API Surface

- `GET /api/v1/health`
- `GET /api/v1/dashboard`
- `GET /api/v1/incidents` with date, issue, confidence, department, asset, and recurrence filters
- `GET /api/v1/incidents/{incident_id}`
- `GET /api/v1/assets`
- `GET /api/v1/assets/{asset_key}`
- `GET /api/v1/investigations/{incident_id}`
- `GET /api/v1/reviews`
- `PATCH /api/v1/reviews/{insight_id}`
- `GET /api/v1/search` for hybrid keyword/semantic/metadata retrieval
- `GET /api/v1/reports/maintenance.md`
- `GET /api/v1/taxonomy/phrases`
- `POST /api/v1/pipeline/run`

## Milestones

### Milestone 1: Foundation and Data

- Repository structure, Python/TypeScript tooling, configuration, SQLAlchemy models.
- Seeded synthetic source tables with known recurring episodes and PII examples.
- Polars loader, validation, normalization, cleaning, redaction, and temporal features.

### Milestone 2: Intelligence Pipeline

- Configurable taxonomy and corpus phrase mining.
- Embeddings/FAISS and bounded retrieval explanations.
- Weighted incident grouping and temporal episode features.
- ALP rules, confidence engine, asset risk, grounding enforcement, optional LLM providers.

### Milestone 3: Product API

- Dashboard, explorer, asset, investigation, review, search, taxonomy, and Markdown report endpoints.
- Startup bootstrap for a zero-key synthetic demo.

### Milestone 4: Operations UI

- Responsive control-room shell.
- Executive Dashboard, Incident Explorer, Asset Intelligence, AI Investigation, Human Review Queue, and Reports.
- Loading, empty, and failure states; Markdown download.

### Milestone 5: Evaluation and Delivery

- Unit/integration tests including strict citation containment.
- 50-row audit sampler, evaluator, Brier score, calibration plot.
- Docker Compose, Make targets, pre-commit, documentation, browser screenshots, and end-to-end verification.

## Testing Strategy

- **Unit**: asset key, date validation, text cleaning, PII, issue taxonomy, temporal features, edge score, grouping, ALP, confidence, risk, grounding.
- **Integration**: synthetic CSV ingestion to canonical tables; API response schemas; review persistence; Markdown citations.
- **Invariant/property checks**: unique work-order counts survive many-to-many joins; no unsupported citations; scores remain in range; no candidate self-pairs.
- **Frontend**: strict TypeScript compilation and production Vite build.
- **System**: start services, health check, exercise all six routes, verify browser console and responsive screenshots.

## Data Access Decision

The presentation contains challenge data counts and directs participants to event materials/Discord, but does not contain downloadable CSV payloads or a stable direct dataset URL. The repository therefore ships a realistic generator and synthetic demo CSVs. Authorized challenge files can be placed in `data/raw/` using the documented filenames and ingested with the same pipeline; that directory is ignored by Git.

## Known Scope Boundaries

- The default threshold is explicitly an uncalibrated demo policy until reviewer labels are collected.
- Resolution rate is reported only when a direct resolution signal exists.
- Related assets are inferred only from work-order co-attachment, never from matching UID alone.
- PDF export is deferred; Markdown export is complete and printable.
