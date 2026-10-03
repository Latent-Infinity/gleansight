from __future__ import annotations

from pathlib import Path

from pydantic import JsonValue, TypeAdapter

from nsqd.app.use_cases import AutonomousTauLabelingUseCase, TauMeasurementEvidenceUseCase
from nsqd.composition import NsqdContainer
from nsqd.domain.artifact_paths import resolve_artifact_path
from nsqd.domain.tau_review import autonomous_tau_review_packet_digest
from papers.config.settings import DEFAULT_OLLAMA_BASE_URL, Settings
from papers.infra.llm_codex_subscription.client import CodexSubscriptionClient, RoutedLLMClient
from papers.infra.llm_openai_compat.client import build_openai_compat_client

MAX_AUTONOMOUS_TAU_PACKET_BYTES = 8 * 1024 * 1024


def load_autonomous_tau_rows(inputs: list[Path], *, repo_root: Path) -> list[dict[str, JsonValue]]:
    rows: list[dict[str, JsonValue]] = []
    adapter = TypeAdapter(dict[str, JsonValue])
    for input_path in inputs:
        path = (
            input_path if input_path.is_absolute() else resolve_artifact_path(repo_root, input_path)
        )
        if path.stat().st_size > MAX_AUTONOMOUS_TAU_PACKET_BYTES:
            raise ValueError(f"autonomous tau packet exceeds byte limit: {path}")
        payload = adapter.validate_json(path.read_text(encoding="utf-8"))
        raw_rows = payload.get("rows")
        if not isinstance(raw_rows, list) or not raw_rows:
            raise ValueError(f"autonomous tau packet rows are required: {path}")
        packet_rows = [adapter.validate_python(row) for row in raw_rows]
        if payload.get("packet_digest") != autonomous_tau_review_packet_digest(packet_rows):
            raise ValueError(f"autonomous tau packet digest drift: {path}")
        rows.extend(packet_rows)
    return rows


def build_autonomous_tau_use_case(
    *, container: NsqdContainer, settings: Settings
) -> AutonomousTauLabelingUseCase:
    autonomous_tau = settings.nsqd.autonomous_tau
    evidence = TauMeasurementEvidenceUseCase(
        candidates=container.ctx.candidates,
        approved_projection_digests=container.ctx.approved_projection_digests,
    )
    openai_client = build_openai_compat_client(
        base_url=autonomous_tau.writer.base_url or DEFAULT_OLLAMA_BASE_URL,
        api_key=None,
    )
    adjudicator = autonomous_tau.adjudicator
    llm_client = RoutedLLMClient(
        default_client=openai_client,
        provider_clients={
            "codex_subscription": CodexSubscriptionClient(
                executable_path=adjudicator.executable_path or "codex",
                default_reasoning_effort=adjudicator.reasoning_effort or "high",
            )
        },
    )
    return AutonomousTauLabelingUseCase(
        measurement_evidence=evidence,
        llm_client=llm_client,
        clock=container.clock,
        settings=autonomous_tau,
    )
