from __future__ import annotations

import tomllib
from pathlib import Path

APPROVED = Path(__file__).resolve().parents[1] / "fixtures" / "approved"
REQUIRED_KEYS = (
    "id",
    "paper_id",
    "title",
    "abstract",
    "markdown_path",
    "source_paper_id",
    "source_kind",
    "redaction",
    "owner",
    "refresh_when",
)
ROLE_TABLES = ("DATA-01a", "DATA-01b", "DATA-01c")


def _manifest() -> dict[str, object]:
    path = APPROVED / "manifest.toml"
    assert path.is_file(), f"missing {path}"
    return tomllib.loads(path.read_text(encoding="utf-8"))


def test_manifest_has_three_paper_fixtures_with_required_keys() -> None:
    data = _manifest()
    fixtures = data.get("fixture")
    assert isinstance(fixtures, dict)
    for role in ROLE_TABLES:
        row = fixtures.get(role)
        assert isinstance(row, dict), f"missing fixture.{role}"
        for key in REQUIRED_KEYS:
            assert key in row, f"fixture.{role} missing {key}"
            value = row[key]
            assert isinstance(value, str) and value.strip(), f"fixture.{role}.{key} empty"
        assert row["id"] == role
        assert row["source_kind"] == "convert-path-paper"
        assert row["owner"] == "product"
        redaction = row["redaction"].casefold()
        assert "rewritten" not in redaction
        assert "invented" not in redaction
        md = APPROVED / row["markdown_path"]
        assert md.is_file(), f"missing markdown {md}"
        assert md.read_text(encoding="utf-8").strip()


def test_paper_ids_do_not_sort_as_role_order() -> None:
    data = _manifest()
    fixtures = data["fixture"]
    assert isinstance(fixtures, dict)
    role_order: list[str] = []
    for role in ROLE_TABLES:
        row = fixtures[role]
        assert isinstance(row, dict)
        role_order.append(str(row["paper_id"]))
    assert sorted(role_order) != role_order
