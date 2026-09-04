from collections import Counter

from app.config import Settings, get_settings
from app.main import app
from app.models.database import InsightRow, ReviewRow
from sqlalchemy import select


def test_operational_endpoints(client) -> None:
    health = client.get("/api/v1/health")
    dashboard = client.get("/api/v1/dashboard")
    incidents = client.get("/api/v1/incidents")
    assets = client.get("/api/v1/assets")

    assert health.status_code == 200
    assert health.json()["status"] == "operational"
    assert health.json()["dataset_label"] == "Synthetic Demo Dataset"
    assert dashboard.json()["metrics"]["total_work_orders"] == 222
    assert incidents.status_code == assets.status_code == 200
    assert incidents.json() and assets.json()

    incident_id = incidents.json()[0]["incident_id"]
    asset_key = assets.json()[0]["asset_key"]
    assert client.get(f"/api/v1/incidents/{incident_id}").status_code == 200
    assert client.get(f"/api/v1/investigations/{incident_id}").status_code == 200
    assert client.get(f"/api/v1/assets/{asset_key}").status_code == 200


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
        ).json()
    }

    assert search_ids
    assert search_ids <= recurring_ids


def test_review_update_and_markdown_export(client) -> None:
    reviews = client.get("/api/v1/reviews").json()
    insight_id = reviews[0]["insight"]["insight_id"]
    response = client.patch(
        f"/api/v1/reviews/{insight_id}",
        json={
            "decision": "CONFIRMED",
            "reviewer_note": "Evidence verified in test.",
            "edited_recommendation": "Inspect the verified component.",
        },
    )
    client.patch(f"/api/v1/reviews/{insight_id}", json={"decision": "PENDING"})
    updated = next(
        item
        for item in client.get("/api/v1/reviews").json()
        if item["insight"]["insight_id"] == insight_id
    )
    report = client.get("/api/v1/reports/maintenance.md")

    assert response.status_code == 200
    assert response.json()["decision"] == "CONFIRMED"
    assert updated["edited_recommendation"] == "Inspect the verified component."
    assert report.status_code == 200
    assert report.headers["content-type"].startswith("text/markdown")
    assert "Evidence-Based Findings" in report.text


def test_api_returns_redacted_evidence_and_unknown_search_is_empty(client) -> None:
    incidents = client.get("/api/v1/incidents").json()
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


def test_rejected_finding_is_non_actionable_across_outputs(client, repository) -> None:
    before_dashboard = client.get("/api/v1/dashboard").json()
    incidents = client.get("/api/v1/incidents").json()
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
    active_incidents = client.get("/api/v1/incidents").json()
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
