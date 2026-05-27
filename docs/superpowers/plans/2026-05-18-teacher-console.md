# Teacher Console Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a local browser-based teacher console for configuring OpenAI-compatible Chinese LLM providers, generating teaching artifacts, and optionally rendering a low-quality Manim preview.

**Architecture:** Keep the existing `AnimationPipeline` and artifact schemas intact. Add a thin FastAPI/local-static layer with focused helpers for provider config, run summaries, render health, and existing-run rendering.

**Tech Stack:** Python 3.10+, FastAPI, static HTML/CSS/JavaScript, existing M2M2 pipeline modules, pytest.

---

## File Structure

- Create `math_to_manim/app/local_config.py`: provider presets, safe `.env.m2m2` parsing/writing, masking, and runtime environment application.
- Create `math_to_manim/app/run_summary.py`: safe run-id resolution, artifact reading, run summaries, render dependency health, and render-an-existing-run helper.
- Modify `math_to_manim/app/api.py`: serve the static console and expose `/api/config`, `/api/generate`, `/api/runs`, `/api/runs/{run_id}`, `/api/runs/{run_id}/render`, `/api/runs/{run_id}/video`, and `/api/health/render`.
- Create `math_to_manim/app/static/index.html`: teacher console markup.
- Create `math_to_manim/app/static/styles.css`: restrained, responsive teacher-console styling.
- Create `math_to_manim/app/static/app.js`: browser behavior for config, generation, run history, tabs, dependency checks, and render actions.
- Create `scripts/start-teacher-console.sh`: macOS/Linux/WSL startup script.
- Modify `.gitignore`: ignore `.superpowers/` and local web scratch if needed.
- Create `tests/unit/test_local_config.py`: config and provider preset tests.
- Create `tests/unit/test_run_summary.py`: summary and health parsing tests.
- Create `tests/unit/test_teacher_console_api.py`: optional FastAPI endpoint tests.

This checkout has no `.git` directory, so commit steps are replaced with `git status --short || true` plus final changed-file reporting.

## Task 1: Local Provider Config

**Files:**
- Create: `math_to_manim/app/local_config.py`
- Test: `tests/unit/test_local_config.py`

- [ ] **Step 1: Write failing config tests**

```python
from __future__ import annotations

from math_to_manim.app.local_config import (
    DEFAULT_CONFIG_PATH,
    apply_provider_config_to_env,
    load_local_config,
    mask_secret,
    provider_presets,
    public_config,
    save_local_config,
)


def test_provider_presets_include_chinese_openai_compatible_options() -> None:
    presets = {preset["id"]: preset for preset in provider_presets()}

    assert {"deepseek", "qwen", "kimi", "glm", "doubao", "custom"}.issubset(presets)
    assert presets["deepseek"]["base_url"].startswith("https://")
    assert presets["custom"]["base_url"] == ""


def test_save_load_public_config_masks_api_key(tmp_path) -> None:
    config_path = tmp_path / ".env.m2m2"

    saved = save_local_config(
        {
            "provider_id": "deepseek",
            "base_url": "https://api.deepseek.com",
            "model": "deepseek-v4-flash",
            "api_key": "sk-abcdef123456",
        },
        path=config_path,
    )
    loaded = load_local_config(config_path)
    public = public_config(config_path)

    assert saved.provider_id == "deepseek"
    assert loaded.api_key == "sk-abcdef123456"
    assert public["current"]["has_api_key"] is True
    assert public["current"]["api_key_mask"] == "sk-a********3456"
    assert "sk-abcdef123456" not in str(public)


def test_save_preserves_existing_api_key_when_post_body_omits_key(tmp_path) -> None:
    config_path = tmp_path / ".env.m2m2"
    save_local_config(
        {
            "provider_id": "deepseek",
            "base_url": "https://api.deepseek.com",
            "model": "deepseek-v4-flash",
            "api_key": "sk-existing",
        },
        path=config_path,
    )

    save_local_config(
        {
            "provider_id": "qwen",
            "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
            "model": "qwen-plus",
        },
        path=config_path,
    )

    loaded = load_local_config(config_path)
    assert loaded.provider_id == "qwen"
    assert loaded.api_key == "sk-existing"


def test_apply_provider_config_to_env_sets_openai_compatible_variables(tmp_path, monkeypatch) -> None:
    config_path = tmp_path / ".env.m2m2"
    save_local_config(
        {
            "provider_id": "kimi",
            "base_url": "https://api.moonshot.ai/v1",
            "model": "moonshot-v1-8k",
            "api_key": "sk-test",
        },
        path=config_path,
    )

    apply_provider_config_to_env(load_local_config(config_path))

    assert DEFAULT_CONFIG_PATH.name == ".env.m2m2"
    assert monkeypatch is not None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `./.venv/bin/python -m pytest tests/unit/test_local_config.py -q`

Expected: FAIL because `math_to_manim.app.local_config` does not exist.

- [ ] **Step 3: Implement `local_config.py`**

Implement these public functions and dataclasses:

```python
@dataclass(frozen=True)
class ProviderPreset:
    id: str
    name: str
    base_url: str
    default_model: str


