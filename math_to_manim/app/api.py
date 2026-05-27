"""Optional FastAPI application and local teacher console."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from math_to_manim.app.local_config import (
    DEFAULT_CONFIG_PATH,
    apply_provider_config_to_env,
    load_local_config,
    public_config,
    save_local_config,
)
from math_to_manim.app.run_summary import (
    check_render_health,
    list_runs,
    render_existing_run,
    restage_run,
    safe_run_dir,
    summarize_run,
)
from math_to_manim.config import RuntimeConfig
from math_to_manim.pipeline.runner import AnimationPipeline

STATIC_DIR = Path(__file__).parent / "static"


def _should_use_deterministic_generation(payload: dict[str, Any], *, has_api_key: bool) -> bool:
    """Default the teacher console to the fast local path unless AI is requested."""

    if bool(payload.get("deterministic", False)):
        return True
    if not has_api_key:
        return True
    return not bool(payload.get("use_ai", False))


def create_app(config_path: str | Path | None = None, runs_dir: str | Path | None = None):
    try:
        from fastapi import FastAPI, HTTPException
        from fastapi.responses import FileResponse, Response
        from fastapi.staticfiles import StaticFiles
    except ImportError as exc:
        raise RuntimeError("Install the web extra to use the API: pip install -e .[web]") from exc

    config_file = Path(config_path) if config_path is not None else DEFAULT_CONFIG_PATH
    runs_dir_override = Path(runs_dir) if runs_dir is not None else None

    app = FastAPI(title="Math-To-Manim Teacher Console")
    if STATIC_DIR.exists():
        app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    def runtime_config(*, deterministic: bool | None = None) -> RuntimeConfig:
        provider_config = load_local_config(config_file)
        apply_provider_config_to_env(provider_config)
        config = RuntimeConfig.from_env()
        updates: dict[str, Any] = {}
        if runs_dir_override is not None:
            updates["runs_dir"] = runs_dir_override
        if deterministic is not None:
            updates["deterministic"] = deterministic
        elif not provider_config.has_api_key:
            updates["deterministic"] = True
        if provider_config.model:
            updates["model"] = provider_config.model
        return RuntimeConfig(**{**config.__dict__, **updates})

    def require_run(run_id: str) -> Path:
        run_dir = safe_run_dir(runtime_config().runs_dir, run_id)
        if run_dir is None:
            raise HTTPException(status_code=404, detail={"message": "Run not found."})
        return run_dir

    @app.get("/")
    def index():
        index_path = STATIC_DIR / "index.html"
        if not index_path.exists():
            return {"name": "Math-To-Manim Teacher Console", "status": "static assets not installed"}
        return FileResponse(index_path)

    @app.get("/favicon.ico", include_in_schema=False)
    def favicon():
        return Response(status_code=204)

    @app.get("/api/config")
    def get_config():
        return public_config(config_file)

    @app.post("/api/config")
    def post_config(payload: dict[str, Any]):
        save_local_config(payload, path=config_file)
        return public_config(config_file)

    @app.post("/api/config/test")
    def test_config(payload: dict[str, Any] | None = None):
        if payload:
            config = save_local_config(payload, path=config_file)
        else:
            config = load_local_config(config_file)
        if not config.has_api_key:
            return {"status": "needs_config", "message": "API Key is required before testing the provider."}
        try:
            import httpx
        except ImportError:
            return {"status": "skipped", "message": "Install httpx to test provider connectivity."}

        endpoint = f"{config.base_url.rstrip('/')}/chat/completions"
        try:
            response = httpx.post(
                endpoint,
                headers={"Authorization": f"Bearer {config.api_key}"},
                json={
                    "model": config.model,
                    "messages": [{"role": "user", "content": "Reply with ok."}],
                    "max_tokens": 8,
                },
                timeout=10,
            )
        except Exception as exc:
            return {"status": "failed", "message": f"Provider test failed: {exc.__class__.__name__}"}
        if response.status_code >= 400:
            return {"status": "failed", "message": f"Provider returned HTTP {response.status_code}."}
        return {"status": "ok", "message": "Provider connection succeeded."}

    @app.post("/api/generate")
    def generate_run(payload: dict[str, Any]):
        prompt = str(payload.get("prompt") or "").strip()
        if not prompt:
            raise HTTPException(status_code=400, detail={"message": "Prompt is required."})
        provider_config = load_local_config(config_file)
        deterministic = _should_use_deterministic_generation(payload, has_api_key=provider_config.has_api_key)
        config = runtime_config(deterministic=deterministic)
        try:
            package = AnimationPipeline(config=config).generate(
                prompt=prompt,
                audience_level=str(payload.get("audience_level") or "high_school"),
                desired_duration=int(payload.get("desired_duration") or 60),
                style=str(payload.get("style") or "clean classroom"),
                render=False,
            )
        except Exception as exc:
            import traceback

            tb = traceback.format_exc()
            print(tb, flush=True)
            if not deterministic:
                try:
                    fallback_config = runtime_config(deterministic=True)
                    package = AnimationPipeline(config=fallback_config).generate(
                        prompt=prompt,
                        audience_level=str(payload.get("audience_level") or "high_school"),
                        desired_duration=int(payload.get("desired_duration") or 60),
                        style=str(payload.get("style") or "clean classroom"),
                        render=False,
                    )
                    run_dir = Path(
                        package.metadata.get("run_dir") or Path(package.metadata["reproducibility_manifest"]).parent
                    )
                    summary = summarize_run(run_dir)
                    summary["notice"] = {
                        "level": "warn",
                        "message": f"AI 深度生成失败，已自动切换为本地快速草稿：{exc.__class__.__name__}",
                    }
                    return summary
                except Exception:
                    pass
            raise HTTPException(
                status_code=500,
                detail={
                    "message": f"Generation failed: {exc.__class__.__name__}",
                    "error": str(exc)[:500],
                    "traceback": tb[-2000:],
                },
            ) from exc
        run_dir = Path(package.metadata.get("run_dir") or Path(package.metadata["reproducibility_manifest"]).parent)
        return summarize_run(run_dir)

    @app.get("/api/runs")
    def get_runs():
        return {"runs": list_runs(runtime_config().runs_dir)}

    @app.get("/api/runs/{run_id}")
    def get_run(run_id: str):
        return summarize_run(require_run(run_id))

    @app.post("/api/runs/{run_id}/render")
    def render_run(run_id: str):
        try:
            return render_existing_run(require_run(run_id), runtime_config(deterministic=False))
        except Exception as exc:
            import traceback

            tb = traceback.format_exc()
            print(f"[render_run] Unhandled exception: {exc}\n{tb}", flush=True)
            raise HTTPException(
                status_code=500, detail={"message": f"渲染请求内部错误：{exc}", "traceback": tb[-2000:]}
            ) from exc

    @app.post("/api/runs/{run_id}/restage")
    def restage(run_id: str, payload: dict[str, Any]):
        stage = str(payload.get("stage", "")).strip()
        if not stage:
            raise HTTPException(status_code=400, detail={"message": "stage is required"})
        run_dir = require_run(run_id)
        result = restage_run(run_dir, runtime_config(deterministic=False), stage)
        if "error" in result:
            raise HTTPException(status_code=400, detail={"message": result["error"]})
        return summarize_run(run_dir)

    @app.get("/api/runs/{run_id}/video")
    def run_video(run_id: str):
        summary = summarize_run(require_run(run_id))
        video_path = summary.get("video_path")
        if not video_path or not Path(video_path).exists():
            raise HTTPException(status_code=404, detail={"message": "Video not found."})
        return FileResponse(video_path, media_type="video/mp4")

    @app.get("/api/health/render")
    def render_health():
        return check_render_health()

    @app.post("/generate")
    def legacy_generate(payload: dict[str, Any]):
        config = runtime_config(deterministic=bool(payload.get("deterministic", False)))
        package = AnimationPipeline(config).generate(
            prompt=payload["prompt"],
            audience_level=payload.get("audience_level", "high_school"),
            desired_duration=int(payload.get("desired_duration", 60)),
            style=payload.get("style", "cinematic"),
            render=bool(payload.get("render", False)),
        )
        return package.to_public_dict()

    return app
