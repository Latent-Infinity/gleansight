from __future__ import annotations

from typing import Final, Protocol

_COUNT_WORDS: Final = (
    "zero",
    "one",
    "two",
    "three",
    "four",
    "five",
    "six",
    "seven",
    "eight",
    "nine",
    "ten",
)


class FindingTrack(Protocol):
    @property
    def track_id(self) -> str: ...

    @property
    def occupied_cell_count(self) -> int: ...

    @property
    def observed_cell_coverage(self) -> float: ...

    @property
    def records_per_occupied_cell(self) -> float: ...


def derive_pilot_findings(
    total_record_count: int,
    eligible_record_ids: tuple[str, ...],
    tracks: tuple[FindingTrack, FindingTrack, FindingTrack],
) -> tuple[str, str, str]:
    eligible_count = len(eligible_record_ids)
    identities = _series(eligible_record_ids)
    occupancy = tuple(track.occupied_cell_count for track in tracks)
    coverage = (
        tracks[0].observed_cell_coverage,
        tracks[1].observed_cell_coverage,
        tracks[2].observed_cell_coverage,
    )
    density = (
        tracks[0].records_per_occupied_cell,
        tracks[1].records_per_occupied_cell,
        tracks[2].records_per_occupied_cell,
    )
    if len(set(occupancy)) == len(set(coverage)) == len(set(density)) == 1:
        track_finding = (
            f"All three tracks occupy {_count(occupancy[0])} cells among "
            f"{_count(eligible_count)} coordinate-eligible records; descriptive occupied-cell "
            "coverage and density are unchanged."
        )
    else:
        track_finding = (
            f"The {tracks[0].track_id} track occupies {_count(occupancy[0])} cells, the "
            f"{tracks[1].track_id} track occupies {_count(occupancy[1])} cells, and the "
            f"{tracks[2].track_id} track occupies {_count(occupancy[2])} cells among "
            f"{_count(eligible_count)} coordinate-eligible records; descriptive occupied-cell "
            f"coverage is {_series_numbers(coverage)}, with density {_series_numbers(density)} "
            "records per occupied cell."
        )
    return (
        f"All {_count(total_record_count)} records have observed validation_target values; only "
        f"{identities} have registered-axis coordinates.",
        track_finding,
        "Held-out archive coverage gain is not estimable from "
        f"{_count(eligible_count)} coordinate-eligible records; no stability or quality evidence "
        "is claimed.",
    )


def _count(value: int) -> str:
    return _COUNT_WORDS[value] if value < len(_COUNT_WORDS) else str(value)


def _series(values: tuple[str, ...]) -> str:
    return values[0] if len(values) == 1 else f"{', '.join(values[:-1])}, and {values[-1]}"


def _series_numbers(values: tuple[float, float, float]) -> str:
    return f"{values[0]}, {values[1]}, and {values[2]}"
