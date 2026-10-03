"""Tau measurement and report operations sharing the application trust boundary."""

import json

from pydantic import JsonValue, TypeAdapter

from gleansight.api.nsqd.requests import TauEvaluateRequest, TauRequest
from gleansight.api.runtime import ApiRuntime
from nsqd.app.use_cases import AutonomousTauPacketEvaluationUseCase, TauMeasurementEvidenceUseCase
from nsqd.infra.piccolo.stores import PiccoloApprovedDigestStore
from nsqd.infrastructure.workflow_output import create_run_directory
from nsqd.tau_runtime import build_autonomous_tau_use_case, load_autonomous_tau_rows


def _evidence(runtime: ApiRuntime) -> TauMeasurementEvidenceUseCase:
    return TauMeasurementEvidenceUseCase(
        candidates=runtime.nsqd.ctx.candidates,
        approved_projection_digests=PiccoloApprovedDigestStore(
            runtime.nsqd.database
        ).list_digests(),
    )


def export(runtime: ApiRuntime, request: TauRequest) -> JsonValue:
    return {
        "jsonl": _evidence(runtime).export_jsonl(request.candidate_artifact_hashes).decode("utf-8")
    }


def inventory(runtime: ApiRuntime, request: TauRequest) -> JsonValue:
    return TypeAdapter(JsonValue).validate_python(
        _evidence(runtime).inventory(request.candidate_artifact_hashes)
    )


def review(runtime: ApiRuntime, request: TauRequest) -> JsonValue:
    runtime.nsqd.ctx.approved_projection_digests = PiccoloApprovedDigestStore(
        runtime.nsqd.database
    ).list_digests()
    result = build_autonomous_tau_use_case(container=runtime.nsqd, settings=runtime.settings).run(
        request.candidate_artifact_hashes,
    )
    return _report(runtime, "autonomous-tau-review", TypeAdapter(JsonValue).validate_python(result))


def evaluate(runtime: ApiRuntime, request: TauEvaluateRequest) -> JsonValue:
    audit = runtime.settings.nsqd.autonomous_tau.audit
    rows = load_autonomous_tau_rows(request.inputs, repo_root=runtime.repo_root)
    result = AutonomousTauPacketEvaluationUseCase(
        measurement_evidence=_evidence(runtime),
        audit_policy_revision=audit.policy_revision,
        audit_sample_rate=audit.sample_rate,
    ).run(request.candidate_artifact_hashes, rows, require_balanced=request.require_balanced)
    return _report(
        runtime, "evaluate-autonomous-tau-reviews", TypeAdapter(JsonValue).validate_python(result)
    )


def _report(runtime: ApiRuntime, workflow: str, result: JsonValue) -> JsonValue:
    output = create_run_directory(runtime.repo_root, workflow) / "report.json"
    output.write_text(
        json.dumps(result, sort_keys=True, indent=2, allow_nan=False) + "\n", encoding="utf-8"
    )
    return {"output": str(output), "report": result}
