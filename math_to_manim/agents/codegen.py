"""Manim code generation stage."""

from __future__ import annotations

import json
from pathlib import Path

from math_to_manim.agents.base import StageAgent, mark_sdk_metadata, run_structured_sdk_agent
from math_to_manim.providers import CodexCliProvider
from math_to_manim.schemas import GeneratedCode, ManimSceneSpec


class ManimCodeAgent(StageAgent[ManimSceneSpec, GeneratedCode]):
    name = "codegen"

    def run(self, spec: ManimSceneSpec) -> GeneratedCode:
        if self.config.codegen_provider == "codex-cli" and not self.config.deterministic:
            return CodexCliProvider(self.config).generate_code(spec)

        if not self.config.deterministic:
            artifact = run_structured_sdk_agent(
                name="ManimCodeAgent",
                instructions=(
                    "Generate complete, runnable Manim Community Edition Python code from the scene spec. "
                    "Return only the GeneratedCode artifact. The code must import `from manim import *`, "
                    "define exactly the requested Scene class, avoid network/file IO, avoid custom external "
                    "assets, keep text readable, and implement real educational visuals from the spec. "
                    "Prefer robust Manim CE primitives: Axes, Dot, Line, always_redraw, ValueTracker, "
                    "Text, MarkupText, VGroup, Transform, FadeIn, Create. Use MathTex/Tex only when "
                    "LaTeX is confirmed available or explicitly requested; otherwise render formulas as "
                    "readable plain Text labels. "
                    "IMPORTANT Manim v0.20 API rules: RightAngle() requires Line objects, not vertex arrays. "
                    "Use RightAngle(Line(p1, p2), Line(p2, p3), ...) instead of RightAngle(v0, v1, v2, ...). "
                    "Do NOT use Checkmark — it does not exist in Manim CE. Use Text('✓', color=GREEN) instead. "
                    "Do not produce a generic title-card scaffold. Keep overlays sparse: no more than "
                    "two equation/text overlays visible in the same region, font sizes generally 24-40, "
                    "and use fixed corners or side panels so labels never overlap the curve, axes, or "
                    "each other. When animating labels, prefer FadeOut/FadeIn or ReplacementTransform "
                    "between compatible Text objects; avoid transforms that leave unreadable glyph "
                    "fragments. "
                    "IMPORTANT: ALL on-screen text must be in Chinese (Simplified). Use Chinese strings "
                    'for all Text(), MarkupText(), and MathTex() calls. For example: use Text("导数") instead '
                    'of Text("Derivative"). Equations and formulas can use standard mathematical notation. '
                    "The scene spec metadata contains 'requested_duration_seconds'. Write animations with "
                    "appropriate wait() calls and scene pacing to approximately fill the requested duration."
                    "ACCURACY REQUIREMENTS — strictly follow every detail in the scene spec: "
                    "1. Implement EVERY object listed in the spec 'objects' array with the specified type, properties, and positions. "
                    "2. Follow each animation step in the spec 'animations' array in order — each action (FadeIn/Create/Write/Transform) must match exactly. "
                    "3. The spec 'camera' and 'config' fields define screen layout — do not deviate. "
                    "4. Scene pacing: use wait() calls and run_time to match the spec's duration_seconds per animation. "
                    "5. If the spec has a 'timeline' in metadata, use each beat's 'beats' array as the visual action sequence for that segment. "
                    "6. Do NOT add extra scenes, objects, or animations not described in the spec."
                ),
                prompt=json.dumps(spec.to_public_dict(), indent=2),
                model=self.config.model,
                output_type=GeneratedCode,
            )
            if artifact is not None:
                artifact = mark_sdk_metadata(artifact, agent_name=self.name, model=self.config.model)
                if "file_path" not in artifact.metadata:
                    artifact = artifact.model_copy(
                        update={"metadata": {**artifact.metadata, "file_path": "generated_scene.py"}}
                    )
                return artifact

        code = _deterministic_scene_code(spec)
        return GeneratedCode(
            scene_name=spec.scene_name,
            code=code,
            dependencies=["manim"],
            source_spec_id=spec.storyboard_scene_id,
            metadata={
                "file_path": "generated_scene.py",
                "estimated_runtime_seconds": 30,
                "risk_notes": ["deterministic scaffold; replace with SDK code generation for production quality"],
            },
        )

    def repair(self, spec: ManimSceneSpec, generated: GeneratedCode, failure: str) -> GeneratedCode:
        """Repair generated Manim code after a static/render failure."""

        if self.config.deterministic:
            return generated
        if self.config.codegen_provider == "codex-cli":
            return CodexCliProvider(self.config).repair_code(spec, generated, failure)

        artifact = run_structured_sdk_agent(
            name="ManimRepairAgent",
            instructions=(
                "Repair a complete Manim Community Edition Python scene using the traceback. "
                "Return only a GeneratedCode artifact with the complete corrected file. Preserve "
                "the educational visual intent, scene class name, and dependencies. Make surgical "
                "fixes first. Avoid fragile or version-specific methods. In Manim CE 0.19, do not "
                "use add_fixed_in_frame_mobjects in MovingCameraScene; use normal mobjects, camera "
                "frame animation, or a compatible Scene/ThreeDScene choice instead. "
                "Checkmark does NOT exist in Manim CE — replace with Text('✓', color=GREEN). "
                "Also fix visible "
                "layout risks while repairing: remove overlapping labels, reduce crowded text, place "
                "formulas in stable corners/panels, and replace glitchy text transforms with clean "
                "FadeOut/FadeIn or ReplacementTransform. If the failure mentions missing LaTeX, replace "
                "MathTex/Tex with plain Text labels. Avoid file IO, network calls, and external assets. "
                "IMPORTANT: ALL on-screen text must remain in Chinese (Simplified). If any English text "
                "was introduced, replace it with Chinese."
                "ACCURACY: After repair, the scene must still implement every animation from the scene spec "
                "'animations' array in order. Do NOT remove or reorder visual steps — only fix bugs."
            ),
            prompt=json.dumps(
                {
                    "scene_spec": spec.to_public_dict(),
                    "generated_code": generated.to_public_dict(),
                    "failure": failure[-8000:],
                },
                indent=2,
            ),
            model=self.config.model,
            output_type=GeneratedCode,
        )
        if artifact is None:
            return generated
        artifact = mark_sdk_metadata(artifact, agent_name="repair", model=self.config.model)
        metadata = dict(artifact.metadata)
        metadata.setdefault("file_path", generated.metadata.get("file_path", "generated_scene.py"))
        metadata["repair_of"] = generated.scene_name
        return artifact.model_copy(update={"metadata": metadata})


