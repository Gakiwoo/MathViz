"""Tests for manim_fixes — code fix-up utilities for AI-generated scenes."""

from __future__ import annotations

import ast

from math_to_manim.schemas import GeneratedCode
from math_to_manim.tools.manim_fixes import (
    _LatexTextToPlainText,
    fix_manim_common_issues,
    preview_safe_generated_code,
)


def _make_generated(code: str) -> GeneratedCode:
    return GeneratedCode(scene_name="TestScene", code=code)


class TestFixManimCommonIssues:
    def test_fix_checkmark_replaced_with_text(self) -> None:
        gen = _make_generated("from manim import *\nclass TestScene(Scene):\n    check = Checkmark()")
        fixed = fix_manim_common_issues(gen)
        assert "Checkmark" not in fixed.code
        assert 'Text("✓"' in fixed.code
        assert fixed.metadata.get("manim_fixes_applied") is True

    def test_fix_transform_matching_tex_replaced(self) -> None:
        gen = _make_generated("from manim import *\nself.play(TransformMatchingTex(a, b))")
        fixed = fix_manim_common_issues(gen)
        assert "TransformMatchingTex" not in fixed.code
        assert "ReplacementTransform" in fixed.code

    def test_no_fix_needed_when_code_is_clean(self) -> None:
        gen = _make_generated("from manim import *\nclass TestScene(Scene):\n    pass\n")
        fixed = fix_manim_common_issues(gen)
        assert fixed.code == gen.code
        assert fixed.metadata.get("manim_fixes_applied") is not True

    def test_syntax_error_code_is_unchanged(self) -> None:
        gen = _make_generated("this is not valid python {{{")
        fixed = fix_manim_common_issues(gen)
        assert fixed.code == gen.code


class TestPreviewSafeGeneratedCode:
    def test_mathtex_rewritten_to_text(self) -> None:
        gen = _make_generated(
            "from manim import *\nclass Demo(Scene):\n    def construct(self):\n        eq = MathTex(r'x^2')\n"
        )
        fixed = preview_safe_generated_code(gen)
        assert "MathTex" not in fixed.code
        assert "Text" in fixed.code
        assert fixed.metadata.get("preview_safe_latex_rewrite") is True

    def test_bulletedlist_rewritten_to_vgroup(self) -> None:
        gen = _make_generated(
            "from manim import *\nclass Demo(Scene):\n    def construct(self):\n        bl = BulletedList('a', 'b', 'c')\n"
        )
        fixed = preview_safe_generated_code(gen)
        assert "BulletedList" not in fixed.code
        assert "VGroup" in fixed.code

    def test_no_change_when_no_latex_calls(self) -> None:
        gen = _make_generated(
            "from manim import *\nclass Demo(Scene):\n    def construct(self):\n        t = Text('hello')\n"
        )
        fixed = preview_safe_generated_code(gen)
        assert fixed.code == gen.code

    def test_syntax_error_returns_unchanged(self) -> None:
        gen = _make_generated("def broken(")
        fixed = preview_safe_generated_code(gen)
        assert fixed.code == gen.code


class TestTexToPlainTextTransformer:
    def test_mathtex_to_text(self) -> None:
        code = "from manim import *\neq = MathTex(r'x^2')"
        tree = ast.parse(code)
        transformer = _LatexTextToPlainText()
        transformed = transformer.visit(tree)
        result = ast.unparse(transformed)
        assert "MathTex(" not in result
        assert "Text(" in result
        assert transformer.changed is True

    def test_tex_to_text(self) -> None:
        code = "from manim import *\neq = Tex(r'a+b=c')"
        tree = ast.parse(code)
        transformer = _LatexTextToPlainText()
        transformed = transformer.visit(tree)
        result = ast.unparse(transformed)
        assert "Tex(" not in result
        assert "Text(" in result
        assert transformer.changed is True

    def test_bulletedlist_to_vgroup(self) -> None:
        code = "from manim import *\nbl = BulletedList('a', 'b')"
        tree = ast.parse(code)
        transformer = _LatexTextToPlainText()
        transformed = transformer.visit(tree)
        result = ast.unparse(transformed)
        assert "BulletedList(" not in result
        assert "VGroup(" in result
        assert transformer.changed is True

    def test_non_latex_calls_unchanged(self) -> None:
        code = "from manim import *\nt = Text('hello')"
        tree = ast.parse(code)
        transformer = _LatexTextToPlainText()
        transformed = transformer.visit(tree)
        result = ast.unparse(transformed)
        assert "Text(" in result
        assert transformer.changed is False
