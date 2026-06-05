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

        # Derive topic-aware objects and animations from the first scene's metadata
        first_scene = storyboard.scenes[0] if storyboard.scenes else None
        scene_objects = first_scene.metadata.get("objects", []) if first_scene else []
        equation_overlays = first_scene.metadata.get("equation_overlays", []) if first_scene else []

        objects: list[ManimObjectSpec] = [ManimObjectSpec(id="title", type="Text", properties={"font_size": 44})]
        if "axes" in str(scene_objects).lower() or "坐标" in str(scene_objects):
            objects.append(ManimObjectSpec(id="axes", type="Axes", properties={"x_range": [-4, 4], "y_range": [-3, 5]}))
        if "curve" in str(scene_objects).lower() or "图形" in str(scene_objects):
            objects.append(ManimObjectSpec(id="graph", type="ParametricFunction", properties={"color": "BLUE_B"}))
        for idx, _ in enumerate(equation_overlays):
            objects.append(
                ManimObjectSpec(id=f"formula_{idx}", type="Text", properties={"font_size": 30, "color": "BLUE_A"})
            )
        objects.append(ManimObjectSpec(id="takeaway", type="Text", properties={"font_size": 28, "color": "YELLOW"}))

        timeline = []
        current = 0.0
        animations: list[ManimAnimationSpec] = []
        for scene in storyboard.scenes:
            duration = scene.duration_seconds or 8.0
            timeline.append(
                {
                    "start": current,
                    "duration": duration,
                    "title": scene.title,
                    "beats": scene.visual_actions,
                }
            )
            obj_targets = [obj.id for obj in objects if obj.id != "title"]
            beat_objs = obj_targets[: len(scene.visual_actions)] if obj_targets else ["formula_0"]
            for beat_idx, _ in enumerate(scene.visual_actions):
                target = beat_objs[beat_idx % len(beat_objs)]
                animations.append(
                    ManimAnimationSpec(
                        action="FadeIn" if beat_idx == 0 else "Write",
                        target=target,
                        start_time=current,
                        duration_seconds=max(1.0, duration / len(scene.visual_actions)),
                    )
                )
            current += duration

        # Ensure at least one animation if scenes are empty
        if not animations:
            animations = [
                ManimAnimationSpec(action="FadeIn", target="title", start_time=0, duration_seconds=1),
                ManimAnimationSpec(action="Write", target="takeaway", start_time=1, duration_seconds=2),
            ]

        return ManimSceneSpec(
            scene_name=class_name,
            storyboard_scene_id=(storyboard.scenes[0].id if storyboard.scenes else None),
            imports=["from manim import *"],
            objects=objects,
            animations=animations,
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