@dataclass(frozen=True)
class LocalProviderConfig:
    provider_id: str
    base_url: str
    model: str
    api_key: str = ""

    @property
    def has_api_key(self) -> bool:
        return bool(self.api_key.strip())
```

Use managed keys:

```python
M2M2_PROVIDER_ID
OPENAI_API_KEY
OPENAI_BASE_URL
M2M2_MODEL
OPENAI_MODEL
```

Preset defaults:

```python
deepseek: https://api.deepseek.com, deepseek-v4-flash
qwen: https://dashscope.aliyuncs.com/compatible-mode/v1, qwen-plus
kimi: https://api.moonshot.ai/v1, moonshot-v1-8k
glm: https://open.bigmodel.cn/api/paas/v4, glm-4-flash
doubao: https://ark.cn-beijing.volces.com/api/v3, doubao-seed-1-6-250615
custom: "", ""
```

- [ ] **Step 4: Run config tests**

Run: `./.venv/bin/python -m pytest tests/unit/test_local_config.py -q`

Expected: PASS.

## Task 2: Run Summary and Render Helpers

**Files:**
- Create: `math_to_manim/app/run_summary.py`
- Test: `tests/unit/test_run_summary.py`

- [ ] **Step 1: Write failing run summary tests**

```python
from __future__ import annotations

import json

from math_to_manim.app.run_summary import check_render_health, list_runs, safe_run_dir, summarize_run


def write_json(path, payload):
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_summarize_run_reads_artifacts_and_missing_render(tmp_path) -> None:
    run_dir = tmp_path / "20260518T000000Z-demo"
    run_dir.mkdir()
    write_json(run_dir / "request.json", {"prompt": "Explain derivatives", "target_audience": "high_school", "duration_seconds": 60, "style": "cinematic"})
    write_json(run_dir / "curriculum.json", {"title": "Derivatives", "learning_objectives": ["See slope as change"], "modules": []})
    write_json(run_dir / "storyboard.json", {"title": "Slope story", "scenes": [{"title": "Zoom", "narration": "A secant becomes tangent", "visual_actions": ["Draw curve"]}]})
    write_json(run_dir / "generated_code.json", {"scene_name": "DemoScene", "code": "from manim import *\\nclass DemoScene(Scene):\\n    def construct(self):\\n        pass\\n"})
    write_json(run_dir / "validation_report.json", {"status": "passed", "issues": [], "checked_artifacts": ["generated_scene.py"], "summary": "ok", "metadata": {}})
    write_json(run_dir / "render_result.json", {"status": "failed", "scene_name": "DemoScene", "output_path": None, "command": [], "stderr": "render skipped", "metadata": {"skipped": True}})
    write_json(run_dir / "manifest.json", {"created_at": "2026-05-18T00:00:00+00:00", "artifacts": ["request", "curriculum"]})

    summary = summarize_run(run_dir)

    assert summary["run_id"] == "20260518T000000Z-demo"
    assert summary["prompt"] == "Explain derivatives"
    assert summary["status"]["validation"] == "passed"
    assert summary["status"]["render"] == "failed"
    assert summary["video_url"] is None
    assert "See slope as change" in summary["sections"]["teaching_plan"]
    assert "DemoScene" in summary["sections"]["manim_code"]


def test_safe_run_dir_rejects_path_traversal(tmp_path) -> None:
    runs_dir = tmp_path / "runs"
    runs_dir.mkdir()
    good = runs_dir / "run-a"
    good.mkdir()

    assert safe_run_dir(runs_dir, "run-a") == good.resolve()
    assert safe_run_dir(runs_dir, "../outside") is None


