"""Third-party LLM provider helpers.

Shared utilities for calling OpenAI-compatible APIs through the Agents SDK
(with structured output) or directly via the OpenAI client (for third-party
providers that don't support json_schema response_format).
"""

from __future__ import annotations

import json
import os
from typing import Any

from math_to_manim.config import load_env_file


def _is_third_party_provider() -> bool:
    base_url = os.getenv("OPENAI_BASE_URL", "")
    return bool(base_url) and "api.openai.com" not in base_url


def _ensure_tracing_disabled() -> None:
    if not _is_third_party_provider():
        return
    try:
        from agents import set_tracing_disabled

        set_tracing_disabled(True)
    except (ImportError, ModuleNotFoundError):
        pass


def _get_model_for_provider(model: str):
    """Return the right Model implementation for the configured provider.

    When OPENAI_BASE_URL points to a third-party OpenAI-compatible provider,
    use Chat Completions API; otherwise default to the SDK's built-in provider
    (Responses API for OpenAI).
    """

    if not _is_third_party_provider():
        return model

    try:
        from agents.models.openai_chatcompletions import OpenAIChatCompletionsModel
        from openai import AsyncOpenAI
    except ImportError:
        return model

    client = AsyncOpenAI(base_url=os.getenv("OPENAI_BASE_URL"), api_key=os.getenv("OPENAI_API_KEY"))
    return OpenAIChatCompletionsModel(model=model, openai_client=client)


def _repair_truncated_json(text: str) -> dict | None:
    """Attempt to repair truncated or malformed JSON from LLM output."""
    if not text:
        return None

    # Remove trailing commas before closing brackets/braces
    import re

    text = re.sub(r",\s*([}\]])", r"\1", text)

    # If the JSON looks truncated (unbalanced braces/brackets), try to close it
    open_braces = text.count("{") - text.count("}")
    open_brackets = text.count("[") - text.count("]")

    if open_braces > 0 or open_brackets > 0:
        # Check if we're inside a string (odd number of unescaped quotes)
        in_string = False
        i = 0
        while i < len(text):
            ch = text[i]
            if ch == "\\":
                i += 2
                continue
            if ch == '"':
                in_string = not in_string
            i += 1
        if in_string:
            text += '"'

        # Close any open structures
        # First close arrays, then objects
        text += "]" * open_brackets
        text += "}" * open_braces

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Last resort: try to find the last valid complete object
    for i in range(len(text) - 1, 0, -1):
        if text[i] in ("}", "]"):
            try:
                return json.loads(text[: i + 1])
            except json.JSONDecodeError:
                continue
    return None


def _strip_nulls(obj: Any) -> Any:
    """Recursively remove keys with null values from dicts."""
    if isinstance(obj, dict):
        return {k: _strip_nulls(v) for k, v in obj.items() if v is not None}
    if isinstance(obj, list):
        return [_strip_nulls(item) for item in obj]
    return obj


def _provider_extra_body() -> dict[str, Any] | None:
    provider_id = os.getenv("M2M2_PROVIDER_ID", "").lower()
    base_url = os.getenv("OPENAI_BASE_URL", "").lower()
    if "deepseek" not in provider_id and "deepseek" not in base_url:
        return None
    if os.getenv("M2M2_DEEPSEEK_DISABLE_THINKING", "1") in {"0", "false", "False"}:
        return None
    return {"thinking": {"type": "disabled"}}


