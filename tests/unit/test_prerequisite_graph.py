"""Tests for PrerequisiteGraphAgent and its helpers."""

from __future__ import annotations

from math_to_manim.agents.prerequisite_graph import (
    PrerequisiteGraphAgent,
    _default_prerequisites,
    concept_id,
    normalize_concept_name,
)
from math_to_manim.config import RuntimeConfig
from math_to_manim.schemas import ConceptIntent


class TestPrerequisiteGraphHelpers:
    def test_normalize_concept_name_trims_and_lowercases(self) -> None:
        assert normalize_concept_name("  Derivative  ") == "derivative"
        assert normalize_concept_name("Linear   Algebra") == "linear algebra"

    def test_concept_id_replaces_special_chars_with_hyphens(self) -> None:
        assert concept_id("linear algebra") == "linear-algebra"
        assert concept_id("  F'(a) ") == "f-a"
        assert concept_id("") == "concept"

    def test_default_prerequisites_for_derivative(self) -> None:
        prereqs = _default_prerequisites("derivative")
        assert "limits" in prereqs

    def test_default_prerequisites_for_pythagorean(self) -> None:
        prereqs = _default_prerequisites("pythagorean")
        assert "right triangles" in prereqs

    def test_default_prerequisites_for_fourier(self) -> None:
        prereqs = _default_prerequisites("fourier")
        assert "superposition" in prereqs

    def test_default_prerequisites_for_unknown_topic(self) -> None:
        prereqs = _default_prerequisites("topology")
        assert len(prereqs) == 4


class TestPrerequisiteGraphAgent:
    def test_deterministic_run_produces_valid_graph(self) -> None:
        config = RuntimeConfig(deterministic=True)
        agent = PrerequisiteGraphAgent(config=config)
        intent = ConceptIntent(
            primary_concept="derivative",
        )

        graph = agent.run(intent)

        assert graph.root_node_id == "derivative"
        assert len(graph.nodes) >= 2
        assert all(edge.relationship == "prerequisite" for edge in graph.edges)
        assert not graph.has_cycle()
        graph.validate_references()

    def test_deterministic_graph_with_explicit_prerequisites(self) -> None:
        config = RuntimeConfig(deterministic=True)
        agent = PrerequisiteGraphAgent(config=config)
        intent = ConceptIntent(
            primary_concept="calculus",
            prerequisites=["algebra", "trigonometry", "functions"],
        )

        graph = agent.run(intent)

        root = graph.require_node(graph.root_node_id)
        assert root is not None
        assert len(graph.nodes) == 4  # root + 3 prereqs
        assert len(graph.edges) == 3
        assert not graph.has_cycle()

    def test_deterministic_graph_topological_order_is_valid(self) -> None:
        config = RuntimeConfig(deterministic=True)
        agent = PrerequisiteGraphAgent(config=config)
        intent = ConceptIntent(primary_concept="derivative")

        graph = agent.run(intent)
        order = graph.topological_node_ids()

        # Root (target) should be last
        assert order[-1] == graph.root_node_id
