# Teacher Console Design

Date: 2026-05-18

## Summary

Build a local, browser-based teacher console on top of the existing Math-To-Manim pipeline. The first version targets a single teacher running the project on their own machine: they download the repository, run one startup script, configure an OpenAI-compatible Chinese LLM provider, generate a teaching plan and Manim code, then optionally render a low-quality preview video when local render dependencies are available.

The product goal is to reduce teacher friction without changing the core M2M2 contract: prompts still become typed artifacts, generated Manim code, validation reports, optional renders, review reports, and reproducible run bundles.

## Decisions

- Product shape: local single-machine tool, not a SaaS product.
- Implementation route: FastAPI plus static frontend assets served by the same local app.
- Frontend build: no Node/Vite/React dependency for the first version.
- Model support: OpenAI-compatible configuration with presets for Chinese providers.
- Default generation: two-step flow. First generate plan and code with `render=false`; render preview only after the user clicks a render action.
- Secrets: save only to local ignored environment files, never show API keys in logs, UI, docs, or final responses.
- Pipeline contract: preserve existing artifact names and schemas unless a later implementation task explicitly changes them.

## Non-Goals

- No user accounts, login, billing, tenants, or cloud storage.
- No public deployment design in this first version.
- No multi-user queue, database, or background worker system.
- No full visual timeline editor or drag-and-drop Manim canvas.
- No provider-specific SDK integrations for individual Chinese vendors in the first version.

## User Journey

1. A teacher downloads the repository.
2. The teacher runs `./scripts/start-teacher-console.sh`, double-clicks `scripts/start-teacher-console.command` on macOS, or runs `scripts\start-teacher-console.bat` / `.\scripts\start-teacher-console.ps1` on Windows.
3. The script creates or reuses `.venv`, installs `.[web]`, starts the local FastAPI app, and opens the browser.
4. The teacher chooses a provider preset such as DeepSeek, Qwen, Kimi, GLM, Doubao, or custom OpenAI-compatible.
5. The teacher enters API Key, Base URL, and model name, then saves the local config.
6. The teacher enters a teaching prompt, audience level, duration, and style.
7. The app generates teaching artifacts and Manim code without rendering by default.
8. The teacher reviews the teaching plan, storyboard, generated code, and run bundle path.
9. If render dependencies are available, the teacher clicks "Render low-quality preview".
10. The app shows the preview video when rendering succeeds, or a stage-specific error if it fails.

If no API key is configured, the app should show a deterministic local demo action so the teacher can see the workflow before adding credentials.

## Architecture

The current pipeline remains the core runtime:

```text
browser
  -> FastAPI local app
  -> AnimationPipeline(RuntimeConfig)
  -> runs/<run_id>/ typed artifact bundle
```

The local app is a thin product layer around existing M2M2 modules. It should not move provider details into artifact schemas and should not bypass static validation before rendering.

Expected additions:

- `math_to_manim/app/api.py`: expand the optional FastAPI app into the local console API.
- `math_to_manim/app/static/`: static HTML, CSS, and JavaScript for the teacher console.
- `math_to_manim/app/local_config.py`: read/write local provider settings safely.
- `math_to_manim/app/run_summary.py`: summarize run bundle artifacts for the UI.
- `scripts/start-teacher-console.sh`: one-command startup path for macOS/Linux/WSL.
- `scripts/start-teacher-console.command`: macOS Finder double-click wrapper.
- `scripts/start-teacher-console.ps1` and `scripts/start-teacher-console.bat`: Windows startup paths.
- Tests under `tests/unit/` for config, API, and run summary behavior.

## API Surface

Minimum endpoints:

- `GET /`: serve the teacher console.
- `GET /api/config`: return provider preset names, current non-secret config, and API key presence.
- `POST /api/config`: validate and save provider, base URL, model, and API key to local config.
- `POST /api/config/test`: run a minimal provider connectivity check with a short timeout when an API key is present; otherwise return a clear `needs_config` response.
- `POST /api/generate`: generate artifacts with `render=false` by default.
- `POST /api/runs/{run_id}/render`: render an existing generated scene using the frozen run bundle.
- `GET /api/runs`: list recent run directories.
- `GET /api/runs/{run_id}`: return a safe summary of artifacts, status, paths, and video output.
- `GET /api/health/render`: check local Manim, FFmpeg, and LaTeX availability.

The API should return teacher-readable error messages plus developer-oriented fields such as stage, run directory, report path, and stderr summary when safe. It must not return secret values.

