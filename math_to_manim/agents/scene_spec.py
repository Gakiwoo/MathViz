"""Manim scene specification stage."""

from __future__ import annotations

import json

from math_to_manim.agents.base import StageAgent, mark_sdk_metadata, run_structured_sdk_agent
from math_to_manim.schemas import ManimAnimationSpec, ManimObjectSpec, ManimSceneSpec, VisualStoryboard


class SceneSpecAgent(StageAgent[VisualStoryboard, ManimSceneSpec]):
    name = "scene_spec"

    def run(self, storyboard: VisualStoryboard) -> ManimSceneSpec:
        if not self.config.deterministic:
            artifact = run_structured_sdk_agent(
                name="SceneSpecAgent",
                instructions=(
                    "Translate the storyboard into an implementable Manim CE scene spec. "
                    "Use one scene_name ending in Scene. Include concrete objects, animation "
                    "steps, camera/config notes, code requirements, and metadata with a timeline. "
                    "The spec must be practical for code generation, not just descriptive. "
                    "IMPORTANT: The codegen upstream will use this spec to generate Chinese-language animations. "
                    "Ensure text-related requirements specify Chinese content."
                    "CONCRETENESS REQUIREMENTS: "
                    "1. In objects, specify exact Manim types (Circle, Square, Polygon, Text, etc.) and their key properties (color, position hints). "
                    "2. In animations, specify exact Manim actions (Create, FadeIn, Transform, Write, Indicate, etc.) and which object target. "
                    "3. The timeline in metadata must describe what appears on screen for each segment — be as specific as possible. "
                    "4. code_requirements must list concrete LaTeX or text strings to display, not abstract goals. "
                    "5. Camera and config: specify background color, whether to use static or moving camera."
                ),
                prompt=json.dumps(storyboard.to_public_dict(), indent=2),
                model=self.config.model,
                output_type=ManimSceneSpec,
            )
            if artifact is not None:
                return mark_sdk_metadata(artifact, agent_name=self.name, model=self.config.model)

        class_name = "".join(part for part in storyboard.title.title() if part.isalnum()) or "GeneratedScene"
        if not class_name.endswith("Scene"):
            class_name += "Scene"
        timeline = []
        current = 0.0
        for scene in storyboard.scenes:
            duration = scene.duration_seconds or 0.0
            timeline.append(
                {
                    "start": current,
                    "duration": duration,
                    "title": scene.title,
                    "beats": scene.visual_actions,
                }
            )
            current += duration
        return ManimSceneSpec(
            scene_name=class_name,
            storyboard_scene_id=(storyboard.scenes[0].id if storyboard.scenes else None),
            imports=["from manim import *"],
            objects=[
                ManimObjectSpec(id="title", type="Text", properties={"font_size": 44}),
                ManimObjectSpec(id="formula", type="Text", properties={"font_size": 30}),
                ManimObjectSpec(id="takeaway", type="Text", properties={"font_size": 28}),
            ],
            animations=[
                ManimAnimationSpec(action="FadeIn", target="title", start_time=0, duration_seconds=1),
                ManimAnimationSpec(action="Write", target="formula", start_time=1, duration_seconds=2),
                ManimAnimationSpec(action="Write", target="takeaway", start_time=3, duration_seconds=2),
            ],
            camera={"plan": "static readable frame"},
            config={"background_color": "#0f172a", "quality_target": "low"},
            code_requirements=[
                "Use Manim Community Edition.",
                "Keep text readable and inside frame.",
                "Show a visual metaphor before formal notation.",
            ],
            metadata={
                "timeline": timeline,
                "render_command": f"python -m manim -ql generated_scene.py {class_name}",
            },
        )
