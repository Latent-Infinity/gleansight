from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone
from itertools import permutations
from pathlib import Path

import pytest
import yaml

from nsqd.domain.card import card_decision, corpus_ingest_rejection, missing_card_fields
from nsqd.domain.descriptor import cell_id_from_descriptor
from nsqd.domain.elite import choose_elite
from nsqd.domain.grounding import classify_local
from nsqd.domain.novelty import mean_cosine_distance, novelty_term
from nsqd.domain.snapshot import normalize_source, record_content_hash, snapshot_id
from nsqd.domain.status import cell_status, record_lifecycle
from nsqd.domain.viability import score_dpred, score_dval, score_fals, score_mech, viability

AS_OF = datetime(2024, 1, 1, tzinfo=UTC)
RECENT = AS_OF - timedelta(days=10)
STALE = AS_OF - timedelta(days=365 * 3)
NSQD_FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "approved" / "nsqd"
CAL = {"snapshot_state": "calibration", "inspected": True, "expected": True}


def _rec(
    type: str,
    harvested: datetime | None = None,
    *,
    tags: list[str] | None = None,
    invalid: str | None = None,
) -> dict[str, object]:
    row: dict[str, object] = {"type": type}
    if harvested is not None:
        row["harvested_at"] = harvested
    if tags is not None:
        row["tags"] = tags
    if invalid is not None:
        row["invalid_reason"] = invalid
    return row


def test_snapshot_digest_known_vectors_and_order_invariance() -> None:
    content = record_content_hash(
        type="paper",
        paraphrase="Condition allocation trust on dealer-hedging convexity regime.",
        source="doi:10.0000/example",
    )
    assert content == "3036b024a7a63dc6116f42e11a04d2b29ae382abfffc878dcdff890c73e15ced"
    records_a = [
        {"record_id": "rec-b", "content_hash": "0" * 64},
        {"record_id": "rec-a", "content_hash": content},
    ]
    records_b = list(reversed(records_a))
    sid = snapshot_id(records=records_a, schema_version=1)
    assert sid == snapshot_id(records=records_b, schema_version=1)
    assert sid == "00b5ac629b90943fd9cc61b7361f8941d2dd1e7e8b0367ffb9c0c65fe2f8a9b4"
    assert snapshot_id(records=records_a, schema_version=2) == (
        "d08d2cbf7ea0ccb830af4d9ab21ae2eb816f6bdf23209f8f976e3990159209db"
    )
    assert snapshot_id(records=[], schema_version=1) == (
        "16bf24d404b6914dd084140cfc2ff9adc145ed6a3db2fe852f20b47f5bab0d6c"
    )


def test_snapshot_id_rejects_duplicate_record_ids() -> None:
    with pytest.raises(ValueError, match="duplicate record_id"):
        snapshot_id(
            records=[
                {"record_id": "rec-a", "content_hash": "0" * 64},
                {"record_id": "rec-a", "content_hash": "1" * 64},
            ],
            schema_version=1,
        )


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("doi:10.0000/example", "doi:10.0000/example"),
        ("DOI:10.0000/EXAMPLE/", "doi:10.0000/example"),
        ("https://doi.org/10.0000/example", "doi:10.0000/example"),
        ("https://DOI.org/10.0000/Example/", "doi:10.0000/example"),
        ("http://doi.org/10.0000/example", "doi:10.0000/example"),
        ("10.1234/AbC", "doi:10.1234/abc"),
        (
            "HTTPS://Example.COM/path/#frag/",
            "https://example.com/path",
        ),
        ("http://Example.COM", "http://example.com"),
        ("  plain Source  ", "plain Source"),
        ("line\r\nbreak", "line\nbreak"),
    ],
)
def test_source_normalization_cases(source: str, expected: str) -> None:
    assert normalize_source(source) == expected


def test_smoke_forces_novelty_and_viability_zero() -> None:
    assert mean_cosine_distance([]) is None
    nov = novelty_term(evidence=None, snapshot_state="smoke_only", grounding_class="unevaluated")
    assert nov == 0
    assert viability(nov=0, mech=5, fals=5, dpred=5, dval=5) == 0