## Provider Configuration

The first version uses one OpenAI-compatible adapter shape:

- provider display name
- base URL
- model name
- API key

Provider presets:

- DeepSeek
- Qwen / Tongyi
- Kimi / Moonshot
- GLM / Zhipu
- Doubao / Volcano Ark
- Custom OpenAI-compatible

The UI can prefill common Base URL and model examples, but the teacher can edit them. Runtime config should map saved settings into environment/runtime values compatible with the existing agent path, such as `OPENAI_API_KEY`, `OPENAI_BASE_URL`, and `M2M2_MODEL`.

The local config file should be ignored by git. Existing `.env` support can be reused if the implementation keeps parsing simple and avoids overwriting unrelated user values unexpectedly.

## UI Design

The app opens directly into a teacher console. It is not a marketing page.

Layout:

- Left rail: Generate, Model Config, Run History, Dependency Check.
- Main panel: prompt form, audience/duration/style controls, stage status cards, artifact tabs.
- Right panel: video preview, render health, render action, run directory action.

Primary workflow:

- Main button: "Generate teaching plan and code".
- Secondary button: "Load example".
- Render button: "Render low-quality preview"; disabled or explanatory when dependencies are missing.

Artifact tabs:

- Teaching plan
- Knowledge graph summary
- Storyboard
- Manim code
- Run bundle

The interface should feel like a quiet teaching tool: dense enough for repeated use, clear status, restrained palette, and no decorative landing-page sections. API keys are masked and never displayed after save.

## Data Flow

Generation request:

```text
Prompt form
  -> POST /api/generate
  -> RuntimeConfig from local config
  -> AnimationPipeline.generate(render=false)
  -> runs/<run_id>/
  -> UI run summary
```

Render request:

```text
Existing run id
  -> dependency check
  -> static validation result already present
  -> render generated_scene.py if validation passed
  -> update render_result.json and review_report.json
  -> UI video preview or failure state
```

If render retry or repair is added, it should reuse the frozen upstream `scene_spec` and captured stdout/stderr rather than rerunning all planning stages.

## Error Handling

Teacher-facing errors should be short and actionable:

- Model config failure: "API Key, Base URL, or model name is unavailable."
- Generation failure: show failed stage, run directory if created, and safe trace/report links.
- Missing dependencies: list missing `manim`, `ffmpeg`, or `latex`, then show install commands from this repository.
- Static validation failure: explain that rendering was blocked before Manim ran.
- Render failure: show Manim stderr summary, command, and report path.

Developer detail stays in the run bundle. The UI should avoid raw stack traces unless a developer/debug view is explicitly opened.

## Testing Plan

Unit tests:

- Provider preset mapping returns expected non-secret fields.
- Local config save/load masks API keys and preserves required runtime values.
- Run summary parser reads existing artifact files and handles missing render output.
- API generation path supports deterministic/no-render generation.
- Render health endpoint reports missing binaries without crashing.

Smoke checks:

```bash
./.venv/bin/python -m pytest
./.venv/bin/python -m math_to_manim.cli --help
./.venv/bin/python -m math_to_manim.cli generate "Explain why derivatives are slopes" --deterministic --no-render --runs-dir /tmp/m2m2-smoke
./scripts/start-teacher-console.sh --no-open
```

Manual acceptance:

- Browser opens from the startup script.
- Teacher can save an OpenAI-compatible provider config without exposing the key.
- Teacher can generate a no-render run for "Explain why derivatives are slopes".
- UI shows teaching plan, storyboard, generated code, run directory, and render status.
- Missing render dependencies produce clear install guidance.

## Risks

- OpenAI-compatible providers can differ in structured output quality. Keep deterministic fallback and clear provider error reporting.
- Real rendering still depends on system packages outside Python. The two-step flow avoids making first launch fail because FFmpeg or LaTeX is missing.
- Writing to `.env` can overwrite user expectations. Implementation should preserve unrelated keys and only manage documented M2M2/provider keys.
- Serving generated code and video paths locally is acceptable for single-machine use, but this design is not sufficient for public hosting.

## Rollback

The work is additive. If the console causes problems, the existing CLI path remains available:

```bash
./.venv/bin/python -m math_to_manim.cli generate "Explain why derivatives are slopes" --deterministic --no-render
```

Removing the new app/static files and startup script should restore the repository to the current CLI-first behavior without schema or pipeline migration.
