from __future__ import annotations

import os

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient

from math_to_manim.app.api import _should_use_deterministic_generation, create_app

# Environment variables that RuntimeConfig.from_env() reads and that
# load_local_config falls back to.  Tests must be isolated from the
# project-root .env.m2m2 so that a real API key never leaks into a
# deterministic-only test and triggers a live API call.
_MANAGED_ENV_VARS = (
    "OPENAI_API_KEY",
    "OPENAI_BASE_URL",
    "M2M2_MODEL",
    "OPENAI_MODEL",
    "M2M2_PROVIDER_ID",
    "M2M2_RUNS_DIR",
    "M2M2_DETERMINISTIC",
    "M2M2_TRACE",
    # Console auth / bind guard. Must be unset unless a test opts in, so the
    # default local-only, token-free console keeps working.
    "MATHVIZ_API_TOKEN",
    "MATHVIZ_BIND_HOST",
)


@pytest.fixture(autouse=True)
def _isolate_from_project_env() -> None:
    """Remove env vars that may have been loaded from the root .env.m2m2."""
    saved = {k: os.environ.pop(k, None) for k in _MANAGED_ENV_VARS}
    yield
    for k, v in saved.items():
        if v is not None:
            os.environ[k] = v


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


def test_restage_valid_stage_endpoint_reruns_artifact(tmp_path) -> None:
    app = create_app(config_path=tmp_path / ".env.m2m2", runs_dir=tmp_path / "runs")
    client = TestClient(app)

    gen = client.post(
        "/api/generate",
        json={"prompt": "Explain why derivatives are slopes", "deterministic": True},
    )
    assert gen.status_code == 200
    run_id = gen.json()["run_id"]

    response = client.post(f"/api/runs/{run_id}/restage", json={"stage": "intent"})

    assert response.status_code == 200
    data = response.json()
    assert data["run_id"] == run_id
    assert (tmp_path / "runs" / run_id / "intent.json").exists()


def test_restage_unknown_stage_endpoint_returns_400(tmp_path) -> None:
    app = create_app(config_path=tmp_path / ".env.m2m2", runs_dir=tmp_path / "runs")
    client = TestClient(app)

    gen = client.post(
        "/api/generate",
        json={"prompt": "Explain why derivatives are slopes", "deterministic": True},
    )
    run_id = gen.json()["run_id"]

    response = client.post(f"/api/runs/{run_id}/restage", json={"stage": "bogus_stage"})

    assert response.status_code == 400
    data = response.json()
    assert "bogus_stage" in str(data["detail"])


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


def test_api_stays_open_when_no_token_configured(tmp_path) -> None:
    """The local-only console must keep working out of the box."""

    app = create_app(config_path=tmp_path / ".env.m2m2", runs_dir=tmp_path / "runs")
    client = TestClient(app)

    assert client.get("/api/runs").status_code == 200


def test_api_requires_token_when_configured(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("MATHVIZ_API_TOKEN", "s3cret")
    app = create_app(config_path=tmp_path / ".env.m2m2", runs_dir=tmp_path / "runs")
    client = TestClient(app)

    assert client.get("/api/runs").status_code == 401
    assert client.get("/api/runs", headers={"Authorization": "Bearer wrong"}).status_code == 401
    assert client.get("/api/runs", headers={"Authorization": "Bearer s3cret"}).status_code == 200
    assert client.get("/api/runs", headers={"X-API-Key": "s3cret"}).status_code == 200

    # Static assets stay reachable; only /api routes are guarded.
    assert client.get("/").status_code in (200, 404)


def test_non_loopback_bind_without_token_is_refused(tmp_path, monkeypatch) -> None:
    """Exposing the console beyond localhost must require a token."""

    monkeypatch.setenv("MATHVIZ_BIND_HOST", "0.0.0.0")
    monkeypatch.delenv("MATHVIZ_API_TOKEN", raising=False)

    with pytest.raises(RuntimeError, match="MATHVIZ_API_TOKEN"):
        create_app(config_path=tmp_path / ".env.m2m2", runs_dir=tmp_path / "runs")


def test_non_loopback_bind_with_token_is_allowed(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("MATHVIZ_BIND_HOST", "0.0.0.0")
    monkeypatch.setenv("MATHVIZ_API_TOKEN", "s3cret")

    app = create_app(config_path=tmp_path / ".env.m2m2", runs_dir=tmp_path / "runs")
    client = TestClient(app)

    assert client.get("/api/runs").status_code == 401
    assert client.get("/api/runs", headers={"Authorization": "Bearer s3cret"}).status_code == 200