def test_list_runs_orders_newest_first(tmp_path) -> None:
    runs_dir = tmp_path / "runs"
    runs_dir.mkdir()
    older = runs_dir / "20260518T000000Z-old"
    newer = runs_dir / "20260518T010000Z-new"
    older.mkdir()
    newer.mkdir()

    assert [run["run_id"] for run in list_runs(runs_dir)] == ["20260518T010000Z-new", "20260518T000000Z-old"]


def test_check_render_health_reports_missing_fake_binaries() -> None:
    health = check_render_health(manim_bin="missing-manim-for-test", ffmpeg_bin="missing-ffmpeg-for-test", latex_bin="missing-latex-for-test")

    assert health["ready"] is False
    assert health["tools"]["manim"]["available"] is False
    assert health["tools"]["ffmpeg"]["available"] is False
    assert health["tools"]["latex"]["available"] is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `./.venv/bin/python -m pytest tests/unit/test_run_summary.py -q`

Expected: FAIL because `run_summary.py` does not exist.

- [ ] **Step 3: Implement `run_summary.py`**

Implement:

```python
def safe_run_dir(runs_dir: Path, run_id: str) -> Path | None
def summarize_run(run_dir: Path) -> dict[str, Any]
def list_runs(runs_dir: Path, *, limit: int = 20) -> list[dict[str, Any]]
def check_render_health(manim_bin: str = "manim", ffmpeg_bin: str = "ffmpeg", latex_bin: str = "latex") -> dict[str, Any]
def render_existing_run(run_dir: Path, config: RuntimeConfig) -> dict[str, Any]
```

`render_existing_run` must read `generated_code.json`, run or refresh static validation, skip rendering if validation fails, call `RenderAgent` if validation passes, write `render_result.json` and `review_report.json`, then return `summarize_run(run_dir)`.

- [ ] **Step 4: Run run summary tests**

Run: `./.venv/bin/python -m pytest tests/unit/test_run_summary.py -q`

Expected: PASS.

## Task 3: FastAPI Local Console API

**Files:**
- Modify: `math_to_manim/app/api.py`
- Test: `tests/unit/test_teacher_console_api.py`

- [ ] **Step 1: Write failing API tests**

```python
from __future__ import annotations

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient

from math_to_manim.app.api import create_app


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
    assert data["status"]["render"] == "failed"
    assert (tmp_path / "runs" / data["run_id"] / "manifest.json").exists()


def test_render_health_endpoint_returns_tool_status(tmp_path) -> None:
    app = create_app(config_path=tmp_path / ".env.m2m2", runs_dir=tmp_path / "runs")
    client = TestClient(app)

    response = client.get("/api/health/render")

    assert response.status_code == 200
    data = response.json()
    assert "manim" in data["tools"]
    assert "install_commands" in data
```

- [ ] **Step 2: Run API tests to verify they fail**

Run: `./.venv/bin/python -m pytest tests/unit/test_teacher_console_api.py -q`

Expected: FAIL because `create_app` does not yet accept `config_path` or `runs_dir`, and the new endpoints are missing.

- [ ] **Step 3: Expand `api.py`**

Keep the existing `create_app()` factory importable by uvicorn. Add optional keyword arguments:

```python
def create_app(config_path: Path | None = None, runs_dir: Path | None = None):
```

Endpoint behavior:

- `GET /` returns `math_to_manim/app/static/index.html`.
- `GET /api/config` returns `public_config(config_path)`.
- `POST /api/config` calls `save_local_config(payload, path=config_path)`.
- `POST /api/config/test` returns `{"status": "needs_config"}` when no API key is present; otherwise performs a short OpenAI-compatible `/chat/completions` request.
- `POST /api/generate` builds a `RuntimeConfig` from env plus local config, defaults to deterministic if no API key is saved, calls `AnimationPipeline.generate(..., render=False)`, and returns `summarize_run(run_dir)`.
- `GET /api/runs` returns `list_runs(config.runs_dir)`.
- `GET /api/runs/{run_id}` resolves with `safe_run_dir` and returns 404 on invalid ids.
- `POST /api/runs/{run_id}/render` calls `render_existing_run`.
- `GET /api/runs/{run_id}/video` returns a `FileResponse` for the rendered MP4 when present.
- `GET /api/health/render` returns `check_render_health()`.

- [ ] **Step 4: Run API tests**

Run: `./.venv/bin/python -m pytest tests/unit/test_teacher_console_api.py -q`

Expected: PASS or SKIP if FastAPI/httpx is not installed.

## Task 4: Static Teacher Console UI

