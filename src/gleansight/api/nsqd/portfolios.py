"""Capped acquisition portfolios and replayable observed contribution reports."""

from __future__ import annotations

from pathlib import Path

from pydantic import Field, JsonValue

from gleansight.api.models import Identifier, Request
from gleansight.api.operation import Operation, RegisteredOperation, json_result
from gleansight.api.runtime import ApiRuntime
from nsqd.app.portfolio.artifacts import read_artifact, write_artifact
from nsqd.app.portfolio.inputs import freeze_input
from nsqd.app.portfolio.planning import plan_portfolio
from nsqd.app.portfolio.replay import replay_report
from nsqd.app.portfolio.reporting import observe, project_inputs
from nsqd.app.portfolio.staging import stage_portfolio
from nsqd.domain.acquisition_portfolio import (
    AcquisitionPortfolio,
    PortfolioCaps,
    PortfolioError,
    StagedPortfolio,
    Target,
)
from nsqd.domain.contribution import ContributionReport
from nsqd.infra.paper_runtime import compose_default_runtime


class PlanRequest(Request):
    snapshot_id: Identifier
    domain_policy_id: Identifier
    target: Target = "calibration"
    caps: PortfolioCaps = Field(default_factory=PortfolioCaps)


class ArtifactRequest(Request):
    bundle_path: Path


class ProjectRequest(ArtifactRequest):
    approved_projections: list[Path] = Field(min_length=1, max_length=200)
    approval_manifest: Path


def plan(runtime: ApiRuntime, request: PlanRequest) -> JsonValue:
    portfolio = plan_portfolio(
        observe(runtime.nsqd.ctx, request.snapshot_id, request.domain_policy_id, request.target),
        request.caps,
    )
    artifact = write_artifact(runtime.repo_root, "acquisition-portfolio", portfolio)
    return json_result(
        {
            "artifact": artifact.model_dump(mode="json"),
            "portfolio": portfolio.model_dump(mode="json"),
        }
    )


def stage(runtime: ApiRuntime, request: ArtifactRequest) -> JsonValue:
    portfolio = read_artifact(runtime.repo_root, request.bundle_path, AcquisitionPortfolio)
    configured = compose_default_runtime(
        papers=runtime.papers,
        nsqd_db_path=runtime.nsqd_db,
        nsqd_index_path=runtime.nsqd_index,
        llm_base_url=runtime.configuration.llm_base_url,
    )
    bridge = configured.nsqd.ctx.bridge
    if bridge is None:
        raise PortfolioError("Paper acquisition bridge is not configured")
    staged = stage_portfolio(portfolio, bridge)
    artifact = write_artifact(runtime.repo_root, "acquisition-portfolio", staged)
    return json_result(
        {"artifact": artifact.model_dump(mode="json"), "staged": staged.model_dump(mode="json")}
    )


def project(runtime: ApiRuntime, request: ProjectRequest) -> JsonValue:
    staged = read_artifact(runtime.repo_root, request.bundle_path, StagedPortfolio)
    inputs = tuple(
        freeze_input(runtime.resolve(path), runtime.resolve(request.approval_manifest))
        for path in request.approved_projections
    )
    report = project_inputs(runtime.nsqd.ctx, staged, inputs)
    artifact = write_artifact(runtime.repo_root, "source-contribution", report)
    return json_result(
        {"artifact": artifact.model_dump(mode="json"), "report": report.model_dump(mode="json")}
    )


def replay(runtime: ApiRuntime, request: ArtifactRequest) -> JsonValue:
    report = read_artifact(runtime.repo_root, request.bundle_path, ContributionReport)
    return json_result(replay_report(report).model_dump(mode="json"))


def operations() -> tuple[RegisteredOperation, ...]:
    return (
        Operation(
            "nsqd.portfolios.plan",
            "Plan deterministic capped cell/probe/type deficits.",
            PlanRequest,
            plan,
            ("write",),
        ),
        Operation(
            "nsqd.portfolios.stage",
            "Discover and stage deduplicated sources for a verified portfolio.",
            ArtifactRequest,
            stage,
            ("write", "external"),
        ),
        Operation(
            "nsqd.portfolios.project",
            "Verify approved inputs and report every observed projection transition.",
            ProjectRequest,
            project,
            ("write", "external"),
        ),
        Operation(
            "nsqd.portfolios.replay",
            "Replay a digest-bound contribution report offline without approval authority.",
            ArtifactRequest,
            replay,
        ),
    )