def test_novelty_evidence_mean_and_k_sizes() -> None:
    assert mean_cosine_distance([0.0]) == 0.0
    assert mean_cosine_distance([0.2, 0.4]) == pytest.approx(0.3)
    under_k = [0.10, 0.20, 0.30]
    assert len(under_k) < 5
    assert mean_cosine_distance(under_k) == pytest.approx(0.20)
    exact_k = [0.10, 0.20, 0.30, 0.40, 0.50]
    assert mean_cosine_distance(exact_k) == pytest.approx(0.30)


@pytest.mark.parametrize(
    ("evidence", "snapshot_state", "grounding_class", "expected"),
    [
        (0.90, "production_valid", "already_done", 0),
        (0.90, "production_valid", "renamed", 0),
        (0.90, "smoke_only", "orthogonal", 0),
        (None, "calibration", "orthogonal", 0),
        (0.00, "calibration", "orthogonal", 1),
        (0.14, "calibration", "orthogonal", 1),
        (0.15, "calibration", "orthogonal", 2),
        (0.29, "production_valid", "orthogonal", 2),
        (0.30, "calibration", "clean_gap", 3),
        (0.44, "calibration", "orthogonal", 3),
        (0.45, "calibration", "orthogonal", 4),
        (0.59, "calibration", "orthogonal", 4),
        (0.60, "calibration", "orthogonal", 5),
        (0.70, "production_valid", "orthogonal", 5),
        (0.70, "calibration", "already_done", 0),
    ],
)
def test_novelty_term_bins(
    evidence: float | None,
    snapshot_state: str,
    grounding_class: str,
    expected: int,
) -> None:
    assert (
        novelty_term(
            evidence=evidence,
            snapshot_state=snapshot_state,  # type: ignore[arg-type]
            grounding_class=grounding_class,  # type: ignore[arg-type]
        )
        == expected
    )


def test_novelty_threshold_tau_is_unset_and_report_only() -> None:
    from nsqd.domain.novelty import (
        NOVELTY_THRESHOLD_TAU,
        apply_novelty_threshold,
        novelty_term,
    )

    assert NOVELTY_THRESHOLD_TAU is None
    term = novelty_term(
        evidence=0.0,
        snapshot_state="calibration",
        grounding_class="orthogonal",
    )
    assert term == 1
    assert apply_novelty_threshold(term, evidence=0.0) == 1
    assert apply_novelty_threshold(term, evidence=0.0, tau=None) == 1
    assert apply_novelty_threshold(term, evidence=0.0, tau=0.15) == 0
    with pytest.raises(ValueError, match="tau must be a non-negative number or unset"):
        apply_novelty_threshold(term, evidence=0.0, tau=-0.1)
    with pytest.raises(ValueError, match="tau must be a non-negative number or unset"):
        apply_novelty_threshold(term, evidence=0.0, tau=True)


