from collections import Counter

from app.config import Settings, get_settings
from app.main import app
from app.models.database import InsightRow, PipelineRunRow, ReviewRow
from sqlalchemy import select


def test_operational_endpoints(client) -> None:
    health = client.get("/api/v1/health")
    dashboard = client.get("/api/v1/dashboard")
    incidents_response = client.get("/api/v1/incidents")
    assets_response = client.get("/api/v1/assets")

    assert health.status_code == 200
    assert health.json()["status"] == "operational"
    assert health.json()["dataset_label"] == "Synthetic Demo Dataset"
    assert dashboard.json()["metrics"]["total_work_orders"] == 222
    assert incidents_response.status_code == assets_response.status_code == 200
    incidents = incidents_response.json()
    assets = assets_response.json()
    assert incidents["items"] and assets["items"]
    assert incidents["total"] >= len(incidents["items"])
    assert assets["total"] >= len(assets["items"])

    incident_id = incidents["items"][0]["incident_id"]
    asset_key = assets["items"][0]["asset_key"]
    assert client.get(f"/api/v1/incidents/{incident_id}").status_code == 200
    assert client.get(f"/api/v1/investigations/{incident_id}").status_code == 200
    assert client.get(f"/api/v1/assets/{asset_key}").status_code == 200


def test_registers_are_pageable_and_asset_classes_are_filterable(client) -> None:
    first = client.get("/api/v1/incidents", params={"limit": 1}).json()
    second = client.get("/api/v1/incidents", params={"limit": 1, "offset": 1}).json()
    equipment = client.get(
        "/api/v1/assets", params={"limit": 10, "asset_class": "equipment"}
    ).json()
    locations = client.get(
        "/api/v1/assets", params={"limit": 10, "asset_class": "location"}
    ).json()
    pending = client.get(
        "/api/v1/reviews", params={"limit": 10, "decision": "PENDING"}
    ).json()
    next_pending = client.get(
        "/api/v1/reviews", params={"limit": 1, "offset": 1, "decision": "PENDING"}
    ).json()

    assert first["total"] == second["total"]
    assert first["items"][0]["incident_id"] != second["items"][0]["incident_id"]
    assert all(item["asset_class"] == "equipment" for item in equipment["items"])
    assert all(item["asset_class"] == "location" for item in locations["items"])
    assert all(item["decision"] == "PENDING" for item in pending["items"])
    assert next_pending["total"] == pending["total"]
    assert next_pending["items"][0]["review_id"] != pending["items"][0]["review_id"]


def test_search_recurring_filter_matches_incident_filter(client) -> None:
    search_ids = {
        item["incident_id"]
        for item in client.get(
            "/api/v1/search", params={"q": "recurring issues"}
        ).json()["incidents"]
    }
    recurring_ids = {
        item["incident_id"]
        for item in client.get(
            "/api/v1/incidents", params={"recurring_only": "true"}
        ).json()["items"]
    }

    assert search_ids <= recurring_ids
    sewer_search = client.get(
        "/api/v1/search", params={"q": "recurring sewer backups"}
    ).json()
    assert sewer_search["interpreted_filters"]["issue_family"] == "sewer_backup"
    assert all(
        item["issue_family"] == "sewer_backup" for item in sewer_search["incidents"]
    )
    electrical_search = client.get(
        "/api/v1/search", params={"q": "recurring streetlights out"}
    ).json()
    assert (
        electrical_search["interpreted_filters"]["issue_family"] == "electrical_issue"
    )
    assert all(
        item["issue_family"] == "electrical_issue"
        for item in electrical_search["incidents"]
    )


def test_review_update_and_report_exports(client) -> None:
    reviews = client.get("/api/v1/reviews").json()["items"]
    insight_id = reviews[0]["insight"]["insight_id"]
    response = client.patch(
        f"/api/v1/reviews/{insight_id}",
        json={
            "decision": "CONFIRMED",
            "reviewer_note": "Evidence verified by Moore, Cynthia: in test.",
            "edited_issue_family": "pothole",
            "edited_recommendation": "Inspect the verified component.",
        },
    )
    updated = next(
        item
        for item in client.get("/api/v1/reviews").json()["items"]
        if item["insight"]["insight_id"] == insight_id
    )
    report = client.get("/api/v1/reports/maintenance.md")
    structured_report = client.get("/api/v1/reports/maintenance.json")

    assert response.status_code == 200
    assert response.json()["decision"] == "CONFIRMED"
    assert updated["edited_recommendation"] == "Inspect the verified component."
    assert "Moore, Cynthia" not in updated["reviewer_note"]
    assert updated["insight"]["issue_family"] == "pothole"
    assert updated["insight"]["title"].startswith("Pothole recurrence")
    assert "Human review assigned" in updated["insight"]["summary"]
    assert updated["insight"]["possible_cause"]["support_level"] == "UNKNOWN"
    assert updated["insight"]["recommended_action"] == "Inspect the verified component."
    assert report.status_code == 200
    assert report.headers["content-type"].startswith("text/markdown")
    assert "Evidence-Based Findings" in report.text
    assert structured_report.status_code == 200
    payload = structured_report.json()
    assert payload["REPORT_TYPE"] == "PM_INSIGHT_REPORT"
    assert payload["TOTAL_FINDINGS"] >= payload["EXPORTED_FINDINGS"]
    assert payload["FINDINGS"][0]["SUPPORTING_WORK_ORDERS"]
    assert isinstance(payload["FINDINGS"][0]["CAUSAL_FACTOR"], str)
    assert "REVIEW_DECISION" in payload["FINDINGS"][0]
    assert payload["FINDINGS"][0]["DISPATCH_STATUS"] == ("PENDING_HUMAN_AUTHORIZATION")
    restored = client.patch(
        f"/api/v1/reviews/{insight_id}",
        json={
            "decision": "PENDING",
            "reviewer_note": None,
            "edited_issue_family": None,
            "edited_recommendation": None,
        },
    )
    assert restored.status_code == 200


