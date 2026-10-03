from __future__ import annotations

import argparse
from pathlib import Path

from research.financial_jepa.capacity_workflow import run_capacity


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(
        description="Bounded offline capacity diagnostic and separate walk-forward "
        "preregistration; development data only."
    )
    parser.add_argument("--source-bundle", required=True, type=Path)
    parser.add_argument(
        "--data-dir", type=Path, default=root / "data/research/financial-jepa/treasury"
    )
    arguments = parser.parse_args()
    for path in run_capacity(root, arguments.source_bundle, arguments.data_dir):
        print(path)


if __name__ == "__main__":
    main()