def test_viability_zero_paths_and_finance_presence() -> None:
    empty = {
        field: ""
        for field in (
            "mechanism",
            "inefficiency",
            "counterparty",
            "persistence",
            "capacity",
            "regime_dependence",
        )
    }
    assert score_mech(empty, domain_pack="finance/1") == 0
    whitespace = dict.fromkeys(empty, "  ")
    assert score_mech(whitespace, domain_pack="finance/1") == 0
    none_fields = dict.fromkeys(empty, None)
    assert score_mech(none_fields, domain_pack="finance/1") == 0
    filled = dict.fromkeys(empty, "present")
    assert score_mech(filled, domain_pack="finance/1") == 5
    assert score_mech(filled, domain_pack="other/1") == 0
    assert score_fals({"cheapest_falsifier": "", "kill_criteria": "x"}) == 0
    assert score_fals({"cheapest_falsifier": "x", "kill_criteria": "  "}) == 0
    assert score_fals({"cheapest_falsifier": "x", "kill_criteria": "y"}) == 5
    assert score_dpred({"differential_prediction": ""}) == 0
    assert score_dpred({"differential_prediction": "present"}) == 5
    assert score_dval({}) == 0
    assert score_dval({"dval": "5"}) == 0
    assert (
        score_dval(
            {
                "dval": {
                    "value": 5,
                    "assigned_by": "",
                    "assigned_at": "2026-08-18T00:00:00+00:00",
                    "rubric_id": "finance/dval/1",
                }
            }
        )
        == 0
    )
    assert (
        score_dval(
            {
                "dval": {
                    "value": 5,
                    "assigned_by": "product",
                    "assigned_at": "2026-08-18T00:00:00+00:00",
                    "rubric_id": "",
                }
            }
        )
        == 0
    )
    assert (
        score_dval(
            {
                "dval": {
                    "value": 5,
                    "assigned_by": "product",
                    "assigned_at": None,
                    "rubric_id": "finance/dval/1",
                }
            }
        )
        == 0
    )
    assert (
        score_dval(
            {
                "dval": {
                    "value": 5,
                    "assigned_by": "product",
                    "assigned_at": "2026-08-18T00:00:00",
                    "rubric_id": "finance/dval/1",
                }
            }
        )
        == 0
    )
    assert (
        score_dval(
            {
                "dval": {
                    "value": 5,
                    "assigned_by": "product",
                    "assigned_at": "2026-08-18T00:00:00+01:00",
                    "rubric_id": "finance/dval/1",
                }
            }
        )
        == 0
    )
    assert (
        score_dval(
            {
                "dval": {
                    "value": 5,
                    "assigned_by": "product",
                    "assigned_at": datetime(2026, 8, 18, 0, 0, 0),
                    "rubric_id": "finance/dval/1",
                }
            }
        )
        == 0
    )
    assert (
        score_dval(
            {
                "dval": {
                    "value": 5,
                    "assigned_by": "product",
                    "assigned_at": datetime(
                        2026, 8, 18, 0, 0, 0, tzinfo=timezone(timedelta(hours=1))
                    ),
                    "rubric_id": "finance/dval/1",
                }
            }
        )
        == 0
    )
    assert (
        score_dval(
            {
                "dval": {
                    "value": 9,
                    "assigned_by": "product",
                    "assigned_at": "2026-08-18T00:00:00+00:00",
                    "rubric_id": "finance/dval/1",
                }
            }
        )
        == 0
    )
    assert (
        score_dval(
            {
                "dval": {
                    "value": "5",
                    "assigned_by": "product",
                    "assigned_at": "2026-08-18T00:00:00+00:00",
                    "rubric_id": "finance/dval/1",
                }
            }
        )
        == 0
    )
    assert (
        score_dval(
            {
                "dval": {
                    "value": 3,
                    "assigned_by": "product",
                    "assigned_at": datetime(2026, 8, 18, 0, 0, 0, tzinfo=UTC),
                    "rubric_id": "finance/dval/1",
                }
            }
        )
        == 3
    )
    assert (
        score_dval(
            {
                "dval": {
                    "value": 4,
                    "assigned_by": "product",
                    "assigned_at": "2026-08-18T00:00:00Z",
                    "rubric_id": "finance/dval/1",
                }
            }
        )
        == 4
    )
    assert (
        score_dval(
            {
                "dval": {
                    "value": 5,
                    "assigned_by": "product",
                    "assigned_at": "2026-08-18T00:00:00+00:00",
                    "rubric_id": "finance/dval/1",
                }
            }
        )
        == 5
    )
    assert viability(nov=5, mech=5, fals=5, dpred=5, dval=0) == 0
    assert viability(nov=1, mech=5, fals=5, dpred=5, dval=5) == 625


