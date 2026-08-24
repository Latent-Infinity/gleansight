from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
import yaml

from nsqd.app.handlers import NsqdHandlerContext, handle_project
from nsqd.app.use_cases import ProjectPaperUseCase
from nsqd.domain.card import corpus_ingest_rejection
from nsqd.domain.policy import records_for_policy
from nsqd.domain.project import (
    REVIEWED_PROJECTION_FIELDS,
    canonical_reviewed_projection_digest,
    normalize_paraphrase,
)
from nsqd.domain.snapshot import sha256_hex
from nsqd.null_adapters import (
    FixedClock,
    NullCorpusIndex,
    NullCorpusRecordStore,
    NullCorpusSnapshotStore,
    NullFrontierCardStore,
    NullHarvestStore,
    NullMorphospaceStore,
    NullNsqdCandidateStore,
)
from nsqd.ports import NsqdJob

AS_OF = datetime(2024, 1, 1, tzinfo=UTC)
NSQD = Path(__file__).resolve().parents[1] / "fixtures" / "approved" / "nsqd"
APPROVED = Path(__file__).resolve().parents[1] / "fixtures" / "approved"


def _ctx(
    approved_projection_digests: frozenset[str] = frozenset(),
    *,
    records: NullCorpusRecordStore | None = None,
) -> NsqdHandlerContext:
    resolved_records = records or NullCorpusRecordStore()
    snapshots = NullCorpusSnapshotStore()
    return NsqdHandlerContext(
        clock=FixedClock(AS_OF),
        candidates=NullNsqdCandidateStore(),
        cards=NullFrontierCardStore(),
        snapshots=snapshots,
        records=resolved_records,
        harvest=NullHarvestStore(resolved_records, snapshots),
        index=NullCorpusIndex(),
        morph=NullMorphospaceStore(),
        approved_projection_digests=approved_projection_digests,
    )


def _load_yaml(path: Path) -> dict[str, object]:
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    return payload


def _paper_a() -> dict[str, object]:
    return _load_yaml(NSQD / "paper-a.yaml")


def _abstract() -> str:
    import tomllib

    data = tomllib.loads((APPROVED / "manifest.toml").read_text(encoding="utf-8"))
    abstract = data["fixture"]["DATA-01c"]["abstract"]
    assert isinstance(abstract, str)
    return abstract


def _project(ctx: NsqdHandlerContext) -> ProjectPaperUseCase:
    return ProjectPaperUseCase(
        harvest=ctx.harvest,
        records=ctx.records,
        clock=ctx.clock,
        approved_projection_digests=ctx.approved_projection_digests,
    )


def _normalized_paraphrase_hash(paraphrase: str) -> str:
    return sha256_hex(normalize_paraphrase(paraphrase).encode("utf-8"))


def _approved_digests(*projections: dict[str, object]) -> frozenset[str]:
    return frozenset(canonical_reviewed_projection_digest(projection) for projection in projections)


def _non_nsqd_projection(domain_policy_id: str = "optimization/1") -> dict[str, object]:
    projection = _paper_a()
    projection["id"] = "DATA-NSQD-OTHER"
    projection["paper_id"] = "paper-21"
    projection["source_paper_id"] = "paper-source-21"
    projection["source"] = "paper:paper-source-21"
    projection["domain_policy_id"] = domain_policy_id
    projection["coordinates"] = (
        {
            "mechanism": "flow-driven",
            "target": "drawdown",
            "horizon": "intraday",
        }
        if domain_policy_id == "finance/1"
        else {
            "problem": "constrained-expectation",
            "method": "sequential-quadratic",
            "setting": "rank-deficient",
        }
    )
    return projection


def test_requirement_cards_are_rejected_by_projector() -> None:
    ctx = _ctx()
    card = _load_yaml(NSQD / "gamma-flow.yaml")
    assert corpus_ingest_rejection(card) == "requirement-card is not a corpus record"
    with pytest.raises(ValueError, match="requirement-card"):
        _project(ctx).run(domain_policy_id="finance/1", projection=card)


def test_abstract_substitution_is_rejected() -> None:
    ctx = _ctx()
    projection = _paper_a()
    abstract = _abstract()
    projection["paraphrase"] = abstract
    projection["abstract"] = abstract
    projection["paraphrase_sha256"] = _normalized_paraphrase_hash(abstract)
    with pytest.raises(ValueError, match="abstract"):
        _project(ctx).run(domain_policy_id="optimization/1", projection=projection)


