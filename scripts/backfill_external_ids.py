#!/usr/bin/env python3
"""Backfill external IDs from candidates to paper_external_ids table.

This script migrates external IDs from candidates that were imported before
the PDF resolver feature was added. It populates the paper_external_ids table
so that download jobs can resolve PDF URLs.

Usage:
    uv run python scripts/backfill_external_ids.py [--dry-run]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from papers.infra.piccolo.database import PiccoloDatabase
from papers.infra.piccolo.stores import PiccoloCandidateStore, PiccoloPaperExternalIdStore


def backfill_external_ids(db_path: Path, dry_run: bool = False) -> int:
    """Backfill missing external IDs from imported candidates."""
    db = PiccoloDatabase(db_path)
    db.initialize_schema()

    candidate_store = PiccoloCandidateStore()
    external_id_store = PiccoloPaperExternalIdStore()
    candidates = candidate_store.list_candidates(imported=True)

    updated = 0
    for candidate in candidates:
        paper_id = candidate.get("imported_paper_id")
        external_ids_json = candidate.get("external_ids_json")
        if not paper_id or not external_ids_json:
            continue

        try:
            parsed_external_ids = json.loads(external_ids_json)
        except (json.JSONDecodeError, TypeError):
            print(f"  SKIP {paper_id[:8]}... invalid external_ids_json")
            continue
        if not isinstance(parsed_external_ids, dict) or not parsed_external_ids:
            print(f"  SKIP {paper_id[:8]}... empty external IDs")
            continue

        external_ids = {str(kind): str(value) for kind, value in parsed_external_ids.items()}
        existing = external_id_store.get_external_ids(paper_id)
        missing_or_changed = {
            kind: value for kind, value in external_ids.items() if existing.get(kind) != value
        }
        if not missing_or_changed:
            print(f"  SKIP {paper_id[:8]}... external IDs already current")
            continue

        title = str(candidate.get("title") or "Unknown")[:50]
        id_summary = ", ".join(
            f"{kind}={value[:10]}..." if len(value) > 10 else f"{kind}={value}"
            for kind, value in missing_or_changed.items()
        )
        if dry_run:
            print(f"  WOULD ADD {paper_id[:8]}... ({title}...)")
            print(f"            IDs: {id_summary}")
        else:
            external_id_store.create_external_ids(paper_id, missing_or_changed)
            print(f"  ADDED {paper_id[:8]}... ({title}...)")
            print(f"          IDs: {id_summary}")
        updated += 1

    return updated


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Backfill external IDs from candidates to paper_external_ids table"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Only print what would be done, don't make changes",
    )
    parser.add_argument(
        "--db-path",
        type=Path,
        default=Path("data/db/app.sqlite"),
        help="Path to SQLite database (default: data/db/app.sqlite)",
    )
    args = parser.parse_args()

    if not args.db_path.exists():
        print(f"ERROR: Database not found at {args.db_path}")
        sys.exit(1)

    print(f"{'DRY RUN - ' if args.dry_run else ''}Backfilling external IDs...")
    print(f"Database: {args.db_path}")
    print()

    updated = backfill_external_ids(args.db_path, dry_run=args.dry_run)

    print()
    if args.dry_run:
        print(f"Would update {updated} papers")
        print("Run without --dry-run to apply changes")
    else:
        print(f"Updated {updated} papers")


if __name__ == "__main__":
    main()
