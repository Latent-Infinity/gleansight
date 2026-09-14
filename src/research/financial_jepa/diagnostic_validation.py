from __future__ import annotations

from collections.abc import Mapping
from datetime import date

import numpy as np
from numpy.typing import NDArray

from research.financial_jepa.contracts import ProtocolError

type NumericArray = NDArray[np.number] | NDArray[np.str_]


def _dates(
    arrays: Mapping[str, NumericArray], name: str, minimum_year: int, maximum_year: int
) -> None:
    values = arrays[name]
    if values.dtype != np.dtype("U10"):
        raise ProtocolError("diagnostic dates must use fixed U10 Unicode arrays")
    try:
        parsed = tuple(date.fromisoformat(str(value)) for value in values.flat)
    except ValueError as exc:
        raise ProtocolError("diagnostic date array contains invalid ISO dates") from exc
    if any(day.year < minimum_year or day.year > maximum_year for day in parsed):
        raise ProtocolError("diagnostic date array is outside its development split")


def validate_date_arrays(arrays: Mapping[str, NumericArray]) -> None:
    _dates(arrays, "train_row_dates", 2001, 2017)
    _dates(arrays, "validation_row_dates", 2018, 2021)
    _dates(arrays, "origin_dates", 2018, 2021)
    _dates(arrays, "target_dates", 2018, 2021)