def test_api_returns_redacted_evidence_and_unknown_search_is_empty(client) -> None:
    incidents = client.get("/api/v1/incidents").json()["items"]
    detail = client.get(f"/api/v1/incidents/{incidents[0]['incident_id']}").json()
    comments = [
        comment for order in detail["work_orders"] for comment in order["comments"]
    ]
    search = client.get("/api/v1/search", params={"q": "xyzzy"}).json()

    assert all(
        "raw_text" not in comment and "clean_text" not in comment
        for comment in comments
    )
    assert all("Jordan Rivera" not in comment["redacted_text"] for comment in comments)
    assert search["incidents"] == []
    assert search["assets"] == []
    note_search = client.get("/api/v1/search", params={"q": "Jordan Rivera"}).json()
    assert all(
        "Jordan Rivera" not in item["evidence_excerpt"]
        for item in note_search["work_orders"]
    )


def test_incident_date_filters_and_non_demo_authentication(client) -> None:
    response = client.get(
        "/api/v1/incidents",
        params={"start_date": "2025-01-01", "end_date": "2024-01-01"},
    )
    assert response.status_code == 422
    assert (
        client.post(
            "/api/v1/pipeline/run", json={"source": "demo", "use_semantic_model": False}
        ).status_code
        == 503
    )
    app.dependency_overrides[get_settings] = lambda: Settings(
        demo_mode=False, operator_api_key="test-secret"
    )

    assert client.get("/api/v1/dashboard").status_code == 401
    assert (
        client.get(
            "/api/v1/dashboard", headers={"X-CivicOps-Key": "test-secret"}
        ).status_code
        == 200
    )


def test_operational_provenance_cannot_bypass_data_access(client, repository) -> None:
    with repository.session() as session:
        latest_run = session.scalar(
            select(PipelineRunRow).order_by(PipelineRunRow.completed_at.desc()).limit(1)
        )
        original_source = latest_run.source
        latest_run.source = "C:/private/demo"
    app.dependency_overrides[get_settings] = lambda: Settings(
        demo_mode=True, operator_api_key="test-secret"
    )

    assert client.get("/api/v1/dashboard").status_code == 401
    assert (
        client.get(
            "/api/v1/dashboard", headers={"X-CivicOps-Key": "test-secret"}
        ).status_code
        == 200
    )
    assert client.get("/api/v1/health").json()["demo_mode"] is False
    health = client.get("/api/v1/health").json()
    assert health["requires_operator_key"] is True
    assert health["calibration"]["applied"] is False

    with repository.session() as session:
        latest_run = session.scalar(
            select(PipelineRunRow).order_by(PipelineRunRow.completed_at.desc()).limit(1)
        )
        latest_run.source = original_source


def test_rejected_finding_is_non_actionable_across_outputs(client, repository) -> None:
    before_dashboard = client.get("/api/v1/dashboard").json()
    incidents = client.get("/api/v1/incidents").json()["items"]
    asset_counts = Counter(item["asset_key"] for item in incidents)
    target = next(item for item in incidents if asset_counts[item["asset_key"]] > 1)
    before_asset = client.get(f"/api/v1/assets/{target['asset_key']}").json()
    before_detail = client.get(f"/api/v1/incidents/{target['incident_id']}").json()
    with repository.session() as session:
        insight = session.scalar(
            select(InsightRow).where(InsightRow.incident_id == target["incident_id"])
        )
        review = session.scalar(
            select(ReviewRow).where(ReviewRow.insight_id == insight.insight_id)
        )
        if not review:
            session.add(
                ReviewRow(review_id="REV-REJECTION-TEST", insight_id=insight.insight_id)
            )
    response = client.patch(
        f"/api/v1/reviews/{insight.insight_id}", json={"decision": "REJECTED"}
    )
    detail = client.get(f"/api/v1/incidents/{target['incident_id']}").json()
    asset = client.get(f"/api/v1/assets/{target['asset_key']}").json()
    dashboard = client.get("/api/v1/dashboard").json()
    active_incidents = client.get("/api/v1/incidents").json()["items"]
    search = client.get(
        "/api/v1/search", params={"q": target["issue_family"].replace("_", " ")}
    ).json()
    report = client.get("/api/v1/reports/maintenance.md")

    assert response.status_code == 200
    assert detail["insight"]["review_decision"] == "REJECTED"
    assert target["incident_id"] not in {
        item["incident_id"] for item in active_incidents
    }
    assert target["incident_id"] not in {
        item["incident_id"] for item in asset["incidents"]
    }
    assert asset["asset"]["risk_score"] <= before_asset["asset"]["risk_score"]
    assert dashboard["metrics"]["recurring_incidents"] == (
        before_dashboard["metrics"]["recurring_incidents"] - int(target["recurring"])
    )
    remaining = [
        item for item in active_incidents if item["asset_key"] == target["asset_key"]
    ]
    assert remaining
    assert all(item["risk_score"] == asset["asset"]["risk_score"] for item in remaining)
    assert target["incident_id"] not in {
        item["incident_id"] for item in search["incidents"]
    }
    assert before_detail["insight"]["title"] not in report.text