def test_unapproved_draft_is_rejected() -> None:
    ctx = _ctx()
    projection = _paper_a()
    projection["review_status"] = "pending"
    with pytest.raises(ValueError, match="approved"):
        _project(ctx).run(domain_policy_id="optimization/1", projection=projection)


def test_missing_policy_id_is_rejected() -> None:
    ctx = _ctx()
    with pytest.raises(ValueError, match="domain_policy_id is required"):
        _project(ctx).run(domain_policy_id="", projection=_paper_a())


def test_projection_policy_must_match_explicit_argument() -> None:
    projection = _non_nsqd_projection(domain_policy_id="optimization/1")
    ctx = _ctx(_approved_digests(projection))

    with pytest.raises(ValueError, match=r"projection\.domain_policy_id"):
        _project(ctx).run(domain_policy_id="finance/1", projection=projection)


def test_source_paper_id_must_be_present_and_not_fall_back_to_paper_id() -> None:
    ctx = _ctx()
    projection = _paper_a()
    projection.pop("source_paper_id")
    with pytest.raises(ValueError, match="source_paper_id is required"):
        _project(ctx).run(domain_policy_id="optimization/1", projection=projection)


def test_source_paper_id_must_be_a_non_empty_string() -> None:
    ctx = _ctx()
    projection = _paper_a()
    projection["source_paper_id"] = 123
    with pytest.raises(ValueError, match="source_paper_id is required"):
        _project(ctx).run(domain_policy_id="optimization/1", projection=projection)


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("human_reviewer", "", "human_reviewer is required"),
        ("human_reviewer", object(), "human_reviewer is required"),
        ("human_approved_at", "2026-08-21T19:03:54", "human_approved_at must be a UTC timestamp"),
        ("paraphrase_source", "", "paraphrase_source is required"),
        ("paraphrase_source", object(), "paraphrase_source is required"),
        (
            "source_abstract_sha256",
            "UPPERCASE",
            "source_abstract_sha256 must be a lowercase SHA-256 hex digest",
        ),
        (
            "source_markdown_sha256",
            "short",
            "source_markdown_sha256 must be a lowercase SHA-256 hex digest",
        ),
        (
            "paraphrase_sha256",
            "not-a-hash",
            "paraphrase_sha256 must be a lowercase SHA-256 hex digest",
        ),
    ],
)
def test_projector_rejects_invalid_review_and_hash_fields(
    field: str,
    value: object,
    message: str,
) -> None:
    ctx = _ctx()
    projection = _paper_a()
    projection[field] = value
    with pytest.raises(ValueError, match=message):
        _project(ctx).run(domain_policy_id="optimization/1", projection=projection)


def test_projector_rejects_paraphrase_hash_mismatch() -> None:
    ctx = _ctx()
    projection = _paper_a()
    projection["paraphrase"] = f"{projection['paraphrase']} extra"
    with pytest.raises(
        ValueError, match="paraphrase_sha256 does not match normalized paraphrase bytes"
    ):
        _project(ctx).run(domain_policy_id="optimization/1", projection=projection)


def test_projector_rejects_abstract_hash_equality_even_without_abstract_text() -> None:
    ctx = _ctx()
    projection = _paper_a()
    projection.pop("abstract", None)
    projection["source_abstract_sha256"] = str(projection["paraphrase_sha256"])
    with pytest.raises(ValueError, match="abstract is not a mechanism paraphrase"):
        _project(ctx).run(domain_policy_id="optimization/1", projection=projection)


def test_projector_ignores_caller_supplied_digest_metadata() -> None:
    projection = _paper_a()
    projection["reviewed_projection_digest"] = "0" * 64
    ctx = _ctx(_approved_digests(_paper_a()))

    result = _project(ctx).run(domain_policy_id="optimization/1", projection=projection)

    assert result["created"] is True


def test_projector_rejects_missing_legacy_digest_without_mutating_record() -> None:
    projection = _non_nsqd_projection()
    approved_digests = _approved_digests(projection)
    original_ctx = _ctx(approved_digests)
    created = _project(original_ctx).run(domain_policy_id="optimization/1", projection=projection)
    legacy = original_ctx.records.get(str(created["record_id"]))
    assert legacy is not None
    legacy.pop("reviewed_projection_digest")
    legacy_records = NullCorpusRecordStore()
    legacy_records.put(legacy)
    repair_ctx = _ctx(approved_digests, records=legacy_records)

    with pytest.raises(ValueError, match="explicit immutable migration is required"):
        _project(repair_ctx).run(domain_policy_id="optimization/1", projection=projection)

    assert repair_ctx.records.get(str(created["record_id"])) == legacy


