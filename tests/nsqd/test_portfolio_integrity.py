from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import JsonValue

from nsqd.app.portfolio.artifacts import read_artifact, write_artifact
from nsqd.app.portfolio.inputs import freeze_input, verified_input
from nsqd.app.portfolio.planning import plan_portfolio
from nsqd.app.portfolio.staging import stage_portfolio
from nsqd.app.portfolio.validation import validate_staged
from nsqd.domain.acquisition_portfolio import AcquisitionPortfolio, PortfolioCaps, digest_json
from tests.facts.test_nsqd_acquisition_fallback import FakePaperBridge
from tests.nsqd.test_acquisition_portfolio import observation


def test_stage_rejects_spoofed_shortlists_and_over_budget_results(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plan = plan_portfolio(observation(), PortfolioCaps(per_deficit_sources=1))
    for malicious in (
        [{"source_paper_id": "undiscovered"}],
        [{"source_paper_id": "a", "review_status": "approved"}],
        [{"source_paper_id": "a"}, {"source_paper_id": "b"}],
    ):
        bridge = FakePaperBridge([{"source_paper_id": "a"}, {"source_paper_id": "b"}])

        def shortlist(
            candidates: list[dict[str, JsonValue]],
            *,
            limit: int,
            insufficiency_query: str,
            filters: dict[str, JsonValue],
            failure_context: dict[str, JsonValue],
        ) -> list[dict[str, str]]:
            return malicious

        monkeypatch.setattr(bridge, "shortlist", shortlist)
        with pytest.raises(ValueError):
            stage_portfolio(plan, bridge)


def test_staged_bindings_cannot_be_forged_or_expand_caps() -> None:
    plan = plan_portfolio(observation(), PortfolioCaps(max_sources=1, per_deficit_sources=1))
    staged = stage_portfolio(plan, FakePaperBridge([{"source_paper_id": "a"}]))
    source, row = staged.sources[0], staged.retrievals[0]
    variants = (
        staged.model_copy(update={"plan": plan.model_copy(update={"portfolio_id": "0" * 64})}),
        staged.model_copy(update={"sources": (source, source)}),
        staged.model_copy(update={"retrievals": staged.retrievals[:-1]}),
        staged.model_copy(
            update={
                "retrievals": (row.model_copy(update={"target_ids": ()}), *staged.retrievals[1:])
            }
        ),
        staged.model_copy(update={"sources": (source.model_copy(update={"target_ids": ()}),)}),
        staged.model_copy(
            update={
                "sources": (source.model_copy(update={"draft": {"review_status": "approved"}}),)
            }
        ),
        staged.model_copy(
            update={
                "retrievals": (
                    row.model_copy(update={"shortlisted_source_ids": ("spoofed",)}),
                    *staged.retrievals[1:],
                )
            }
        ),
    )
    for forged in variants:
        with pytest.raises(ValueError):
            validate_staged(forged)


def test_artifact_hash_and_workspace_boundary_are_checked(tmp_path: Path) -> None:
    plan = plan_portfolio(observation(), PortfolioCaps())
    reference = write_artifact(tmp_path, "acquisition-portfolio", plan)
    path = Path(reference.bundle_path)
    assert read_artifact(tmp_path, path, AcquisitionPortfolio) == plan
    with pytest.raises(ValueError):
        read_artifact(tmp_path, tmp_path.parent, AcquisitionPortfolio)
    (tmp_path / path / "extra.json").write_text("{}")
    with pytest.raises(ValueError):
        read_artifact(tmp_path, path, AcquisitionPortfolio)
    (tmp_path / path / "extra.json").unlink()
    (tmp_path / path / "manifest.json").write_text('{"other": "digest"}')
    with pytest.raises(ValueError):
        read_artifact(tmp_path, path, AcquisitionPortfolio)


def test_frozen_paths_cannot_escape_even_with_rehashed_payload(tmp_path: Path) -> None:
    projection, manifest = tmp_path / "missing.yaml", tmp_path / "missing.toml"
    frozen = freeze_input(projection, manifest)
    payload = frozen.model_dump(mode="json", exclude={"sha256"})
    payload["projection_path"] = "../escape.yaml"
    forged = frozen.model_validate({**payload, "sha256": digest_json(payload)})
    with pytest.raises(ValueError, match="escapes"):
        verified_input(forged)


def test_oversized_projection_is_refused_before_reading_unbounded_input(tmp_path: Path) -> None:
    path = tmp_path / "large.yaml"
    path.write_bytes(b"x" * (256 * 1024 + 1))
    with pytest.raises(ValueError, match="256 KiB"):
        freeze_input(path, tmp_path / "manifest.toml")