def _summarize_schema_props(schema: dict, defs: dict | None = None, indent: int = 0) -> str:
    """Build a human-readable summary of a JSON schema's properties."""

    if defs is None:
        defs = schema.get("$defs", {})

    prefix = "  " * indent
    props = schema.get("properties", {})
    required = set(schema.get("required", []))

    if not props:
        return f"{prefix}(any valid JSON)"

    lines = []
    for prop_name, prop_info in props.items():
        req_mark = " (REQUIRED)" if prop_name in required else ""
        prop_type = prop_info.get("type", "any")
        ref = prop_info.get("$ref", "")

        if ref:
            ref_key = ref.split("/")[-1]
            ref_schema = defs.get(ref_key, {})
            ref_type = ref_schema.get("type", "object")
            if ref_type == "object":
                sub = _summarize_schema_props(ref_schema, defs, indent + 1)
                lines.append(f'{prefix}- "{prop_name}": object ({ref_key}){req_mark}\n{sub}')
            else:
                lines.append(f'{prefix}- "{prop_name}": {ref_type}{req_mark}')
        elif prop_type == "array":
            items = prop_info.get("items", {})
            items_ref = items.get("$ref", "")
            if items_ref:
                ref_key = items_ref.split("/")[-1]
                ref_schema = defs.get(ref_key, {})
                sub = _summarize_schema_props(ref_schema, defs, indent + 1)
                lines.append(f'{prefix}- "{prop_name}": array of {ref_key}{req_mark}\n{sub}')
            elif items.get("type") == "object":
                sub = _summarize_schema_props(items, defs, indent + 1)
                lines.append(f'{prefix}- "{prop_name}": array of objects{req_mark}\n{sub}')
            else:
                lines.append(f'{prefix}- "{prop_name}": array of {items.get("type", "string")}{req_mark}')
        elif prop_type == "object":
            sub = _summarize_schema_props(prop_info, defs, indent + 1)
            lines.append(f'{prefix}- "{prop_name}": object{req_mark}\n{sub}')
        else:
            enum_vals = prop_info.get("enum")
            if enum_vals:
                lines.append(f'{prefix}- "{prop_name}": one of {enum_vals}{req_mark}')
            else:
                lines.append(f'{prefix}- "{prop_name}": {prop_type}{req_mark}')

    return "\n".join(lines)


def run_third_party_structured(
    *,
    name: str,
    instructions: str,
    prompt: str,
    model: str,
    output_type: type,
) -> Any:
    """Use json_object response_format via direct client call for reliability.

    Bypasses the Agents SDK for the LLM call because third-party providers
    don't support the json_schema response_format that the SDK uses for
    structured outputs.
    """

    from openai import OpenAI

    load_env_file()

    schema = output_type.model_json_schema()
    # Provide the model with a compact schema summary
    required = schema.get("required", [])
    defs = schema.get("$defs", {})
    props_summary = _summarize_schema_props(schema, defs)

    system_msg = (
        f"{instructions}\n\n"
        f"You MUST output valid JSON. Required top-level keys: {', '.join(required)}\n"
        f"IMPORTANT: Do NOT flatten nested structures. Keep each field at its correct level.\n\n"
        f"Schema:\n{props_summary}\n\n"
        f"For reference, the complete JSON Schema:\n"
        f"{json.dumps(schema, indent=2, ensure_ascii=False)}\n\n"
        f"Output ONLY the JSON object, no markdown, no extra text."
    )

    client = OpenAI(
        base_url=os.getenv("OPENAI_BASE_URL"),
        api_key=os.getenv("OPENAI_API_KEY"),
        timeout=float(os.getenv("M2M2_LLM_TIMEOUT_SECONDS", "45")),
    )
    max_tokens = int(os.getenv("M2M2_LLM_MAX_TOKENS", "12000"))
    extra_body = _provider_extra_body()

    last_error = None
    for attempt in range(3):
        request_kwargs: dict[str, Any] = {}
        if extra_body:
            request_kwargs["extra_body"] = extra_body
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_msg},
                {"role": "user", "content": prompt},
            ],
            response_format={"type": "json_object"},
            temperature=0.7,
            max_tokens=max_tokens,
            **request_kwargs,
        )
        text = response.choices[0].message.content.strip()
        finish_reason = getattr(response.choices[0], "finish_reason", "")
        # Strip markdown fences if present
        if text.startswith("```"):
            lines = text.split("\n")
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            text = "\n".join(lines).strip()
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            parsed = _repair_truncated_json(text)
            if parsed is None:
                last_error = ValueError(
                    f"Failed to parse JSON from model response (attempt {attempt + 1}/3). "
                    f"finish_reason={finish_reason}, text[-200:]: {text[-200:]}"
                )
                if attempt < 2:
                    continue
                raise last_error
        parsed = _strip_nulls(parsed)
        return output_type.model_validate(parsed)

    raise last_error  # type: ignore[misc]