def _deterministic_scene_code(spec: ManimSceneSpec) -> str:
    signal = _spec_signal(spec)
    if _has_any(signal, ("\u5e73\u884c", "\u76f8\u4ea4", "parallel", "intersect")):
        return _parallel_intersect_scene_code(spec.scene_name)
    if _has_any(signal, ("\u52fe\u80a1", "\u76f4\u89d2\u4e09\u89d2", "pythagorean")):
        return _pythagorean_scene_code(spec.scene_name)
    if _has_any(signal, ("\u5bfc\u6570", "\u659c\u7387", "derivative", "slope")):
        return _function_scene_code(spec.scene_name, "f'(a) = slope")
    if _has_any(signal, ("\u4e00\u6b21\u51fd\u6570", "\u51fd\u6570", "function", "linear")):
        return _function_scene_code(spec.scene_name, "y = kx + b")
    if _has_any(signal, ("\u76f8\u4f3c\u4e09\u89d2", "\u4e09\u89d2", "triangle", "similar")):
        return _triangle_comparison_scene_code(spec.scene_name)
    return _function_scene_code(spec.scene_name, "y = kx + b")


def _spec_signal(spec: ManimSceneSpec) -> str:
    parts = [
        spec.scene_name,
        str(spec.metadata.get("original_prompt", "")),
        " ".join(spec.code_requirements),
        " ".join(obj.id for obj in spec.objects),
    ]
    return " ".join(parts).lower()


def _has_any(text: str, needles: tuple[str, ...]) -> bool:
    return any(needle.lower() in text for needle in needles)


def _scene_lines(scene_name: str, body: list[str]) -> str:
    lines = [
        "from manim import *",
        "",
        "",
        f"class {scene_name}(Scene):",
        "    def construct(self):",
        "        self.camera.background_color = '#0f172a'",
    ]
    lines.extend(body)
    lines.append("        self.wait(1)")
    return "\n".join(lines) + "\n"


def _parallel_intersect_scene_code(scene_name: str) -> str:
    return _scene_lines(
        scene_name,
        [
            "        plane = NumberPlane(x_range=[-6, 6, 1], y_range=[-3, 3, 1], background_line_style={'stroke_opacity': 0.25})",
            "        parallel_a = Line(LEFT * 5 + UP * 1.4, RIGHT * 5 + UP * 1.4, color=BLUE_B, stroke_width=7)",
            "        parallel_b = Line(LEFT * 5 + UP * 0.4, RIGHT * 5 + UP * 0.4, color=BLUE_B, stroke_width=7)",
            "        intersect_a = Line(LEFT * 3.5 + DOWN * 1.8, RIGHT * 3.5 + UP * 1.8, color=YELLOW, stroke_width=7)",
            "        intersect_b = Line(LEFT * 3.5 + UP * 1.8, RIGHT * 3.5 + DOWN * 1.8, color=GREEN_B, stroke_width=7)",
            "        crossing = Dot(ORIGIN, color=RED, radius=0.08)",
            "        angle = Angle(intersect_a, intersect_b, radius=0.45, color=RED)",
            "        parallel_label = Text('\\u5e73\\u884c\\u7ebf\\uff1a\\u59cb\\u7ec8\\u4e0d\\u76f8\\u4ea4', font_size=28, color=BLUE_A).to_corner(UL)",
            "        intersect_label = Text('\\u76f8\\u4ea4\\u7ebf\\uff1a\\u5171\\u6709\\u4e00\\u4e2a\\u4ea4\\u70b9', font_size=28, color=YELLOW).to_corner(DL)",
            "        self.play(Create(plane), run_time=1)",
            "        self.play(Create(parallel_a), Create(parallel_b), run_time=1.5)",
            "        self.play(Write(parallel_label), run_time=1)",
            "        self.play(Create(intersect_a), Create(intersect_b), run_time=1.5)",
            "        self.play(FadeIn(crossing), Create(angle), Write(intersect_label), run_time=1)",
        ],
    )