def test_projector_rejects_existing_different_review_digest() -> None:
    projection = _non_nsqd_projection()
    original_ctx = _ctx(_approved_digests(projection))
    _project(original_ctx).run(domain_policy_id="optimization/1", projection=projection)
    revised = dict(projection)
    revised["human_reviewer"] = "different-reviewer"
    revised_ctx = _ctx(_approved_digests(revised), records=original_ctx.records)

    with pytest.raises(ValueError, match="different reviewed projection metadata"):
        _project(revised_ctx).run(domain_policy_id="optimization/1", projection=revised)


def test_reviewed_projection_fields_contract_is_explicit_and_stable() -> None:
    assert REVIEWED_PROJECTION_FIELDS == (
        "domain_policy_id",
        "paraphrase",
        "paraphrase_source",
        "source_paper_id",
        "source",
        "coordinates",
        "source_abstract_sha256",
        "source_markdown_sha256",
        "paraphrase_sha256",
        "human_reviewer",
        "human_approved_at",
        "review_status",
    )
    assert canonical_reviewed_projection_digest(_paper_a()) == (
        "97e4966c16e253ad3a57d58cef191354412f802cb96084deec9e6109b5ed72e9"
    )


def test_canonical_reviewed_projection_digest_ignores_non_contract_metadata() -> None:
    projection = _paper_a()
    base = canonical_reviewed_projection_digest(projection)

    metadata_changed = dict(projection)
    metadata_changed["title"] = "Mutated title"
    metadata_changed["projector_version"] = "paper-projector/999"
    metadata_changed["overlap_check"] = {"max_contiguous_source_tokens": 1, "limit": 99}
    metadata_changed["extra_metadata"] = {"note": "ignored"}

    reviewed_changed = dict(projection)
    reviewed_changed["human_reviewer"] = "another-reviewer"
    source_changed = dict(projection)
    source_changed["source"] = "doi:10.2139/changed"
    coordinates_changed = dict(projection)
    coordinates_changed["coordinates"] = {
        "problem": "unconstrained",
        "method": "first-order",
        "setting": "full-rank",
    }

    assert canonical_reviewed_projection_digest(metadata_changed) == base
    assert canonical_reviewed_projection_digest(reviewed_changed) != base
    assert canonical_reviewed_projection_digest(source_changed) != base
    assert canonical_reviewed_projection_digest(coordinates_changed) != base


def test_projector_rejects_oversized_canonical_payload() -> None:
    projection = _non_nsqd_projection()
    projection["paraphrase"] = "x" * 100_000
    projection["paraphrase_sha256"] = _normalized_paraphrase_hash(projection["paraphrase"])
    ctx = _ctx(_approved_digests(projection))

    with pytest.raises(ValueError, match="reviewed projection payload is too large"):
        _project(ctx).run(domain_policy_id="optimization/1", projection=projection)


def test_data_nsqd_04_cannot_credit_finance_policy() -> None:
    projection = _paper_a()
    projection["domain_policy_id"] = "finance/1"
    ctx = _ctx(_approved_digests(projection))

    with pytest.raises(ValueError, match="finance/1"):
        _project(ctx).run(domain_policy_id="finance/1", projection=projection)
    assert ctx.records.list_ids() == []


def test_data_nsqd_04_projects_into_optimization_policy() -> None:
    projection = _paper_a()
    ctx = _ctx(_approved_digests(projection))

    result = _project(ctx).run(domain_policy_id="optimization/1", projection=projection)
    assert result["created"] is True
    record_id = result["record_id"]
    stored = ctx.records.get(record_id)
    assert stored is not None
    assert stored["paraphrase"] == normalize_paraphrase(str(projection["paraphrase"]))
    assert stored["paraphrase"] != _abstract()
    assert stored["domain_policy_id"] == "optimization/1"
    assert stored["review_status"] == "approved"
    assert stored["projector_version"] == "paper-projector/1"
    assert stored["type"] == "paper"
    assert stored["record_id"] != stored["content_hash"]
    assert records_for_policy([stored], "finance/1") == []
    assert records_for_policy([stored], "optimization/1") == [stored]


