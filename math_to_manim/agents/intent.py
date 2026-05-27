"""Concept intent stage."""

from __future__ import annotations

import json

from math_to_manim.agents.base import StageAgent, mark_sdk_metadata, run_structured_sdk_agent
from math_to_manim.schemas import ConceptIntent, UserRequest


class IntentAgent(StageAgent[UserRequest, ConceptIntent]):
    name = "intent"

    def run(self, request: UserRequest) -> ConceptIntent:
        if not self.config.deterministic:
            artifact = run_structured_sdk_agent(
                name="ConceptIntentAgent",
                instructions=(
                    "You identify the educational intent behind a math/science animation request. "
                    "Return a compact ConceptIntent. Include prerequisites, learning objectives, "
                    "likely misconceptions, and target audience. Keep it useful for downstream "
                    "visual storyboarding. "
                    "IMPORTANT: All user-facing text (learning objectives, prerequisites, etc.) must be in Chinese (Simplified)."
                ),
                prompt=json.dumps(request.to_public_dict(), indent=2),
                model=self.config.model,
                output_type=ConceptIntent,
            )
            if artifact is not None:
                return mark_sdk_metadata(artifact, agent_name=self.name, model=self.config.model)

        prompt = request.prompt.strip()
        core = _derive_core_concept(prompt)
        domain = _guess_domain(core)
        return ConceptIntent(
            primary_concept=core,
            related_concepts=[],
            prerequisites=_default_prerequisites(core),
            learning_objectives=[f"Explain {core} with a concrete visual intuition."],
            misconceptions=[
                "visual approximations are not automatically formal proofs",
                "symbols should not appear before the learner sees what changes",
            ],
            target_audience=request.target_audience,
            metadata={
                "domain": domain,
                "aha_moment": _guess_aha(core),
                "visual_potential": "high",
                "success_criteria": [
                    "target concept appears in the title",
                    "visual metaphor is shown before formal notation",
                    "final scene states the core takeaway",
                ],
            },
        )


def _derive_core_concept(prompt: str) -> str:
    lowered = prompt.lower()
    for prefix in ("explain why ", "explain ", "show why ", "show ", "visualize ", "animate "):
        if lowered.startswith(prefix):
            return _strip_formula_chars(prompt[len(prefix) :].strip(" ."))
    # Chinese prompt: extract the core concept from quotes or first clause
    import re

    stripped = prompt.strip(" .，。！？；、")
    # Try content inside Chinese/smart quotes: "导数为什么是切线斜率"
    quoted = re.findall(r'[\u201c\u201d""""]([^""""\u201c\u201d]{2,40})[\u201c\u201d""""]', stripped)
    if quoted:
        return _strip_formula_chars(quoted[0].strip())
    # Take first sentence/clause before punctuation
    clause = re.split(r"[，。！？；、]", stripped, maxsplit=1)[0].strip()
    # Heuristic: for Chinese prompts like "给初一学生解释XXX", extract after 解释/讲解/理解
    for marker in ("解释", "讲解", "理解", "介绍", "说明", "展示"):
        if marker in clause:
            idx = clause.index(marker) + len(marker)
            rest = clause[idx:].strip()
            if rest and len(rest) < len(clause):
                return _strip_formula_chars(rest)
    # Fallback: limit to 36 characters to keep scene names readable
    return _strip_formula_chars(clause[:36] or stripped[:36])


def _strip_formula_chars(text: str) -> str:
    """Remove mathematical formula characters from concept names.

    Keeps Chinese characters, ASCII letters/digits, and common punctuation.
    Strips superscript/subscript (²³¹⁰ⁿₓ), math operators (×÷±≈≠≡≤≥∞∫∑∏√),
    and Greek letters that shouldn't appear in scene titles.
    Also removes trailing formula fragments like " a + b = c" after the concept name.
    """
    import re

    # 1. Remove common math notation: superscript/subscript, greek, operators
    cleaned = re.sub(
        r"[\u00b2\u00b3\u00b9\u2070\u2071\u2074-\u207f\u2080-\u208e]"  # superscript/subscript
        r"|[\u00d7\u00f7\u00b1\u2248\u2260\u2261\u2264\u2265\u221e]"  # math operators
        r"|[\u222b\u2211\u220f\u221a\u03b1-\u03c9]"  # integral/sum/product/sqrt/greek
        r"|[\u2190-\u21ff]",  # arrows
        "",
        text,
    ).strip()
    # 2. Trim trailing formula fragments: find first ASCII math expression after Chinese text
    #    Pattern: a space + letter + operator (=/-/+) signals start of formula
    match = re.search(r"\s[a-zA-Z]+\s*[+*/=<>\-]", cleaned)
    if match:
        cleaned = cleaned[: match.start()].strip()
    return cleaned or "数学概念"


def _guess_domain(core: str) -> str:
    text = core.lower()
    if any(term in text for term in ("derivative", "limit", "integral", "slope", "series")):
        return "calculus"
    if any(term in text for term in ("vector", "matrix", "eigen", "linear")):
        return "linear_algebra"
    if any(term in text for term in ("gravity", "quantum", "spacetime", "field")):
        return "physics"
    if any(term in text for term in ("gradient", "neural", "policy", "optimization")):
        return "machine_learning"
    return "mathematics"


def _guess_aha(core: str) -> str:
    text = core.lower()
    if "derivative" in text or "slope" in text:
        return "A secant line becomes a tangent line as the interval shrinks."
    if "pythagorean" in text:
        return "The square on the hypotenuse contains the same area as the two leg squares."
    return f"The abstract idea of {core} becomes visible as a sequence of simple transformations."


def _default_prerequisites(core: str) -> list[str]:
    text = core.lower()
    if "derivative" in text or "slope" in text:
        return ["functions and graphs", "slope of a line", "secant lines", "limits"]
    if "pythagorean" in text:
        return ["right triangles", "area of squares", "congruence", "similarity"]
    if "fourier" in text:
        return ["periodic motion", "sine and cosine", "vectors in the plane", "superposition"]
    if "lorenz" in text:
        return ["differential equations", "phase space", "sensitive dependence", "trajectories"]
    return ["basic notation", "visual model", "core definition", "worked example"]