@pytest.mark.parametrize(
    ("records", "kwargs", "expected"),
    [
        (
            [],
            {**CAL, "invalid_reason": "malformed-cell"},
            "Invalid",
        ),
        (
            [_rec("paper", RECENT, invalid="bad-row")],
            CAL,
            "Invalid",
        ),
        (
            [_rec("paper", RECENT) for _ in range(6)] + [_rec("code", RECENT)],
            {**CAL, "snapshot_state": "smoke_only"},
            "Unknown",
        ),
        (
            [_rec("paper", RECENT)],
            {**CAL, "disagreement": True},
            "Unknown",
        ),
        (
            [],
            {"snapshot_state": "calibration", "inspected": False, "expected": False},
            "Unknown",
        ),
        (
            [_rec("paper", RECENT, tags=["future_work"])],
            CAL,
            "Future-work-only",
        ),
        (
            [_rec("paper", STALE, tags=["stalled"])],
            CAL,
            "Stalled",
        ),
        (
            [_rec("code", STALE, tags=["abandoned"])],
            CAL,
            "Stalled",
        ),
        (
            [],
            CAL,
            "Missing",
        ),
        (
            [_rec("paper", RECENT)],
            CAL,
            "Code-gap",
        ),
        (
            [_rec("paper", RECENT) for _ in range(6)],
            CAL,
            "Code-gap",
        ),
        (
            [_rec("paper", RECENT) for _ in range(6)] + [_rec("code", RECENT)],
            {**CAL, "method_claims_evaluation": True},
            "Benchmark-gap",
        ),
        (
            [_rec("paper", RECENT) for _ in range(6)] + [_rec("code", RECENT)],
            CAL,
            "Mature",
        ),
        (
            [_rec("paper", RECENT) for _ in range(3)] + [_rec("code", RECENT)],
            CAL,
            "Active",
        ),
        (
            [_rec("paper", datetime(2023, 12, 31)) for _ in range(3)]
            + [_rec("code", datetime(2023, 12, 31))],
            CAL,
            "Unknown",
        ),
        (
            [_rec("paper", RECENT.astimezone(timezone(timedelta(hours=1)))) for _ in range(3)]
            + [_rec("code", RECENT.astimezone(timezone(timedelta(hours=1))))],
            CAL,
            "Unknown",
        ),
        (
            [_rec("benchmark", RECENT)],
            CAL,
            "Sparse",
        ),
        (
            [_rec("paper", RECENT), _rec("code", RECENT)],
            CAL,
            "Sparse",
        ),
        (
            [_rec("paper", STALE) for _ in range(3)] + [_rec("code", STALE)],
            CAL,
            "Unknown",
        ),
        (
            [],
            {"snapshot_state": "calibration", "inspected": True, "expected": False},
            "Unknown",
        ),
    ],
)
def test_status_table_and_overlaps(
    records: list[dict[str, object]],
    kwargs: dict[str, object],
    expected: str,
) -> None:
    assert cell_status(records, as_of=AS_OF, **kwargs) == expected  # type: ignore[arg-type]


def test_status_policies_reject_non_utc_as_of() -> None:
    naive = datetime(2024, 1, 1)
    plus_one = datetime(2024, 1, 1, tzinfo=timezone(timedelta(hours=1)))

    with pytest.raises(ValueError, match="as_of must be a UTC datetime"):
        record_lifecycle(_rec("paper", RECENT), as_of=naive)
    with pytest.raises(ValueError, match="as_of must be a UTC datetime"):
        cell_status([], as_of=plus_one, **CAL)


def test_record_lifecycle_bins() -> None:
    assert record_lifecycle(_rec("paper", RECENT, invalid="x"), as_of=AS_OF) == "invalid"
    assert record_lifecycle(_rec("paper", RECENT, tags=["future_work"]), as_of=AS_OF) == (
        "future_work"
    )
    assert record_lifecycle(_rec("paper", RECENT, tags=["stalled"]), as_of=AS_OF) == "attempted"
    assert record_lifecycle(_rec("paper", RECENT), as_of=AS_OF) == "current"
    assert record_lifecycle(_rec("paper", STALE), as_of=AS_OF) == "stale"
    assert record_lifecycle({"type": "paper", "harvested_at": "not-a-dt"}, as_of=AS_OF) == "stale"
    assert (
        record_lifecycle(
            {"type": "paper", "harvested_at": datetime(2023, 12, 31)},
            as_of=AS_OF,
        )
        == "stale"
    )
    assert (
        record_lifecycle(
            {
                "type": "paper",
                "harvested_at": datetime(2023, 12, 31, tzinfo=timezone(timedelta(hours=1))),
            },
            as_of=AS_OF,
        )
        == "stale"
    )
    assert record_lifecycle(_rec("benchmark", RECENT), as_of=AS_OF) == "stale"


