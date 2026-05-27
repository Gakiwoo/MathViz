"""Local OpenAI-compatible provider configuration for the teacher console."""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

DEFAULT_CONFIG_PATH = Path(".env.m2m2")
MANAGED_KEYS = ("M2M2_PROVIDER_ID", "OPENAI_API_KEY", "OPENAI_BASE_URL", "M2M2_MODEL", "OPENAI_MODEL")


@dataclass(frozen=True)
class ProviderPreset:
    id: str
    name: str
    base_url: str
    default_model: str

    def to_public_dict(self) -> dict[str, str]:
        return {
            "id": self.id,
            "name": self.name,
            "base_url": self.base_url,
            "default_model": self.default_model,
        }


@dataclass(frozen=True)
class LocalProviderConfig:
    provider_id: str
    base_url: str
    model: str
    api_key: str = ""

    @property
    def has_api_key(self) -> bool:
        return bool(self.api_key.strip())


PROVIDER_PRESETS: tuple[ProviderPreset, ...] = (
    ProviderPreset("deepseek", "DeepSeek", "https://api.deepseek.com", "deepseek-v4-flash"),
    ProviderPreset("qwen", "通义千问 / Qwen", "https://dashscope.aliyuncs.com/compatible-mode/v1", "qwen-plus"),
    ProviderPreset("kimi", "月之暗面 / Kimi", "https://api.moonshot.ai/v1", "moonshot-v1-8k"),
    ProviderPreset("glm", "智谱 GLM", "https://open.bigmodel.cn/api/paas/v4", "glm-4-flash"),
    ProviderPreset("doubao", "火山方舟 / Doubao", "https://ark.cn-beijing.volces.com/api/v3", "doubao-seed-1-6-250615"),
    ProviderPreset("custom", "自定义 OpenAI-compatible", "", ""),
)


def provider_presets() -> list[dict[str, str]]:
    return [preset.to_public_dict() for preset in PROVIDER_PRESETS]


def load_local_config(path: Path = DEFAULT_CONFIG_PATH) -> LocalProviderConfig:
    values = _read_env_values(path)
    provider_id = values.get("M2M2_PROVIDER_ID") or os.getenv("M2M2_PROVIDER_ID") or "deepseek"
    preset = _preset_by_id(provider_id) or PROVIDER_PRESETS[0]
    base_url = values.get("OPENAI_BASE_URL") or os.getenv("OPENAI_BASE_URL") or preset.base_url
    model = (
        values.get("M2M2_MODEL")
        or values.get("OPENAI_MODEL")
        or os.getenv("M2M2_MODEL")
        or os.getenv("OPENAI_MODEL")
        or preset.default_model
    )
    api_key = values.get("OPENAI_API_KEY") or os.getenv("OPENAI_API_KEY") or ""
    return LocalProviderConfig(provider_id=provider_id, base_url=base_url, model=model, api_key=api_key)


def save_local_config(payload: Mapping[str, Any], path: Path = DEFAULT_CONFIG_PATH) -> LocalProviderConfig:
    current = load_local_config(path)
    provider_id = str(payload.get("provider_id") or current.provider_id or "deepseek").strip()
    preset = _preset_by_id(provider_id) or _preset_by_id("custom") or PROVIDER_PRESETS[-1]
    base_url = str(payload.get("base_url") or preset.base_url or current.base_url).strip()
    model = str(payload.get("model") or preset.default_model or current.model).strip()
    incoming_key = str(payload.get("api_key") or "").strip()
    api_key = incoming_key if incoming_key and not incoming_key.startswith("***") else current.api_key

    config = LocalProviderConfig(provider_id=provider_id, base_url=base_url, model=model, api_key=api_key)
    _write_managed_env_values(
        path,
        {
            "M2M2_PROVIDER_ID": config.provider_id,
            "OPENAI_API_KEY": config.api_key,
            "OPENAI_BASE_URL": config.base_url,
            "M2M2_MODEL": config.model,
            "OPENAI_MODEL": config.model,
        },
    )
    return config


def public_config(path: Path = DEFAULT_CONFIG_PATH) -> dict[str, Any]:
    config = load_local_config(path)
    preset = _preset_by_id(config.provider_id)
    return {
        "presets": provider_presets(),
        "current": {
            "provider_id": config.provider_id,
            "provider_name": preset.name if preset else config.provider_id,
            "base_url": config.base_url,
            "model": config.model,
            "has_api_key": config.has_api_key,
            "api_key_mask": mask_secret(config.api_key),
        },
    }


def apply_provider_config_to_env(config: LocalProviderConfig) -> None:
    if config.api_key:
        os.environ["OPENAI_API_KEY"] = config.api_key
    if config.base_url:
        os.environ["OPENAI_BASE_URL"] = config.base_url
    if config.model:
        os.environ["M2M2_MODEL"] = config.model
        os.environ["OPENAI_MODEL"] = config.model
    if config.provider_id:
        os.environ["M2M2_PROVIDER_ID"] = config.provider_id


def mask_secret(secret: str) -> str:
    if not secret:
        return ""
    if len(secret) <= 8:
        return "*" * len(secret)
    return f"{secret[:4]}********{secret[-4:]}"


def _preset_by_id(provider_id: str) -> ProviderPreset | None:
    return next((preset for preset in PROVIDER_PRESETS if preset.id == provider_id), None)


def _read_env_values(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = _unquote_env_value(value.strip())
    return values


def _write_managed_env_values(path: Path, updates: Mapping[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    existing_lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    preserved_lines = [line for line in existing_lines if _line_key(line) not in MANAGED_KEYS]
    managed_lines = [f"{key}={_quote_env_value(value)}" for key, value in updates.items()]
    path.write_text("\n".join([*preserved_lines, *managed_lines]).strip() + "\n", encoding="utf-8")


def _line_key(line: str) -> str | None:
    stripped = line.strip()
    if not stripped or stripped.startswith("#") or "=" not in stripped:
        return None
    return stripped.split("=", 1)[0].strip()


def _quote_env_value(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def _unquote_env_value(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        value = value[1:-1]
    return value.replace('\\"', '"').replace("\\\\", "\\")
