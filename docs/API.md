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
| `GET` | `/assets` | Paged assets ordered by risk, optionally filtered by class |
| `GET` | `/assets/{asset_key}` | Asset timeline and linked intelligence |
| `GET` | `/reviews` | Paged human review records, low confidence first |
| `PATCH` | `/reviews/{insight_id}` | Persist decision, edits, and reviewer note |
| `GET` | `/search?q=...` | Parsed filters plus semantic and keyword matches |
| `GET` | `/taxonomy/phrases` | Frequent cleaned-comment phrases |
| `GET` | `/reports/maintenance.md` | Grounded Markdown briefing |
| `GET` | `/reports/maintenance.json` | Versioned structured `PM_INSIGHT_REPORT` |
| `POST` | `/pipeline/run` | Rebuild from `demo` or `raw` source |

## Incident Filters

`GET /incidents` accepts `start_date`, `end_date`, `issue_family`, `department`, `asset`, `confidence`, `recurring_only`, `limit`, and `offset`. Dates use `YYYY-MM-DD`; interval filtering includes incidents that overlap the requested range. Other values are exact matches except for case.

Incident, asset, and review registers return `{ items, total, limit, offset }` so every full-corpus record remains reachable. The default page contains 500 records and the maximum `limit` is 1,000. `/assets` also accepts `asset_class=equipment|location`; `/reviews` accepts `decision=PENDING|CONFIRMED|REJECTED` and an exact `insight_id`. Incident pages additionally include stable issue-family and department facets. A recurring incident contains at least three linked work orders.

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

Search identifies known issue phrases, a four-digit year, `more than N`, and the `recurring` qualifier. It also returns bounded TF-IDF nearest work orders using only cleaned, employee-PII-redacted source notes inside the authenticated operator boundary. Those results may retain operational site identifiers and must pass the additional external-model redaction boundary before leaving the service.

Search uses `GET` for a compact demo interface. Operators must not enter private names, addresses, or other sensitive values because query strings can be retained by browser, proxy, or access logs; a production deployment should use a body-based search endpoint with log filtering.

The structured report is schema version `2.0`. It returns every active finding by default, with `TOTAL_FINDINGS`, `EXPORTED_FINDINGS`, and `TRUNCATED` making completeness explicit. Optional `limit` and `offset` query parameters provide a bounded page for downstream consumers. `CAUSAL_FACTOR` is a string; PM interval evidence, field-level citations, provenance, department, evidence window, recurrence, resolution, risk, review state, and human-override status are explicit fields.

## Pipeline Run

```json
{
  "source": "demo",
  "use_semantic_model": false
}
```

The semantic option requires the `backend[ml]` dependencies and may download a model. The default is deterministic and offline.