def test_projector_normalizes_reviewed_fields_once_for_storage_and_hash() -> None:
    projection = _non_nsqd_projection()
    projection["paraphrase"] = "  Alpha\r\nBeta  "
    projection["paraphrase_sha256"] = _normalized_paraphrase_hash("Alpha\nBeta")
    projection["human_approved_at"] = datetime(2026, 8, 21, 19, 3, 54, tzinfo=UTC)
    projection["source"] = " https://doi.org/10.2139/SSRN.3725454/ "
    projection["coordinates"] = {
        "problem": " constrained-expectation ",
        "method": " sequential-quadratic ",
        "setting": " rank-deficient ",
    }
    ctx = _ctx(_approved_digests(projection))

    result = _project(ctx).run(domain_policy_id="optimization/1", projection=projection)

    stored = ctx.records.get(str(result["record_id"]))
    assert stored is not None
    assert stored["paraphrase"] == "Alpha\nBeta"
    assert stored["paraphrase_sha256"] == _normalized_paraphrase_hash("Alpha\nBeta")
    assert stored["human_approved_at"] == "2026-08-21T19:03:54+00:00"
    assert stored["source"] == "doi:10.2139/ssrn.3725454"
    assert stored["coordinates"] == {
        "problem": "constrained-expectation",
        "method": "sequential-quadratic",
        "setting": "rank-deficient",
    }
    assert stored["content_hash"] == sha256_hex(
        b'{"paraphrase":"Alpha\\nBeta","source":"doi:10.2139/ssrn.3725454","type":"paper"}'
    )


class _DirectLookupOnlyRecordStore(NullCorpusRecordStore):
    def __init__(self) -> None:
        super().__init__()
        self.list_ids_calls = 0

    def list_ids(self) -> list[str]:
        self.list_ids_calls += 1
        return super().list_ids()


def test_projection_is_idempotent_on_source_content_and_policy_without_full_scan() -> None:
    projection = _paper_a()
    records = _DirectLookupOnlyRecordStore()
    ctx = _ctx(_approved_digests(projection), records=records)

    first = _project(ctx).run(domain_policy_id="optimization/1", projection=projection)
    second = _project(ctx).run(domain_policy_id="optimization/1", projection=projection)
    assert second["created"] is False
    assert second["record_id"] == first["record_id"]
    assert second["snapshot_id"] == first["snapshot_id"]
    assert records.list_ids_calls == 2
    assert records.list_ids() == [first["record_id"]]


def test_projection_uses_distinct_record_ids_across_policies() -> None:
    finance_projection = _non_nsqd_projection(domain_policy_id="finance/1")
    optimization_projection = _non_nsqd_projection(domain_policy_id="optimization/1")
    ctx = _ctx(_approved_digests(finance_projection, optimization_projection))

    finance = _project(ctx).run(domain_policy_id="finance/1", projection=finance_projection)
    optimization = _project(ctx).run(
        domain_policy_id="optimization/1",
        projection=optimization_projection,
    )

    finance_record = ctx.records.get(str(finance["record_id"]))
    optimization_record = ctx.records.get(str(optimization["record_id"]))
    assert finance_record is not None
    assert optimization_record is not None
    assert finance_record["record_id"] != optimization_record["record_id"]
    assert finance_record["content_hash"] == optimization_record["content_hash"]
    assert finance_record["source_paper_id"] == optimization_record["source_paper_id"]
    assert finance_record["source"] == "paper:paper-source-21"
    assert optimization_record["source"] == "paper:paper-source-21"
    assert finance_record["coordinates"] == finance_projection["coordinates"]
    assert optimization_record["coordinates"] == optimization_projection["coordinates"]
    assert finance_record["domain_policy_id"] == "finance/1"
    assert optimization_record["domain_policy_id"] == "optimization/1"


def test_projection_uses_new_record_id_when_source_hashes_change() -> None:
    projection = _non_nsqd_projection()
    revised = dict(projection)
    revised["source_markdown_sha256"] = "a" * 64
    ctx = _ctx(_approved_digests(projection, revised))

    first = _project(ctx).run(domain_policy_id="optimization/1", projection=projection)
    second = _project(ctx).run(domain_policy_id="optimization/1", projection=revised)

    assert second["created"] is True
    assert second["record_id"] != first["record_id"]
    assert second["snapshot_id"] != first["snapshot_id"]
    assert len(ctx.records.list_ids()) == 2


def test_importing_a_paper_does_not_write_corpus_records() -> None:
    ctx = _ctx()
    assert ctx.records.list_ids() == []
    assert ctx.snapshots.get("unused") is None


def test_handle_project_job() -> None:
    projection = _paper_a()
    ctx = _ctx(_approved_digests(projection))
    job = NsqdJob(
        job_id="jp",
        type="project",
        status="running",
        payload={"domain_policy_id": "optimization/1", "projection": projection},
        attempts=1,
        max_attempts=3,
        run_after=None,
    )
    result = handle_project(ctx, job)
    assert result["status"] == "succeeded"
    assert result["created"] is True
    stored = ctx.records.get(str(result["record_id"]))
    assert stored is not None
    assert stored["domain_policy_id"] == "optimization/1"