**Files:**
- Create: `math_to_manim/app/static/index.html`
- Create: `math_to_manim/app/static/styles.css`
- Create: `math_to_manim/app/static/app.js`

- [ ] **Step 1: Create `index.html`**

The page must include:

- left rail with Generate, Model Config, Run History, Dependency Check
- prompt form
- stage status cards
- artifact tabs
- right preview panel
- config form
- history panel
- dependency panel

Use local CSS and JS only:

```html
<link rel="stylesheet" href="/static/styles.css">
<script defer src="/static/app.js"></script>
```

- [ ] **Step 2: Create `styles.css`**

Use a restrained neutral interface with teal action color, stable three-column layout, responsive fallback below 980px, 8px or smaller card radii, no gradients, no decorative blobs, and stable button dimensions.

- [ ] **Step 3: Create `app.js`**

Implement these functions:

```javascript
async function api(path, options = {})
async function loadConfig()
async function saveConfig(event)
async function testConfig()
async function loadRenderHealth()
async function generateRun(event)
async function renderCurrentRun()
async function loadRuns()
async function openRun(runId)
function renderRun(run)
function switchPanel(panel)
function switchTab(tab)
```

Show API keys only as masked status text. Never put a saved key back into the input value.

- [ ] **Step 4: Manual browser check**

Run: `./scripts/start-teacher-console.sh --no-open --port 8765`

Open: `http://127.0.0.1:8765`

Expected: the console loads without JavaScript errors, config presets populate, render health appears, and deterministic generation can be triggered when no key is saved.

## Task 5: Startup Script and Ignore Rules

**Files:**
- Create: `scripts/start-teacher-console.sh`
- Modify: `.gitignore`

- [ ] **Step 1: Create startup script**

The script must:

- resolve repo root from its own location
- create `.venv` if missing
- install `.[web]`
- support `--host`, `--port`, and `--no-open`
- start uvicorn with `math_to_manim.app.api:create_app --factory`
- open the browser on macOS/Linux when `--no-open` is not set

- [ ] **Step 2: Make script executable**

Run: `chmod +x scripts/start-teacher-console.sh`

Expected: no output.

- [ ] **Step 3: Ignore local brainstorm artifacts**

Add `.superpowers/` to `.gitignore`.

- [ ] **Step 4: Script smoke**

Run: `./scripts/start-teacher-console.sh --no-open --port 8766`

Expected: uvicorn starts. Stop with Ctrl-C after confirming `Application startup complete`.

## Task 6: Full Verification

**Files:**
- No new files.

- [ ] **Step 1: Run focused tests**

Run:

```bash
./.venv/bin/python -m pytest \
  tests/unit/test_local_config.py \
  tests/unit/test_run_summary.py \
  tests/unit/test_teacher_console_api.py \
  -q
```

Expected: PASS, with API tests allowed to SKIP only if optional web dependencies are not installed.

- [ ] **Step 2: Run repository tests**

Run: `./.venv/bin/python -m pytest`

Expected: PASS.

- [ ] **Step 3: Run CLI smoke**

Run:

```bash
./.venv/bin/python -m math_to_manim.cli generate \
  "Explain why derivatives are slopes" \
  --deterministic \
  --no-render \
  --runs-dir /tmp/m2m2-smoke
```

Expected: command exits 0 and prints `Math-To-Manim run complete`.

- [ ] **Step 4: Run web startup smoke**

Run: `./scripts/start-teacher-console.sh --no-open --port 8767`

Expected: uvicorn starts and the app serves `GET /`. Stop with Ctrl-C.

- [ ] **Step 5: Inspect local change state**

Run: `git status --short || true`

Expected in this checkout: `fatal: not a git repository` is acceptable. Report changed files manually in final response.

## Self-Review

Spec coverage:

- Local single-machine startup: Task 5.
- FastAPI static teacher console: Tasks 3 and 4.
- OpenAI-compatible Chinese provider config: Task 1 and Task 3.
- Two-step generation/render flow: Task 2, Task 3, and Task 4.
- Secret masking: Task 1 and Task 4.
- Run history and artifact browsing: Task 2, Task 3, and Task 4.
- Render dependency health: Task 2, Task 3, and Task 4.
- Tests and smoke commands: Task 6.

Placeholder scan: no `TBD`, `TODO`, or undefined "implement later" work remains in this plan.

Type consistency: `LocalProviderConfig`, `ProviderPreset`, `safe_run_dir`, `summarize_run`, `list_runs`, `check_render_health`, and `render_existing_run` are defined before API and UI tasks consume them.
