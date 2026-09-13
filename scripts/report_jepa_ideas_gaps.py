from __future__ import annotations

import argparse
import hashlib
import json
import sys
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Final

if __name__ == "__main__" and not __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from nsqd.domain.trusted_files import read_verified_repo_file
from nsqd.infrastructure.workflow_output import create_run_directory
from papers.domain import (
    InvestigationPlan,
    InvestigationPlanValidationContext,
    investigation_plan_schema,
    parse_investigation_plan_json,
)
from scripts._jepa_investigation_plan import build_investigation_plan
from scripts._jepa_report_rendering import render_report
from scripts._jepa_report_types import EvidenceRef, Experiment, Gap, RetainedHypothesis

REPO_ROOT: Final = Path(__file__).resolve().parents[1]
WORKFLOW: Final = "jepa-finance-gap-analysis"
PACKET_ROOT: Final = Path("docs/reviews/nsqd-jepa-ideas-gaps-2026-09-01")
PROJECTION_ROOT: Final = Path("docs/reviews/nsqd-projection-review-2026-08-28/final")
MODE: Final = "retained_evidence_synthesis"
MAX_INPUT_BYTES: Final = 8 * 1024 * 1024


def _read_packet(name: str) -> tuple[bytes, dict[str, Any]]:
    raw = read_verified_repo_file(
        repo_root=REPO_ROOT,
        relative_path=PACKET_ROOT / name,
        expected_root=PACKET_ROOT,
        field=name,
        max_bytes=MAX_INPUT_BYTES,
    )
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise ValueError(f"{name} must contain a JSON object")
    return raw, value


def _read_packet_json(name: str) -> dict[str, Any]:
    return _read_packet(name)[1]


def _build_investigation_plan(
    results: dict[str, Any], ledger: dict[str, Any], prior_art: dict[str, Any]
) -> InvestigationPlan:
    plan = build_investigation_plan(results, ledger, prior_art)
    allowed_sources = frozenset(source.paper_id for source in plan.sources)
    return parse_investigation_plan_json(
        plan.model_dump_json(),
        InvestigationPlanValidationContext(
            expected_question=plan.question,
            allowed_source_ids=allowed_sources,
            allowed_execution_evidence_refs=frozenset(),
        ),
    )


