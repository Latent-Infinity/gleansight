from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import TypeAdapter

from nsqd.app.portfolio.inputs import freeze_input, verified_input
from nsqd.app.portfolio.planning import plan_portfolio
from nsqd.app.portfolio.replay import replay_report
from nsqd.app.portfolio.reporting import observe, project_inputs
from nsqd.app.portfolio.staging import stage_portfolio
from nsqd.composition import build_container
from nsqd.domain.acquisition_portfolio import PortfolioCaps
from nsqd.null_adapters import HashParaphraseEmbedder
from tests.facts.test_nsqd_acquisition_fallback import FakePaperBridge

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures/approved/nsqd"


def test_report_records_duplicate_and_refused_inputs_and_replays_offline(tmp_path: Path) -> None:
    ctx = build_container(
        db_path=tmp_path / "nsqd.sqlite",
        index_path=tmp_path / "index",
        embedder=HashParaphraseEmbedder(),
    ).ctx
    ctx.snapshots.commit("initial", [], schema_version=1)
    frozen = freeze_input(FIXTURES / "gamma-fragility.yaml", FIXTURES / "manifest.toml")
    source = TypeAdapter(str).validate_python(verified_input(frozen)["source_paper_id"])
    plan = plan_portfolio(observe(ctx, "initial", "finance/1", "calibration"), PortfolioCaps())
    staged = stage_portfolio(plan, FakePaperBridge([{"source_paper_id": source, "title": "Paper"}]))
    corrupt = frozen.model_copy(update={"sha256": "0" * 64})
    report = project_inputs(ctx, staged, (frozen, frozen, corrupt))
    assert [row.outcome for row in report.entries] == ["applied", "applied", "refused"]
    assert [row.created for row in report.entries] == [True, False, False]
    assert report.entries[1].before == report.entries[1].after
    assert report.entries[2].before == report.entries[2].after
    assert report.entries[0].before != report.entries[0].after
    assert not report.grants_approval
    assert replay_report(report).projections == 3
    fabricated = report.entries[0].model_copy(update={"created": False})
    with pytest.raises(ValueError):
        replay_report(report.model_copy(update={"entries": (fabricated, *report.entries[1:])}))


def test_invalid_manifest_is_refused_without_corpus_or_authority_change(tmp_path: Path) -> None:
    from nsqd.domain.acquisition_portfolio import StagedPortfolio

    ctx = build_container(db_path=tmp_path / "nsqd.sqlite", index_path=tmp_path / "index").ctx
    ctx.snapshots.commit("initial", [], schema_version=1)
    plan = plan_portfolio(observe(ctx, "initial", "finance/1", "calibration"), PortfolioCaps())
    staged = stage_portfolio(plan, FakePaperBridge([]))
    assert isinstance(staged, StagedPortfolio)
    manifest = tmp_path / "bad.toml"
    manifest.write_text("schema_version = 1\n")
    frozen = freeze_input(FIXTURES / "gamma-fragility.yaml", manifest)
    report = project_inputs(ctx, staged, (frozen,))
    assert report.entries[0].outcome == "refused"
    assert report.entries[0].before == report.entries[0].after
    assert not ctx.records.list_ids() and not ctx.approved_projection_digests
    assert replay_report(report).refused == 1
    fabricated = report.entries[0].model_copy(update={"refusal": "Unrelated invented explanation"})
    with pytest.raises(ValueError):
        replay_report(report.model_copy(update={"entries": (fabricated,)}))


def test_malformed_yaml_is_frozen_for_clear_replayable_refusal(tmp_path: Path) -> None:
    import yaml

    path = tmp_path / "bad.yaml"
    path.write_text("source_excerpt_path: [broken\n")
    manifest = tmp_path / "manifest.toml"
    manifest.write_text("schema_version = 1\n")
    frozen = freeze_input(path, manifest)
    assert frozen.files["bad.yaml"] == path.read_text()
    with pytest.raises(yaml.YAMLError):
        verified_input(frozen)


def test_current_manual_review_route_blocks_projection_and_replays_without_promotion(
    tmp_path: Path,
) -> None:
    ctx = build_container(db_path=tmp_path / "nsqd.sqlite", index_path=tmp_path / "index").ctx
    ctx.snapshots.commit("initial", [], schema_version=1)
    frozen = freeze_input(FIXTURES / "gamma-fragility.yaml", FIXTURES / "manifest.toml")
    source = TypeAdapter(str).validate_python(verified_input(frozen)["source_paper_id"])
    plan = plan_portfolio(observe(ctx, "initial", "finance/1", "calibration"), PortfolioCaps())
    staged = stage_portfolio(plan, FakePaperBridge([{"source_paper_id": source}]))
    ctx.policies = None
    report = project_inputs(ctx, staged, (frozen,))
    assert report.entries[0].outcome == "refused"
    assert "manual" in str(report.entries[0].refusal).lower()
    assert report.entries[0].source_paper_id == source
    assert report.entries[0].target_ids == staged.sources[0].target_ids
    assert not ctx.records.list_ids()
    assert replay_report(report).refused == 1


def test_replay_includes_preexisting_corpus_and_refuses_an_unstaged_approved_source(
    tmp_path: Path,
) -> None:
    ctx = build_container(db_path=tmp_path / "nsqd.sqlite", index_path=tmp_path / "index").ctx
    ctx.snapshots.commit("initial", [], schema_version=1)
    frozen = freeze_input(FIXTURES / "gamma-fragility.yaml", FIXTURES / "manifest.toml")
    source = TypeAdapter(str).validate_python(verified_input(frozen)["source_paper_id"])
    plan = plan_portfolio(observe(ctx, "initial", "finance/1", "calibration"), PortfolioCaps())
    staged = stage_portfolio(plan, FakePaperBridge([{"source_paper_id": source}]))
    project_inputs(ctx, staged, (frozen,))
    duplicate = project_inputs(ctx, staged, (frozen,))
    assert len(duplicate.initial_records) == 1
    assert not duplicate.entries[0].created
    assert replay_report(duplicate).applied == 1
    unstaged = stage_portfolio(plan, FakePaperBridge([{"source_paper_id": "another-source"}]))
    refused = project_inputs(ctx, unstaged, (frozen,))
    assert refused.entries[0].outcome == "refused"
    assert "not a staged" in str(refused.entries[0].refusal)
    assert replay_report(refused).refused == 1
