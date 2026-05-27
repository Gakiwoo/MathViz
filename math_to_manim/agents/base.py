"""Shared agent adapter primitives.

The production path is OpenAI Agents SDK-compatible, while tests and offline
development can use deterministic stage implementations with the same artifact
contracts.
"""

from __future__ import annotations

import json
import os
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Generic, TypeVar

from math_to_manim.config import RuntimeConfig, load_env_file

InputT = TypeVar("InputT")
OutputT = TypeVar("OutputT")


@dataclass
class AgentInvocation:
    """Trace metadata for a single agent stage call."""

    agent_name: str
    model: str
    used_sdk: bool
    metadata: dict[str, Any] = field(default_factory=dict)


class StageAgent(Generic[InputT, OutputT]):
    """Base class for typed pipeline stages."""

    name = "stage"

    def __init__(self, config: RuntimeConfig | None = None):
        self.config = config or RuntimeConfig.from_env()

    def run(self, value: InputT) -> OutputT:
        raise NotImplementedError

    def invocation(self, *, used_sdk: bool = False, **metadata: Any) -> AgentInvocation:
        return AgentInvocation(
            agent_name=self.name,
            model=self.config.model,
            used_sdk=used_sdk,
            metadata=metadata,
        )


def load_openai_agents_sdk() -> dict[str, Any] | None:
    """Load OpenAI Agents SDK symbols across observed package layouts.

    The installed package is `openai-agents`; some environments expose
    top-level symbols from `agents`, while others require submodule imports.
    """

    try:
        from agents import Agent, Runner, function_tool, handoff  # type: ignore

        return {
            "Agent": Agent,
            "Runner": Runner,
            "function_tool": function_tool,
            "handoff": handoff,
        }
    except Exception:
        pass

    try:
        from agents.agent import Agent  # type: ignore
        from agents.handoffs import handoff  # type: ignore
        from agents.run import Runner  # type: ignore
        from agents.tool import function_tool  # type: ignore

        return {
            "Agent": Agent,
            "Runner": Runner,
            "function_tool": function_tool,
            "handoff": handoff,
        }
    except Exception:
        return None


def _is_third_party_provider() -> bool:
    base_url = os.getenv("OPENAI_BASE_URL", "")
    return bool(base_url) and "api.openai.com" not in base_url


def _ensure_tracing_disabled() -> None:
    if not _is_third_party_provider():
        return
    try:
        from agents import set_tracing_disabled

        set_tracing_disabled(True)
    except Exception:
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


def maybe_run_sdk_agent(
    *,
    name: str,
    instructions: str,
    prompt: str,
    model: str,
    output_parser: Callable[[str], OutputT],
) -> OutputT | None:
    """Run a simple SDK agent when credentials and imports are available.

    This intentionally returns ``None`` instead of raising for missing optional
    runtime state. The deterministic pipeline remains the offline baseline.
    """

    load_env_file()
    if not os.getenv("OPENAI_API_KEY"):
        return None

    _ensure_tracing_disabled()

    sdk = load_openai_agents_sdk()
    if sdk is None:
        return None

    Agent = sdk["Agent"]  # noqa: N806
    Runner = sdk["Runner"]  # noqa: N806
    resolved_model = _get_model_for_provider(model)
    agent = Agent(name=name, instructions=instructions, model=resolved_model)
    result = Runner.run_sync(agent, prompt)
    output = getattr(result, "final_output", result)
    if not isinstance(output, str):
        output = json.dumps(output)
    return output_parser(output)


def run_structured_sdk_agent(
    *,
    name: str,
    instructions: str,
    prompt: str,
    model: str,
    output_type: type[OutputT],
) -> OutputT | None:
    """Run an OpenAI Agents SDK stage and return a typed artifact.

    Returns ``None`` only when the SDK or API key is unavailable. If credentials
    exist and the stage fails, the exception is allowed to surface because a
    silent deterministic fallback would hide that the real chain did not run.
    """

    load_env_file()
    if not os.getenv("OPENAI_API_KEY"):
        return None

    _ensure_tracing_disabled()

    sdk = load_openai_agents_sdk()
    if sdk is None:
        return None

    Agent = sdk["Agent"]  # noqa: N806
    Runner = sdk["Runner"]  # noqa: N806
    resolved_model = _get_model_for_provider(model)

    if _is_third_party_provider():
        # Third-party providers don't support json_schema response_format.
        # Use json_object mode via direct OpenAI client call for reliability.
        return _run_third_party_structured(
            name=name,
            instructions=instructions,
            prompt=prompt,
            model=model,
            output_type=output_type,
        )

    # OpenAI native path: use structured output with json_schema response_format
    from agents.agent_output import AgentOutputSchema  # type: ignore

    agent = Agent(
        name=name,
        instructions=instructions,
        model=resolved_model,
        output_type=AgentOutputSchema(output_type, strict_json_schema=False),
    )
    result = Runner.run_sync(agent, prompt)
    output = getattr(result, "final_output", result)
    if isinstance(output, output_type):
        return output
    return output_type.model_validate(output)


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


def _run_third_party_structured(
    *,
    name: str,
    instructions: str,
    prompt: str,
    model: str,
    output_type: type[OutputT],
) -> OutputT:
    """Use json_object response_format via direct client call for reliability.

    Bypasses the Agents SDK for the LLM call because third-party providers
    don't support the json_schema response_format that the SDK uses for
    structured outputs.
    """

    from openai import OpenAI

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


def mark_sdk_metadata(artifact: OutputT, *, agent_name: str, model: str) -> OutputT:
    """Annotate a Pydantic artifact with runtime provenance metadata."""

    metadata = dict(getattr(artifact, "metadata", {}) or {})
    metadata.update(
        {
            "source_agent": agent_name,
            "runtime": "openai_agents_sdk",
            "model": model,
        }
    )
    return artifact.model_copy(update={"metadata": metadata})  # type: ignore[return-value]
