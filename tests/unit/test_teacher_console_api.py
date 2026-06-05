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
