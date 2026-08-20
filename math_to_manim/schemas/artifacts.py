from __future__ import annotations

from collections import deque
from collections.abc import Iterable
from typing import Any, Literal

from pydantic import model_validator

from .base import ArtifactModel, Field

GraphNodeKind = Literal[
    "concept",
    "skill",
    "definition",
    "theorem",
    "example",
    "exercise",
    "visual",
]
GraphRelationship = Literal[
    "prerequisite",
    "depends_on",
    "introduces",
    "extends",
    "example_of",
    "visualizes",
    "assesses",
    "supports",
    "contrasts",
    "next",
]
IssueSeverity = Literal["info", "warning", "error"]
ValidationStatus = Literal["passed", "warning", "failed", "skipped"]
RenderStatus = Literal["queued", "running", "succeeded", "failed", "skipped"]

DEPENDENCY_RELATIONSHIPS: tuple[str, ...] = ("prerequisite", "depends_on")


class UserRequest(ArtifactModel):
    request_id: str | None = None
    prompt: str = Field(..., min_length=1)
    topic: str | None = None
    target_audience: str | None = None
    objectives: list[str] = Field(default_factory=list)
    duration_seconds: int | None = Field(default=None, ge=1)
    style: str | None = None
    constraints: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ConceptIntent(ArtifactModel):
    primary_concept: str = Field(..., min_length=1)
    related_concepts: list[str] = Field(default_factory=list)
    prerequisites: list[str] = Field(default_factory=list)
    learning_objectives: list[str] = Field(default_factory=list)
    misconceptions: list[str] = Field(default_factory=list)
    target_audience: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class KnowledgeGraphNode(ArtifactModel):
    id: str = Field(..., min_length=1)
    label: str = Field(..., min_length=1)
    kind: GraphNodeKind = "concept"
    summary: str | None = None
    tags: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class KnowledgeGraphEdge(ArtifactModel):
    source: str = Field(..., min_length=1)
    target: str = Field(..., min_length=1)
    relationship: GraphRelationship
    label: str | None = None
    weight: float = Field(default=1.0, ge=0.0, le=1.0)
    metadata: dict[str, Any] = Field(default_factory=dict)


GraphNode = KnowledgeGraphNode
GraphEdge = KnowledgeGraphEdge


def _validate_graph_integrity(
    nodes: list[KnowledgeGraphNode],
    edges: list[KnowledgeGraphEdge],
    root_node_id: str | None,
) -> None:
    node_ids = [node.id for node in nodes]
    duplicate_node_ids = sorted({node_id for node_id in node_ids if node_ids.count(node_id) > 1})
    if duplicate_node_ids:
        raise ValueError(f"duplicate node ids: {', '.join(duplicate_node_ids)}")

    known_ids = set(node_ids)
    if root_node_id is not None and root_node_id not in known_ids:
        raise ValueError(f"root_node_id references unknown node id: {root_node_id}")

    dangling_edges = [
        f"{edge.source}->{edge.target}"
        for edge in edges
        if edge.source not in known_ids or edge.target not in known_ids
    ]
    if dangling_edges:
        raise ValueError(f"edges reference unknown node ids: {', '.join(dangling_edges)}")

    self_loops = [f"{edge.source}->{edge.target}" for edge in edges if edge.source == edge.target]
    if self_loops:
        raise ValueError(f"self-loop edges are not allowed: {', '.join(self_loops)}")

    edge_keys = [(edge.source, edge.target, edge.relationship) for edge in edges]
    duplicate_edges = sorted({edge_key for edge_key in edge_keys if edge_keys.count(edge_key) > 1})
    if duplicate_edges:
        formatted = ", ".join(f"{source}->{target}:{relationship}" for source, target, relationship in duplicate_edges)
        raise ValueError(f"duplicate edges: {formatted}")


