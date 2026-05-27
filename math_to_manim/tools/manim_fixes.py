"""Manim code fix-up utilities for AI-generated scenes.

These are used before rendering to repair common Manim API misuse
patterns introduced by code-generation models.
"""

from __future__ import annotations

import ast
import re
from typing import Any

from math_to_manim.rendering.commands import resolve_binary
from math_to_manim.schemas import GeneratedCode

LATEX_TEXT_CALLS = {"MathTex", "Tex", "SingleStringMathTex"}
TEXT_UNSAFE_KWARGS = {"arg_separator", "substrings_to_isolate", "tex_environment", "tex_template"}


def fix_manim_common_issues(generated: GeneratedCode) -> GeneratedCode:
    """Fix common Manim API misuse patterns in AI-generated code before rendering.

    Known fixes:
    - RightAngle(vertex1, vertex2, vertex3) → RightAngle(Line(v1,v2), Line(v2,v3))
    - TransformMatchingTex(a, b) → ReplacementTransform(a, b)
    - MathTex/Tex/SingleStringMathTex/BulletedList → Text/VGroup when dvisvgm is missing
    - Checkmark(...) → Text("✓", ...) — Checkmark is not a Manim CE class
    """
    code = generated.code
    original = code

    # Fix 1: RightAngle(vertex arrays) → RightAngle(Line(...), Line(...))
    def _fix_rightangle(m: re.Match) -> str:
        indent = m.group(1)
        var = m.group(2)
        i0, i1, i2 = m.group(3), m.group(4), m.group(5)
        rest = m.group(6) if m.lastindex >= 6 else ""
        arg_indent = indent + " " * 4
        return (
            f"RightAngle(\n"
            f"{arg_indent}Line({var}.get_vertices()[{i0}], {var}.get_vertices()[{i1}]),\n"
            f"{arg_indent}Line({var}.get_vertices()[{i1}], {var}.get_vertices()[{i2}]){rest}"
        )

    code = re.sub(
        r"RightAngle\(\s*\n(\s+)(\w+)\.get_vertices\(\)\[(\d+)\],\s*\n\s+\2\.get_vertices\(\)\[(\d+)\],\s*\n\s+\2\.get_vertices\(\)\[(\d+)\](,[^)]*\))",
        _fix_rightangle,
        code,
    )

    # Fix 2: TransformMatchingTex → ReplacementTransform (works with any mobject)
    code = re.sub(r"\bTransformMatchingTex\b", "ReplacementTransform", code)

    # Fix 4: Checkmark is not a Manim CE class — replace with Text("✓", ...)
    code = re.sub(r"\bCheckmark\s*\(", 'Text("✓", ', code)

    # Fix 3: AST-based rewrite of LaTeX-backed calls when dvisvgm is missing
    changed_by_regex = code != original

    if resolve_binary("dvisvgm") is None or resolve_binary("latex") is None:
        try:
            tree = ast.parse(code)
        except SyntaxError:
            pass
        else:
            transformer = _LatexTextToPlainText()
            transformed = transformer.visit(tree)
            if transformer.changed:
                ast.fix_missing_locations(transformed)
                metadata = dict(generated.metadata)
                metadata["manim_fixes_applied"] = True
                metadata["tex_fallback"] = True
                metadata["tex_fallback_calls"] = sorted(transformer.rewritten_calls)
                return generated.model_copy(update={"code": ast.unparse(transformed) + "\n", "metadata": metadata})

    if changed_by_regex:
        metadata = dict(generated.metadata)
        metadata["manim_fixes_applied"] = True
        return generated.model_copy(update={"code": code, "metadata": metadata})
    return generated


def preview_safe_generated_code(generated: GeneratedCode) -> GeneratedCode:
    """Rewrite LaTeX-backed text calls to Text for low-preview reliability."""

    try:
        tree = ast.parse(generated.code)
    except SyntaxError:
        return generated
    transformer = _LatexTextToPlainText()
    transformed = transformer.visit(tree)
    if not transformer.changed:
        return generated
    ast.fix_missing_locations(transformed)
    metadata = dict(generated.metadata)
    metadata["preview_safe_latex_rewrite"] = True
    metadata["preview_safe_latex_calls"] = sorted(transformer.rewritten_calls)
    return generated.model_copy(update={"code": ast.unparse(transformed) + "\n", "metadata": metadata})


class _LatexTextToPlainText(ast.NodeTransformer):
    """AST transformer that rewrites LaTeX-backed calls to plain Text equivalents.

    Rewrites:
    - MathTex/Tex/SingleStringMathTex → Text (strips tex-specific kwargs)
    - BulletedList → VGroup (wraps string args in Text())
    """

    def __init__(self) -> None:
        self.changed = False
        self.rewritten_calls: set[str] = set()

    def visit_Call(self, node: ast.Call) -> Any:
        node = self.generic_visit(node)
        name = _call_name(node.func)
        if name in LATEX_TEXT_CALLS:
            self.changed = True
            self.rewritten_calls.add(name)
            node.func = _replace_call_name(node.func, "Text")
            node.args = _plain_text_args(node.args)
        elif name == "BulletedList":
            self.changed = True
            self.rewritten_calls.add(name)
            node.func = _replace_call_name(node.func, "VGroup")
            node.args = [
                ast.Call(func=ast.Name(id="Text", ctx=ast.Load()), args=[arg], keywords=[])
                if isinstance(arg, ast.Constant) and isinstance(arg.value, str)
                else arg
                for arg in node.args
            ]
        else:
            return node
        node.keywords = [kw for kw in node.keywords if kw.arg not in TEXT_UNSAFE_KWARGS]
        return node


def _plain_text_args(args: list[ast.expr]) -> list[ast.expr]:
    if len(args) <= 1:
        return args
    if all(isinstance(arg, ast.Constant) and isinstance(arg.value, str) for arg in args):
        return [ast.Constant(value=" ".join(str(arg.value) for arg in args if isinstance(arg, ast.Constant)))]
    return args[:1]


def _call_name(node: ast.expr) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return None


def _replace_call_name(node: ast.expr, replacement: str) -> ast.expr:
    if isinstance(node, ast.Name):
        return ast.Name(id=replacement, ctx=node.ctx)
    if isinstance(node, ast.Attribute):
        return ast.Attribute(value=node.value, attr=replacement, ctx=node.ctx)
    return node