def _build_report_data(
    results: dict[str, Any],
    ledger: dict[str, Any],
    prior_art: dict[str, Any],
) -> dict[str, Any]:
    plan = _build_investigation_plan(results, ledger, prior_art)
    facts = {
        str(row["fact_id"]): EvidenceRef(
            fact_id=str(row["fact_id"]),
            record_id=str(row["source_record_id"]),
            claim=str(row["claim"]),
        )
        for row in results["extracted_facts"]
    }
    overlap = {str(row["source_idea_id"]): row for row in prior_art["candidate_assessments"]}
    coverage = []
    feature_matrix = results["cooccurrence_snapshot"]["feature_matrix"]
    for record in ledger["records"]:
        record_id = str(record["record_id"])
        coverage.append(
            {
                "record_id": record_id,
                "title": str(record["title"]),
                "corpus_role": str(record["corpus_role"]),
                "features": list(feature_matrix[record_id]),
            }
        )
    gaps = [
        asdict(
            Gap(
                gap_id=str(row["gap_id"]),
                title=str(row["title"]),
                inference=str(row["inference"]),
                uncertainty=str(row["uncertainty"]),
                supporting_evidence=tuple(facts[str(item)] for item in row["supporting_fact_ids"]),
            )
        )
        for row in results["inferred_gaps"]
    ]
    hypotheses = []
    for row in results["proposed_ideas"]:
        hypothesis_id = str(row["candidate_id"])
        experiment = row["falsifiable_test"]
        assessment = overlap[hypothesis_id]
        hypotheses.append(
            asdict(
                RetainedHypothesis(
                    hypothesis_id=hypothesis_id,
                    title=str(row["title"]),
                    mechanistic_bridge=str(row["mechanistic_bridge"]),
                    supporting_evidence=tuple(
                        facts[str(item)] for item in row["supporting_fact_ids"]
                    ),
                    experiment=Experiment(
                        design=str(experiment["design"]),
                        baselines=str(experiment["design"]),
                        primary_metric=str(experiment["primary_metric"]),
                        secondary_metrics=tuple(
                            str(item) for item in experiment["secondary_metrics"]
                        ),
                        reject_condition=str(experiment["failure_condition"]),
                    ),
                    overlap_caveat=str(assessment["narrowed_overlap_conclusion"]),
                    remaining_question=str(assessment["remaining_question"]),
                )
            )
        )
    return {
        "schema_version": 2,
        "mode": MODE,
        "report_state": {
            "scope": "retained_evidence_synthesis_and_investigation_planning",
            "status": "not_started",
            "runtime_authorized": False,
            "execution_performed": False,
        },
        "investigation_plan": plan.model_dump(mode="json"),
        "coverage_matrix": coverage,
        "gaps": gaps,
        "retained_hypotheses": hypotheses,
        "limitations": [
            str(results["cooccurrence_snapshot"]["limitation"]),
            str(ledger["interpretation_boundary"]),
            *[str(item) for item in prior_art["known_limitations"]],
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Render retained, evidence-backed JEPA finance gaps and ideas. Output defaults to "
            "output/jepa-finance-gap-analysis/<UTC-run-id>."
        )
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="fresh directory below output/ or system temp; default: "
        "output/jepa-finance-gap-analysis/<UTC-run-id>",
    )
    args = parser.parse_args()
    results_raw, results = _read_packet("results.json")
    ledger_raw, ledger = _read_packet("source-ledger.json")
    prior_art_raw, prior_art = _read_packet("operator-e-broader-prior-art.json")
    source_inputs = {
        "results.json": results_raw,
        "source-ledger.json": ledger_raw,
        "operator-e-broader-prior-art.json": prior_art_raw,
    }
    data = _build_report_data(results, ledger, prior_art)
    plan = InvestigationPlan.model_validate(data["investigation_plan"])
    output_dir = create_run_directory(REPO_ROOT, WORKFLOW, args.output_dir)
    excerpts_dir = output_dir / "cited-excerpts"
    excerpts_dir.mkdir()
    citations = []
    for record in ledger["records"]:
        logical_path = PROJECTION_ROOT / str(record["approved_excerpt"])
        content = read_verified_repo_file(
            repo_root=REPO_ROOT,
            relative_path=logical_path,
            expected_root=PROJECTION_ROOT,
            field="approved_excerpt",
            max_bytes=MAX_INPUT_BYTES,
        )
        copied_name = f"{record['record_id']}.md"
        (excerpts_dir / copied_name).write_bytes(content)
        citations.append(
            {
                "record_id": str(record["record_id"]),
                "source_paper_id": str(record["source_paper_id"]),
                "primary_full_text_url": str(record["primary_full_text_url"]),
                "logical_excerpt_path": str(logical_path),
                "excerpt_sha256": hashlib.sha256(content).hexdigest(),
                "copied_path": f"cited-excerpts/{copied_name}",
            }
        )
    provenance = {
        "schema_version": 2,
        "mode": MODE,
        "generated_at_utc": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "source_cutoffs_utc": [str(ledger["cutoff_utc"]), str(prior_art["cutoff_utc"])],
        "new_literature_search_performed": False,
        "new_backtest_performed": False,
        "source_artifact_sha256": {
            name: hashlib.sha256(content).hexdigest() for name, content in source_inputs.items()
        },
        "input_bundle_sha256": hashlib.sha256(
            b"".join(
                name.encode("utf-8") + b"\0" + len(content).to_bytes(8, "big") + content
                for name, content in sorted(source_inputs.items())
            )
        ).hexdigest(),
        "investigation_plan_schema_sha256": hashlib.sha256(
            json.dumps(investigation_plan_schema(), sort_keys=True, separators=(",", ":")).encode(
                "utf-8"
            )
        ).hexdigest(),
        "citations": citations,
    }
    (output_dir / "report.md").write_text(render_report(data, plan), encoding="utf-8")
    (output_dir / "report-data.json").write_text(
        json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (output_dir / "provenance.json").write_text(
        json.dumps(provenance, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "output_dir": str(output_dir),
                "mode": MODE,
                "gap_count": len(data["gaps"]),
                "hypothesis_count": len(data["retained_hypotheses"]),
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