def test_status_window_default_is_730_days_and_overridable() -> None:
    from nsqd.domain.status import (
        DEFAULT_STATUS_WINDOW,
        STATUS_WINDOW_DAYS,
        record_lifecycle,
        require_status_window_days,
        status_window,
    )

    assert STATUS_WINDOW_DAYS == 730
    assert DEFAULT_STATUS_WINDOW == timedelta(days=730)
    assert require_status_window_days(None) == 730
    assert status_window() == timedelta(days=730)
    assert status_window(365) == timedelta(days=365)
    with pytest.raises(ValueError, match="window_days must be a positive int"):
        require_status_window_days(0)
    with pytest.raises(ValueError, match="window_days must be a positive int"):
        require_status_window_days(True)

    on_cutoff = _rec("paper", AS_OF - timedelta(days=730))
    older = _rec("paper", AS_OF - timedelta(days=731))
    assert record_lifecycle(on_cutoff, as_of=AS_OF) == "current"
    assert record_lifecycle(older, as_of=AS_OF) == "stale"
    assert record_lifecycle(older, as_of=AS_OF, window=status_window(1095)) == "current"
    mid = _rec("paper", AS_OF - timedelta(days=400))
    assert record_lifecycle(mid, as_of=AS_OF) == "current"
    assert record_lifecycle(mid, as_of=AS_OF, window=status_window(365)) == "stale"


def test_elite_replacement_and_hash_tie_and_rejection() -> None:
    low = {"viability": 2, "candidate_artifact_hash": "b"}
    high = {"viability": 9, "candidate_artifact_hash": "z"}
    assert choose_elite(cell_elite=None, candidate=high) == high
    assert choose_elite(cell_elite=low, candidate=high) == high
    assert choose_elite(cell_elite=high, candidate=low) == high
    a = {"viability": 5, "candidate_artifact_hash": "aaa"}
    b = {"viability": 5, "candidate_artifact_hash": "bbb"}
    assert choose_elite(cell_elite=b, candidate=a) == a
    assert choose_elite(cell_elite=a, candidate=b) == a
    same = {"viability": 5, "candidate_artifact_hash": "aaa"}
    assert choose_elite(cell_elite=a, candidate=same) == a
    assert (
        choose_elite(cell_elite=a, candidate={"viability": 0, "candidate_artifact_hash": "0"}) == a
    )
    assert (
        choose_elite(cell_elite=None, candidate={"viability": 0, "candidate_artifact_hash": "x"})
        is None
    )


def test_elite_replay_is_order_independent() -> None:
    cards = [
        {"viability": 4, "candidate_artifact_hash": "ccc"},
        {"viability": 9, "candidate_artifact_hash": "zzz"},
        {"viability": 9, "candidate_artifact_hash": "aaa"},
        {"viability": 0, "candidate_artifact_hash": "000"},
    ]

    def replay(order: tuple[dict[str, object], ...]) -> dict[str, object] | None:
        elite: dict[str, object] | None = None
        for card in order:
            elite = choose_elite(cell_elite=elite, candidate=card)
        return elite

    elites = [replay(order) for order in permutations(cards)]
    assert all(item == elites[0] for item in elites)
    assert elites[0] == {"viability": 9, "candidate_artifact_hash": "aaa"}


def test_card_schema_rejects_each_required_field() -> None:
    base: dict[str, object] = {
        field: "x"
        for field in (
            "card_id",
            "domain_policy_id",
            "cell_id",
            "archive_cell_key",
            "title",
            "generating_operator",
            "snapshot_id",
            "corpus_version",
            "viability",
            "nov",
            "mech",
            "fals",
            "dpred",
            "dval",
            "candidate_artifact_hash",
            "card_decision",
        )
    }
    assert missing_card_fields(base) == []
    for field in base:
        broken = dict(base)
        broken.pop(field)
        assert missing_card_fields(broken) == [field]
        broken = dict(base)
        broken[field] = ""
        assert missing_card_fields(broken) == [field]
        broken[field] = None
        assert missing_card_fields(broken) == [field]


