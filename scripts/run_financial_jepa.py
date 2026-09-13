from __future__ import annotations

import argparse
import sys
from pathlib import Path

import httpx

from nsqd.infrastructure.workflow_output import WorkflowOutputError
from research.financial_jepa.contracts import (
    Deadline,
    DeadlineExceededError,
    ExperimentConfig,
    JsonValue,
    ProtocolError,
)
from research.financial_jepa.dataset import prepare_splits
from research.financial_jepa.experiment import ExperimentRequest, run_prepared_experiment
from research.financial_jepa.provenance import cache_metadata_record, rights_metadata
from research.financial_jepa.treasury import (
    AcquisitionRequest,
    acquire_years,
    parse_years,
)

REPO_ROOT = Path(__file__).resolve().parents[1]


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Run the frozen independent YieldJEPA protocol. Default output: "
            "output/financial-jepa/<UTC-run-id>."
        )
    )
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=REPO_ROOT / "data/research/financial-jepa/treasury",
    )
    parser.add_argument("--offline", action="store_true")
    parser.add_argument("--output-dir", type=Path)
    return parser


def main() -> int:
    arguments = _parser().parse_args()
    config = ExperimentConfig.canonical()
    data_dir: Path = arguments.data_dir
    output_dir: Path | None = arguments.output_dir
    validation_output = output_dir or REPO_ROOT / "output/financial-jepa/pending"
    deadline = Deadline.start(config.deadline_seconds)
    try:
        config.validate_paths(REPO_ROOT, data_dir, validation_output)
        receipt = acquire_years(AcquisitionRequest(config, data_dir, arguments.offline, deadline))
        parsed = parse_years(receipt.files)
        prepared = prepare_splits(parsed.rows, config)
        source = rights_metadata()
        yearly_responses: list[JsonValue] = [
            cache_metadata_record(metadata) for metadata in receipt.metadata
        ]
        dropped_dates: list[JsonValue] = [day.isoformat() for day in parsed.dropped_missing_dates]
        missing_rows: list[JsonValue] = []
        for day, missing_fields in parsed.missing_fields_by_date:
            fields: list[JsonValue] = list(missing_fields)
            missing_row: dict[str, JsonValue] = {"date": day.isoformat(), "fields": fields}
            missing_rows.append(missing_row)
        source["yearly_responses"] = yearly_responses
        source["dropped_missing_dates"] = dropped_dates
        source["missing_tenor_rows"] = missing_rows
        run_root = run_prepared_experiment(
            ExperimentRequest(REPO_ROOT, output_dir, config, prepared, source, deadline)
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