def _pythagorean_scene_code(scene_name: str) -> str:
    return _scene_lines(
        scene_name,
        [
            "        a = np.array([-2.5, -1.4, 0])",
            "        b = np.array([1.5, -1.4, 0])",
            "        c = np.array([-2.5, 1.6, 0])",
            "        triangle = Polygon(a, b, c, color=WHITE, fill_color=BLUE_E, fill_opacity=0.35)",
            "        right_angle = RightAngle(Line(a, b), Line(a, c), length=0.35, color=YELLOW)",
            "        label_a = Text('a', font_size=34, color=BLUE_A).next_to(Line(a, c), LEFT)",
            "        label_b = Text('b', font_size=34, color=BLUE_A).next_to(Line(a, b), DOWN)",
            "        label_c = Text('c', font_size=34, color=RED_A).next_to(Line(b, c), RIGHT)",
            "        formula = Text('a\\u00b2 + b\\u00b2 = c\\u00b2', font_size=38, color=YELLOW).to_corner(UR)",
            "        self.play(Create(triangle), run_time=1.5)",
            "        self.play(Create(right_angle), Write(label_a), Write(label_b), Write(label_c), run_time=1.5)",
            "        self.play(Write(formula), run_time=1)",
        ],
    )


def _function_scene_code(scene_name: str, formula_text: str) -> str:
    return _scene_lines(
        scene_name,
        [
            "        axes = Axes(x_range=[-4, 4, 1], y_range=[-3, 5, 1], x_length=8, y_length=5.5, tips=True)",
            "        graph = axes.plot(lambda x: 0.55 * x + 1, x_range=[-3.5, 3.5], color=BLUE_B)",
            "        secant = Line(axes.c2p(-2, -0.1), axes.c2p(2, 2.1), color=YELLOW, stroke_width=6)",
            "        point_a = Dot(axes.c2p(-2, -0.1), color=YELLOW)",
            "        point_b = Dot(axes.c2p(2, 2.1), color=YELLOW)",
            f"        formula = Text({formula_text!r}, font_size=34, color=BLUE_A).to_corner(UR)",
            "        slope_label = Text('\\u659c\\u7387\\u8868\\u793a\\u53d8\\u5316\\u7387', font_size=28, color=YELLOW).to_corner(DL)",
            "        self.play(Create(axes), run_time=1)",
            "        self.play(Create(graph), run_time=1.5)",
            "        self.play(FadeIn(point_a), FadeIn(point_b), Create(secant), run_time=1)",
            "        self.play(Write(formula), Write(slope_label), run_time=1)",
        ],
    )


def _triangle_comparison_scene_code(scene_name: str) -> str:
    return _scene_lines(
        scene_name,
        [
            "        left = Polygon([-4, -1.5, 0], [-1.8, -1.5, 0], [-3.3, 0.7, 0], color=BLUE_B, fill_opacity=0.25)",
            "        right = Polygon([0.7, -1.5, 0], [4.0, -1.5, 0], [1.75, 1.8, 0], color=GREEN_B, fill_opacity=0.25)",
            "        mark_1 = Angle(Line(left.get_vertices()[0], left.get_vertices()[1]), Line(left.get_vertices()[0], left.get_vertices()[2]), color=YELLOW)",
            "        mark_2 = Angle(Line(right.get_vertices()[0], right.get_vertices()[1]), Line(right.get_vertices()[0], right.get_vertices()[2]), color=YELLOW)",
            "        relation = Text('\\u5bf9\\u5e94\\u89d2\\u76f8\\u7b49\\uff0c\\u5bf9\\u5e94\\u8fb9\\u6210\\u6bd4\\u4f8b', font_size=30, color=YELLOW).to_edge(DOWN)",
            "        self.play(Create(left), Create(right), run_time=1.5)",
            "        self.play(Create(mark_1), Create(mark_2), run_time=1)",
            "        self.play(Write(relation), run_time=1)",
        ],
    )


def write_generated_code(generated: GeneratedCode, run_dir: Path) -> Path:
    path = run_dir / str(generated.metadata.get("file_path", "generated_scene.py"))
    path.write_text(generated.code, encoding="utf-8")
    return path
