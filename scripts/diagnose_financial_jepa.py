from __future__ import annotations

import argparse
import sys
from pathlib import Path

import httpx

from nsqd.infrastructure.workflow_output import WorkflowOutputError
from research.financial_jepa.contracts import (
    Deadline,
    DeadlineExceededError,
    JsonValue,
    ProtocolError,
)
from research.financial_jepa.dataset import prepare_development
from research.financial_jepa.diagnostic_contracts import DiagnosticConfig
from research.financial_jepa.diagnostic_workflow import (
    PreparedDiagnosticRequest,
    run_prepared_diagnostics,
)
from research.financial_jepa.provenance import cache_metadata_record, rights_metadata
from research.financial_jepa.treasury import AcquisitionRequest, acquire_years, parse_years

REPO_ROOT = Path(__file__).resolve().parents[1]


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Run the development-only YieldJEPA four-way diagnostics. Default output: "
            "output/financial-jepa-diagnostics/<UTC-run-id>."
        )
    )
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=REPO_ROOT / "data/research/financial-jepa/treasury",
    )
    parser.add_argument("--offline", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--output-dir", type=Path)
    return parser


def _validate_paths(data_dir: Path, output_dir: Path | None) -> None:
    repository = REPO_ROOT.resolve()
    source = data_dir.resolve()
    expected_source = repository / "data/research/financial-jepa/treasury"
    temporary = Path("/tmp").resolve()
    if source != expected_source and not source.is_relative_to(temporary):
        raise ProtocolError("data directory must be the isolated Treasury cache or temporary")
    if output_dir is None:
        return
    output = output_dir.resolve()
    expected_output = repository / "output/financial-jepa-diagnostics"
    if not output.is_relative_to(expected_output) and not output.is_relative_to(temporary):
        raise ProtocolError("output directory must be below diagnostics output or temporary")
    if output.is_relative_to(repository / "output/financial-jepa"):
        raise ProtocolError("diagnostics cannot use the original financial-jepa output namespace")


def main() -> int:
    arguments = _parser().parse_args()
    data_dir: Path = arguments.data_dir
    output_dir: Path | None = arguments.output_dir
    config = DiagnosticConfig()
    deadline = Deadline.start(config.deadline_seconds)
    try:
        _validate_paths(data_dir, output_dir)
        if arguments.offline and not data_dir.is_dir():
            raise ProtocolError("offline Treasury cache directory does not exist")
        receipt = acquire_years(
            AcquisitionRequest(config.training_config(), data_dir, arguments.offline, deadline)
        )
        parsed = parse_years(receipt.files)
        prepared = prepare_development(parsed.rows, config.training_config())
        source = rights_metadata()
        source["yearly_responses"] = [
            cache_metadata_record(metadata) for metadata in receipt.metadata
        ]
        source["dropped_missing_dates"] = [day.isoformat() for day in parsed.dropped_missing_dates]
        missing_rows: list[JsonValue] = []
        for day, missing_fields in parsed.missing_fields_by_date:
            missing_rows.append({"date": day.isoformat(), "fields": list(missing_fields)})
        source["missing_tenor_rows"] = missing_rows
        run_root = run_prepared_diagnostics(
            PreparedDiagnosticRequest(REPO_ROOT, output_dir, config, prepared, source, deadline)
        )
    except (
        ProtocolError,
        DeadlineExceededError,
        WorkflowOutputError,
        FileExistsError,
        OSError,
        httpx.HTTPError,
    ) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    print(run_root)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
