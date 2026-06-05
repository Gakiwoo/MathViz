"""Tests for VideoReviewAgent and PublisherAgent."""

from __future__ import annotations

from pathlib import Path

import pytest

from math_to_manim.agents.publisher import PublisherAgent
from math_to_manim.agents.video_review import VideoReviewAgent, _infer_run_dir, _sample_timestamps
from math_to_manim.schemas import RenderResult, UserRequest, VideoReviewReport


class TestVideoReviewAgent:
    def test_skipped_render_returns_needs_render_report(self) -> None:
        agent = VideoReviewAgent()
        result = RenderResult(status="skipped", scene_name="TestScene", stderr="render skipped", metadata={"skipped": True})
        report = agent.run(result)
        assert isinstance(report, VideoReviewReport)
        assert report.approved is False
        assert report.score == 0.0
        assert any("did not produce" in obs for obs in report.observations)
        assert any("render-missing" == issue.code for issue in report.issues)
        assert any("Manim" in rec for rec in report.recommendations)

    def test_failed_render_with_no_output_path(self) -> None:
        agent = VideoReviewAgent()
        result = RenderResult(status="failed", scene_name="TestScene", stderr="static validation did not pass", output_path=None)
        report = agent.run(result)
        assert report.score == 0.0
        assert report.approved is False
        assert report.metadata["render_status"] == "failed"

    def test_succeeded_render_without_actual_output(self) -> None:
        agent = VideoReviewAgent()
        result = RenderResult(status="succeeded", scene_name="TestScene", output_path=None)
        report = agent.run(result)
        assert report.score == 0.0
        assert any("render-missing" == issue.code for issue in report.issues)

    def test_rendered_video_is_probed_and_draft_notes_written(self, tmp_path: Path) -> None:
        agent = VideoReviewAgent()
        video_path = tmp_path / "output.mp4"
        video_path.write_bytes(b"\x00" * 1024)
        result = RenderResult(status="succeeded", scene_name="TestScene", output_path=str(video_path), stdout="render ok")
        report = agent.run(result)
        assert isinstance(report, VideoReviewReport)
        assert report.metadata["draft_review"] is not None
        draft = report.metadata["draft_review"]
        assert isinstance(draft, dict)
        assert "notes_path" in draft
        notes_path = draft["notes_path"]
        assert notes_path is not None
        assert Path(notes_path).exists()
        assert "Render did not produce a video" not in " ".join(report.observations)

    def test_report_includes_editor_review_requirement(self, tmp_path: Path) -> None:
        agent = VideoReviewAgent()
        video_path = tmp_path / "output.mp4"
        video_path.write_bytes(b"\x00" * 500)
        result = RenderResult(status="succeeded", scene_name="TestScene", output_path=str(video_path))
        report = agent.run(result)
        assert report.metadata.get("requires_editor_review") is True
        assert report.metadata.get("review_mode") == "draft_editor_review"
        assert any("draft-review-required" == issue.code for issue in report.issues)


class TestPublisherAgent:
    def test_publisher_produces_package_even_with_skipped_render(self, tmp_path: Path) -> None:
        agent = PublisherAgent()
        request = UserRequest(prompt="test")
        render = RenderResult(status="skipped", scene_name="test", stderr="skipped")
        review = VideoReviewReport(approved=False, score=0.0, observations=["none"], recommendations=["rerun"])
        reports: list[str] = []
        package = agent.run((request, tmp_path, render, review, reports))
        assert package is not None
        assert package.request.prompt == "test"

    def test_publisher_includes_reports_in_metadata(self, tmp_path: Path) -> None:
        agent = PublisherAgent()
        request = UserRequest(prompt="test")
        render = RenderResult(status="succeeded", scene_name="test", output_path="/fake/path.mp4")
        review = VideoReviewReport(approved=True, score=0.95, observations=["great"], recommendations=[])
        report_path = tmp_path / "fake_report.json"
        report_path.write_text('{"status": "ok"}')
        reports = [str(report_path)]
        package = agent.run((request, tmp_path, render, review, reports))
        assert package.render_result is not None
        assert package.render_result.status == "succeeded"
        assert package.metadata["reports"] == reports


class TestVideoReviewHelpers:
    def test_infer_run_dir_from_media_parent(self, tmp_path: Path) -> None:
        media_dir = tmp_path / "runs" / "run-001" / "media"
        media_dir.mkdir(parents=True)
        video = media_dir / "output.mp4"
        run_dir = _infer_run_dir(video)
        assert run_dir == tmp_path / "runs" / "run-001"

    def test_infer_run_dir_falls_back_to_parent(self, tmp_path: Path) -> None:
        video = tmp_path / "output.mp4"
        run_dir = _infer_run_dir(video)
        assert run_dir == tmp_path

    def test_sample_timestamps_short_video(self) -> None:
        timestamps = _sample_timestamps(0.5)
        assert timestamps == [0.0]

    def test_sample_timestamps_normal_video(self) -> None:
        timestamps = _sample_timestamps(10.0)
        assert len(timestamps) == 7
        assert timestamps[0] == pytest.approx(0.5)
        assert timestamps[-1] == pytest.approx(9.5)

    def test_sample_timestamps_none_duration(self) -> None:
        timestamps = _sample_timestamps(None)
        assert timestamps == [0.0]
