from __future__ import annotations

from typing import Any


def choose_elite(
    *,
    cell_elite: dict[str, Any] | None,
    candidate: dict[str, Any],
) -> dict[str, Any] | None:
    if int(candidate.get("viability") or 0) <= 0:
        return cell_elite
    if cell_elite is None:
        return candidate
    cand_v = int(candidate["viability"])
    elite_v = int(cell_elite["viability"])
    if cand_v > elite_v:
        return candidate
    if cand_v < elite_v:
        return cell_elite
    cand_hash = str(candidate["candidate_artifact_hash"])
    elite_hash = str(cell_elite["candidate_artifact_hash"])
    return candidate if cand_hash < elite_hash else cell_elite
