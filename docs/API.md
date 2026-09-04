# API Guide

The base path is `/api/v1`. FastAPI also serves interactive OpenAPI documentation at `/docs`.

Operational datasets require `X-CivicOps-Key` on every endpoint except health. The configured value comes from `CIVICOPS_OPERATOR_API_KEY`. API-triggered pipeline runs require this header even in demo mode.

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/health` | Service, database, and demo status |
| `GET` | `/dashboard` | Metrics, trends, risk register, and patterns |
| `GET` | `/incidents` | Filtered incident register |
| `GET` | `/incidents/{incident_id}` | Incident insight and work-order evidence |
| `GET` | `/investigations/{incident_id}` | Investigation alias for incident detail |
| `GET` | `/assets` | Assets ordered by risk |
| `GET` | `/assets/{asset_key}` | Asset timeline and linked intelligence |
| `GET` | `/reviews` | Human review records, low confidence first |
| `PATCH` | `/reviews/{insight_id}` | Persist decision, edits, and reviewer note |
| `GET` | `/search?q=...` | Parsed filters plus semantic and keyword matches |
| `GET` | `/taxonomy/phrases` | Frequent cleaned-comment phrases |
| `GET` | `/reports/maintenance.md` | Grounded Markdown briefing |
| `POST` | `/pipeline/run` | Rebuild from `demo` or `raw` source |

## Incident Filters

`GET /incidents` accepts `start_date`, `end_date`, `issue_family`, `department`, `asset`, `confidence`, and `recurring_only`. Dates use `YYYY-MM-DD`; interval filtering includes incidents that overlap the requested range. Other values are exact matches except for case.

## Review Update

```json
{
  "decision": "CONFIRMED",
  "edited_issue_family": null,
  "edited_recommendation": null,
  "reviewer_note": "Verified against the cited technician notes."
}
```

`decision` must be `CONFIRMED`, `REJECTED`, or `PENDING`. Reviewer notes are limited to 2,000 characters.

## Search Examples

```text
recurring sewer backups
low pressure in 2023
assets with more than 2 water leaks
pavement damage
```

Search identifies known issue phrases, a four-digit year, `more than N`, and the `recurring` qualifier. It also returns bounded TF-IDF nearest work orders with semantic scores.

## Pipeline Run

```json
{
  "source": "demo",
  "use_semantic_model": false
}
```

The semantic option requires the `backend[ml]` dependencies and may download a model. The default is deterministic and offline.
