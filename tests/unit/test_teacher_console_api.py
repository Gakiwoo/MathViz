from __future__ import annotations

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient

from math_to_manim.app.api import _should_use_deterministic_generation, create_app


def test_config_endpoints_save_and_mask_key(tmp_path) -> None:
    app = create_app(config_path=tmp_path / ".env.m2m2", runs_dir=tmp_path / "runs")
    client = TestClient(app)

    response = client.post(
        "/api/config",
        json={
            "provider_id": "deepseek",
            "base_url": "https://api.deepseek.com",
            "model": "deepseek-v4-flash",
            "api_key": "sk-abcdef123456",
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["current"]["has_api_key"] is True
    assert "sk-abcdef123456" not in str(data)


def test_generate_endpoint_creates_deterministic_no_render_run(tmp_path) -> None:
    app = create_app(config_path=tmp_path / ".env.m2m2", runs_dir=tmp_path / "runs")
    client = TestClient(app)

    response = client.post(
        "/api/generate",
        json={
            "prompt": "Explain why derivatives are slopes",
            "audience_level": "high_school",
            "desired_duration": 45,
            "style": "clean classroom",
            "deterministic": True,
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["prompt"] == "Explain why derivatives are slopes"
    assert data["status"]["validation"] == "passed"
    assert data["status"]["render"] in ("failed", "skipped")
    assert (tmp_path / "runs" / data["run_id"] / "manifest.json").exists()


def test_teacher_console_defaults_to_fast_local_generation() -> None:
    assert _should_use_deterministic_generation({}, has_api_key=True) is True
    assert _should_use_deterministic_generation({"use_ai": False}, has_api_key=True) is True
    assert _should_use_deterministic_generation({"use_ai": True}, has_api_key=True) is False
    assert _should_use_deterministic_generation({"use_ai": True}, has_api_key=False) is True
    assert _should_use_deterministic_generation({"deterministic": True}, has_api_key=True) is True


def test_render_health_endpoint_returns_tool_status(tmp_path) -> None:
    app = create_app(config_path=tmp_path / ".env.m2m2", runs_dir=tmp_path / "runs")
    client = TestClient(app)

    response = client.get("/api/health/render")

    assert response.status_code == 200
    data = response.json()
    assert "manim" in data["tools"]
    assert "install_commands" in data


def test_favicon_endpoint_avoids_browser_console_404(tmp_path) -> None:
    app = create_app(config_path=tmp_path / ".env.m2m2", runs_dir=tmp_path / "runs")
    client = TestClient(app)

    response = client.get("/favicon.ico")

    assert response.status_code in {200, 204}


def test_index_endpoint_returns_200(tmp_path) -> None:
    app = create_app(config_path=tmp_path / ".env.m2m2", runs_dir=tmp_path / "runs")
    client = TestClient(app)

    response = client.get("/")

    assert response.status_code == 200


def test_get_config_endpoint_returns_config(tmp_path) -> None:
    app = create_app(config_path=tmp_path / ".env.m2m2", runs_dir=tmp_path / "runs")
    client = TestClient(app)

    response = client.get("/api/config")

    assert response.status_code == 200
    data = response.json()
    assert "current" in data


def test_get_runs_returns_empty_when_no_runs(tmp_path) -> None:
    app = create_app(config_path=tmp_path / ".env.m2m2", runs_dir=tmp_path / "runs")
    client = TestClient(app)

    response = client.get("/api/runs")

    assert response.status_code == 200
    data = response.json()
    assert data["runs"] == []


def test_get_nonexistent_run_returns_404(tmp_path) -> None:
    app = create_app(config_path=tmp_path / ".env.m2m2", runs_dir=tmp_path / "runs")
    client = TestClient(app)

    response = client.get("/api/runs/nonexistent-run-id")

    assert response.status_code == 404
    data = response.json()
    assert "not found" in str(data["detail"]).lower()


def test_render_nonexistent_run_returns_500(tmp_path) -> None:
    app = create_app(config_path=tmp_path / ".env.m2m2", runs_dir=tmp_path / "runs")
    client = TestClient(app)

    response = client.post("/api/runs/nonexistent-run-id/render")

    # render_run catches 404 internally and wraps it as 500
    assert response.status_code == 500


def test_restage_without_stage_returns_400(tmp_path) -> None:
    app = create_app(config_path=tmp_path / ".env.m2m2", runs_dir=tmp_path / "runs")
    client = TestClient(app)

    response = client.post("/api/runs/nonexistent-run-id/restage", json={})

    assert response.status_code == 400
    data = response.json()
    assert "detail" in data


def test_video_nonexistent_run_returns_404(tmp_path) -> None:
    app = create_app(config_path=tmp_path / ".env.m2m2", runs_dir=tmp_path / "runs")
    client = TestClient(app)

    response = client.get("/api/runs/nonexistent-run-id/video")

    assert response.status_code == 404


def test_generate_with_empty_prompt_returns_400(tmp_path) -> None:
    app = create_app(config_path=tmp_path / ".env.m2m2", runs_dir=tmp_path / "runs")
    client = TestClient(app)

    response = client.post("/api/generate", json={"prompt": ""})

    assert response.status_code == 400
    data = response.json()
    assert "Prompt is required" in str(data["detail"])


def test_config_test_endpoint_returns_200(tmp_path) -> None:
    app = create_app(config_path=tmp_path / ".env.m2m2", runs_dir=tmp_path / "runs")
    client = TestClient(app)

    response = client.post("/api/config/test")

    assert response.status_code == 200
    assert response.json() is not None


def test_legacy_generate_endpoint(tmp_path) -> None:
    app = create_app(config_path=tmp_path / ".env.m2m2", runs_dir=tmp_path / "runs")
    client = TestClient(app)

    response = client.post(
        "/generate",
        json={
            "prompt": "Explain why derivatives are slopes",
            "audience_level": "high_school",
            "desired_duration": 45,
            "style": "clean classroom",
            "deterministic": True,
            "render": False,
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert "curriculum_plan" in data
    assert "render_result" in data


def test_generate_without_api_key_uses_deterministic(tmp_path) -> None:
    app = create_app(config_path=tmp_path / ".env.m2m2", runs_dir=tmp_path / "runs")
    client = TestClient(app)

    response = client.post(
        "/api/generate",
        json={
            "prompt": "What is a limit?",
            "use_ai": True,
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert "status" in data
    assert data["status"]["validation"] in ("passed", "failed")