class KnowledgeGraph(ArtifactModel):
    nodes: list[KnowledgeGraphNode] = Field(default_factory=list)
    edges: list[KnowledgeGraphEdge] = Field(default_factory=list)
    root_node_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _validate_graph(self) -> KnowledgeGraph:
        _validate_graph_integrity(self.nodes, self.edges, self.root_node_id)
        return self

    @property
    def node_ids(self) -> set[str]:
        return {node.id for node in self.nodes}

    def get_node(self, node_id: str) -> KnowledgeGraphNode | None:
        return next((node for node in self.nodes if node.id == node_id), None)

    def require_node(self, node_id: str) -> KnowledgeGraphNode:
        node = self.get_node(node_id)
        if node is None:
            raise KeyError(f"unknown node id: {node_id}")
        return node

    def edges_from(
        self,
        node_id: str,
        relationship: str | None = None,
    ) -> list[KnowledgeGraphEdge]:
        self.require_node(node_id)
        return [
            edge
            for edge in self.edges
            if edge.source == node_id and (relationship is None or edge.relationship == relationship)
        ]

    def edges_to(
        self,
        node_id: str,
        relationship: str | None = None,
    ) -> list[KnowledgeGraphEdge]:
        self.require_node(node_id)
        return [
            edge
            for edge in self.edges
            if edge.target == node_id and (relationship is None or edge.relationship == relationship)
        ]

    def adjacent_node_ids(
        self,
        node_id: str,
        relationship: str | None = None,
    ) -> set[str]:
        outgoing = {edge.target for edge in self.edges_from(node_id, relationship)}
        incoming = {edge.source for edge in self.edges_to(node_id, relationship)}
        return outgoing | incoming

    def validate_references(self) -> KnowledgeGraph:
        _validate_graph_integrity(self.nodes, self.edges, self.root_node_id)
        return self

    def topological_node_ids(
        self,
        relationships: Iterable[str] | None = DEPENDENCY_RELATIONSHIPS,
    ) -> list[str]:
        selected_relationships = None if relationships is None else set(relationships)
        adjacency: dict[str, list[str]] = {node.id: [] for node in self.nodes}
        indegree: dict[str, int] = {node.id: 0 for node in self.nodes}

        for edge in self.edges:
            if selected_relationships is not None and edge.relationship not in selected_relationships:
                continue
            adjacency[edge.source].append(edge.target)
            indegree[edge.target] += 1

        ordered_ids = [node.id for node in self.nodes]
        queue: deque[str] = deque(node_id for node_id in ordered_ids if indegree[node_id] == 0)
        result: list[str] = []

        while queue:
            node_id = queue.popleft()
            result.append(node_id)
            for target_id in adjacency[node_id]:
                indegree[target_id] -= 1
                if indegree[target_id] == 0:
                    queue.append(target_id)

        if len(result) != len(self.nodes):
            relationship_label = "all" if selected_relationships is None else ", ".join(sorted(selected_relationships))
            raise ValueError(f"knowledge graph contains a cycle for relationships: {relationship_label}")

        return result

    def has_cycle(
        self,
        relationships: Iterable[str] | None = DEPENDENCY_RELATIONSHIPS,
    ) -> bool:
        try:
            self.topological_node_ids(relationships=relationships)
        except ValueError:
            return True
        return False


class CurriculumStep(ArtifactModel):
    id: str = Field(..., min_length=1)
    title: str = Field(..., min_length=1)
    objective: str = Field(..., min_length=1)
    concept_ids: list[str] = Field(default_factory=list)
    estimated_minutes: int = Field(default=5, ge=1)
    assessment_prompt: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class CurriculumModule(ArtifactModel):
    id: str = Field(..., min_length=1)
    title: str = Field(..., min_length=1)
    summary: str | None = None
    steps: list[CurriculumStep] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class CurriculumPlan(ArtifactModel):
    title: str = Field(..., min_length=1)
    modules: list[CurriculumModule] = Field(default_factory=list)
    learning_objectives: list[str] = Field(default_factory=list)
    estimated_total_minutes: int | None = Field(default=None, ge=1)
    metadata: dict[str, Any] = Field(default_factory=dict)


class Equation(ArtifactModel):
    latex: str = Field(..., min_length=1)
    description: str | None = None
    variables: dict[str, str] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)