def test_requirement_card_is_rejected_as_corpus_record() -> None:
    assert corpus_ingest_rejection({"kind": "candidate-requirement-card"}) == (
        "requirement-card is not a corpus record"
    )
    assert corpus_ingest_rejection({"kind": "paper", "type": "paper"}) is None


def test_grounding_classes_are_deterministic() -> None:
    klass, conf, layers = classify_local(
        exact_source_hit=True,
        terminology_hit=False,
        evidence=0.9,
        code_or_benchmark_hit=False,
    )
    assert klass == "already_done"
    assert conf == 1.0
    assert layers[0].layer == 1
    klass, conf, layers = classify_local(
        exact_source_hit=False,
        terminology_hit=True,
        evidence=0.9,
        code_or_benchmark_hit=False,
    )
    assert klass == "renamed"
    assert conf == 0.8
    assert layers[1].layer == 2
    klass, conf, _ = classify_local(
        exact_source_hit=False,
        terminology_hit=False,
        evidence=0.10,
        code_or_benchmark_hit=False,
    )
    assert klass == "related_partial"
    assert conf == 0.6
    klass, conf, _ = classify_local(
        exact_source_hit=False,
        terminology_hit=False,
        evidence=0.15,
        code_or_benchmark_hit=False,
    )
    assert klass == "orthogonal"
    assert conf == 0.5
    klass, conf, layers = classify_local(
        exact_source_hit=False,
        terminology_hit=False,
        evidence=None,
        code_or_benchmark_hit=True,
    )
    assert klass == "already_done"
    assert conf == 0.9
    assert layers[-1].layer == 4
    klass, conf, _ = classify_local(
        exact_source_hit=False,
        terminology_hit=False,
        evidence=None,
        code_or_benchmark_hit=False,
    )
    assert klass == "unevaluated"
    assert conf == 0.0


def test_fixture_expected_outcomes_match_gate_oracles() -> None:
    for name in ("gamma-flow.yaml", "mechanism-free.yaml"):
        payload = yaml.safe_load((NSQD_FIXTURES / name).read_text(encoding="utf-8"))
        assert payload["kind"] == "candidate-requirement-card"
        assert corpus_ingest_rejection(payload) is not None
        expected = payload["expected_outcomes"]
        nov = novelty_term(
            evidence=expected["evidence"],
            snapshot_state=expected["snapshot_state"],
            grounding_class="unevaluated",
        )
        mech = score_mech(payload, domain_pack=payload["domain_policy_id"])
        fals = score_fals(payload)
        dpred = score_dpred(payload)
        dval = score_dval(payload)
        via = viability(nov=nov, mech=mech, fals=fals, dpred=dpred, dval=dval)
        assert nov == expected["nov"]
        assert mech == expected["mech"]
        assert fals == expected["fals"]
        assert dpred == expected["dpred"]
        assert dval == expected["dval"]
        assert via == expected["viability"]
        assert expected["archive_eligible"] is False
        assert expected["card_decision"] == "rejected"
        assert expected["snapshot_empty"] is True
        elite = choose_elite(
            cell_elite=None,
            candidate={"viability": via, "candidate_artifact_hash": "fixture"},
        )
        assert elite is None


def test_cell_id_from_closed_vocab_and_rejects_unknown() -> None:
    assert (
        cell_id_from_descriptor(
            {"mechanism": "flow-driven", "target": "drawdown", "horizon": "intraday"}
        )
        == "mechanism=flow-driven|target=drawdown|horizon=intraday"
    )
    with pytest.raises(ValueError, match="unlisted"):
        cell_id_from_descriptor(
            {"mechanism": "invented", "target": "drawdown", "horizon": "intraday"}
        )
    assert card_decision(0) == "rejected"
    assert card_decision(1) == "accepted"
