# MathViz Architecture

## Runtime shape

A single-threaded, ordered pipeline. Each stage produces a typed JSON artifact consumed by the next stage. The pipeline is linear, inspectable, and deterministic when `--deterministic` mode is active.

```
UserRequest → IntentAgent → ConceptIntent
           → PrerequisiteGraphAgent → KnowledgeGraph
           → CurriculumAgent → CurriculumPlan
           → MathAgent → MathPacket
           → StoryboardAgent → VisualStoryboard
           → SceneSpecAgent → ManimSceneSpec
           → ManimCodeAgent → GeneratedCode + generated_scene.py
           → StaticReviewAgent → ValidationReport
           → (repair loop if validation fails)
           → RenderAgent → RenderResult + .mp4
           → (repair loop if render fails)
           → VideoReviewAgent → VideoReviewReport
           → PublisherAgent → AnimationPackage + manifest.json
```

## Key decisions

**Story before symbols, geometry before algebra.** Planning stages (intent, graph, curriculum, math packet, storyboard) all execute before the first line of Manim code is generated. This means every stage can be inspected and edited before costly rendering.

**Artifacts before side effects.** Every stage writes its output as a JSON file under `runs/<run_id>/`. The Manim `.py` file is just one artifact among many. Rendering is gated by static validation — failed validation never invokes Manim.

**Deterministic offline baseline.** When `OPENAI_API_KEY` is absent or `--deterministic` is active, every agent falls back to a template-based or heuristic implementation. The pipeline still produces valid artifacts, just with lower visual quality. This makes the pipeline testable in CI without credentials.

## Component layout

```
math_to_manim/
├── agents/         # Pipeline stage adapters (one class per stage)
├── schemas/        # Pydantic artifact contracts (public pipeline interfaces)
├── pipeline/       # Orchestration, state, tracing, repair loops
├── tools/          # Deterministic helpers (AST validation, graph ops, scene discovery, Manim fixes)
├── rendering/      # Manim, FFmpeg, and render command wrappers
├── providers/      # Code-generation providers (OpenAI Agents SDK, Codex CLI, LLM helpers)
├── review/         # Video scoring and evaluation prompts
├── app/            # Teacher console (FastAPI + local_config + run_summary)
├── config.py       # RuntimeConfig dataclass
└── cli.py          # CLI entry points: generate, inspect-run
```

## Schema contracts

All schemas inherit from `ArtifactModel` (Pydantic v1/v2 dual-compatible). Key invariants enforced at validation time:

- `KnowledgeGraph`: no duplicate nodes, no dangling edges, no self-loops, no cycles in dependency relationships
- `ValidationReport`: status "passed" cannot contain error-severity issues
- `RenderResult`: status "skipped" indicates intentional skip; "failed" indicates actual failure

## Provider architecture

Three code-generation paths share the `GeneratedCode` contract:

| Provider | Path | Used when |
|---|---|---|
| OpenAI Agents SDK | `run_structured_sdk_agent()` → `AgentOutputSchema` | `OPENAI_API_KEY` set, `OPENAI_BASE_URL` is api.openai.com |
| Third-party (Chat Completions) | `run_third_party_structured()` → json_object mode with retry+JSON repair | Third-party base URL (DeepSeek, Qwen, Kimi, GLM, etc.) |
| Codex CLI | `CodexCliProvider.generate_code()` → `codex exec` | `--codegen-provider codex-cli` |

## Deterministic fallback summary

| Stage | Fallback behavior |
|---|---|
| IntentAgent | Derives core concept from prompt text using Chinese-aware heuristics |
| PrerequisiteGraphAgent | Uses hardcoded prerequisite lists for known topics (derivative, Pythagorean, etc.) |
| CurriculumAgent | Topological sort of graph nodes → numbered steps |
| MathAgent | Topic-specific equation selection (derivative → slope formulas) |
| StoryboardAgent | Topic-specific scene titles using curriculum_title |
| SceneSpecAgent | Storyboard metadata → Manim object list |
| ManimCodeAgent | Signal-based scene template selection (6 templates) |
| Repair | Codegen agent re-invoked with failure context (max 3 attempts) |