class MathPacket(ArtifactModel):
    concept_id: str | None = None
    definitions: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    key_equations: list[Equation] = Field(default_factory=list)
    worked_examples: list[str] = Field(default_factory=list)
    common_errors: list[str] = Field(default_factory=list)
    source_notes: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class StoryboardScene(ArtifactModel):
    id: str = Field(..., min_length=1)
    title: str = Field(..., min_length=1)
    narration: str | None = None
    visual_actions: list[str] = Field(default_factory=list)
    concept_ids: list[str] = Field(default_factory=list)
    duration_seconds: float | None = Field(default=None, ge=0.0)
    camera: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class VisualStoryboard(ArtifactModel):
    title: str = Field(..., min_length=1)
    scenes: list[StoryboardScene] = Field(default_factory=list)
    target_duration_seconds: float | None = Field(default=None, ge=0.0)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ManimObjectSpec(ArtifactModel):
    id: str = Field(..., min_length=1)
    type: str = Field(..., min_length=1)
    properties: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ManimAnimationSpec(ArtifactModel):
    action: str = Field(..., min_length=1)
    target: str | None = None
    args: dict[str, Any] = Field(default_factory=dict)
    start_time: float | None = Field(default=None, ge=0.0)
    duration_seconds: float | None = Field(default=None, ge=0.0)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ManimSceneSpec(ArtifactModel):
    scene_name: str = Field(..., min_length=1)
    storyboard_scene_id: str | None = None
    manim_version: str | None = None
    imports: list[str] = Field(default_factory=list)
    objects: list[ManimObjectSpec] = Field(default_factory=list)
    animations: list[ManimAnimationSpec] = Field(default_factory=list)
    camera: dict[str, Any] = Field(default_factory=dict)
    config: dict[str, Any] = Field(default_factory=dict)
    code_requirements: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class GeneratedCode(ArtifactModel):
    scene_name: str = Field(..., min_length=1)
    code: str = Field(..., min_length=1)
    language: Literal["python"] = "python"
    dependencies: list[str] = Field(default_factory=list)
    manim_version: str | None = None
    source_spec_id: str | None = None
    checksum: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ValidationIssue(ArtifactModel):
    code: str = Field(..., min_length=1)
    message: str = Field(..., min_length=1)
    severity: IssueSeverity = "error"
    artifact: str | None = None
    path: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


def _validate_report_status(status: str, issues: list[ValidationIssue]) -> None:
    has_error = any(issue.severity == "error" for issue in issues)
    if status == "passed" and has_error:
        raise ValueError("passed validation reports cannot contain error issues")


class ValidationReport(ArtifactModel):
    status: ValidationStatus
    issues: list[ValidationIssue] = Field(default_factory=list)
    checked_artifacts: list[str] = Field(default_factory=list)
    summary: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _validate_status(self) -> ValidationReport:
        _validate_report_status(self.status, self.issues)
        return self

    @property
    def is_successful(self) -> bool:
        return self.status in {"passed", "warning"} and not any(issue.severity == "error" for issue in self.issues)


class RenderResult(ArtifactModel):
    status: RenderStatus
    scene_name: str | None = None
    output_path: str | None = None
    preview_path: str | None = None
    command: list[str] = Field(default_factory=list)
    stdout: str | None = None
    stderr: str | None = None
    duration_seconds: float | None = Field(default=None, ge=0.0)
    validation_report: ValidationReport | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class VideoReviewReport(ArtifactModel):
    approved: bool = False
    score: float | None = Field(default=None, ge=0.0, le=1.0)
    observations: list[str] = Field(default_factory=list)
    issues: list[ValidationIssue] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class RepairPatch(ArtifactModel):
    target_artifact: str = Field(..., min_length=1)
    summary: str = Field(..., min_length=1)
    unified_diff: str | None = None
    replacement_code: str | None = None
    issue_codes: list[str] = Field(default_factory=list)
    validation_expectations: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class AnimationPackage(ArtifactModel):
    package_id: str | None = None
    request: UserRequest
    intent: ConceptIntent | None = None
    knowledge_graph: KnowledgeGraph | None = None
    curriculum_plan: CurriculumPlan | None = None
    math_packet: MathPacket | None = None
    storyboard: VisualStoryboard | None = None
    scene_specs: list[ManimSceneSpec] = Field(default_factory=list)
    generated_code: list[GeneratedCode] = Field(default_factory=list)
    validation_report: ValidationReport | None = None
    render_result: RenderResult | None = None
    video_review_report: VideoReviewReport | None = None
    repair_patches: list[RepairPatch] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
