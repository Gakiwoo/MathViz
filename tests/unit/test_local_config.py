from __future__ import annotations

from math_to_manim.app.local_config import (
    DEFAULT_CONFIG_PATH,
    apply_provider_config_to_env,
    load_local_config,
    public_config,
    save_local_config,
)


def test_provider_presets_include_chinese_openai_compatible_options() -> None:
    config = public_config()
    presets = {preset["id"]: preset for preset in config["presets"]}

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
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
    monkeypatch.delenv("M2M2_MODEL", raising=False)
    monkeypatch.delenv("OPENAI_MODEL", raising=False)
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
    assert __import__("os").environ["OPENAI_API_KEY"] == "sk-test"
    assert __import__("os").environ["OPENAI_BASE_URL"] == "https://api.moonshot.ai/v1"
    assert __import__("os").environ["M2M2_MODEL"] == "moonshot-v1-8k"
    assert __import__("os").environ["OPENAI_MODEL"] == "moonshot-v1-8k"
