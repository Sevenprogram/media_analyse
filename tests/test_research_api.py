from fastapi.testclient import TestClient

from api.main import app


def test_research_health_route():
    client = TestClient(app)
    response = client.get("/api/research/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "module": "research"}


def test_research_job_validation_runs_before_persistence():
    client = TestClient(app)
    response = client.post(
        "/api/research/jobs",
        json={
            "name": "Bad platform",
            "topic": "topic",
            "platforms": ["bili"],
            "keywords": ["topic"],
            "start_date": "2026-01-01",
            "end_date": "2026-01-31",
            "comment_policy": {"enable_comments": True},
        },
    )

    assert response.status_code == 422


def test_research_chart_kinds_route():
    client = TestClient(app)
    response = client.get("/api/research/charts/kinds")

    assert response.status_code == 200
    assert "platform_counts" in response.json()["kinds"]
    assert "sentiment_distribution" in response.json()["kinds"]
