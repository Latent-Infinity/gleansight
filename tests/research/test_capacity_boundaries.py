from __future__ import annotations

from dataclasses import replace
from datetime import date
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pytest

from research.financial_jepa import capacity_storage
from research.financial_jepa.capacity_fitting import project_training, run_trial
from research.financial_jepa.capacity_reporting import summary
from research.financial_jepa.capacity_storage import bounded_read, load_bundle, write_bundle
from research.financial_jepa.contracts import ProtocolError
from research.financial_jepa.walkforward_protocol import preregister_folds
from tests.research.test_capacity_diagnostics import pair


def test_projection_rejects_invalid_and_nonfinite_training_inputs() -> None:
    values = np.ones((5, 4))
    for training, selection, size in (
        (values, np.ones((5, 3)), 2),
        (values, values, 0),
        (values, values, 5),
        (values * np.nan, values, 2),
    ):
        with pytest.raises(ProtocolError):
            project_training(training, selection, size)
    projected, _, state = project_training(values, values, 2)
    assert np.array_equal(projected, np.zeros((5, 2)))
    assert float(state["projection_variance_fraction"]) == 0


def test_target_shape_is_rejected_and_fit_failures_remain_in_paired_report() -> None:
    original = pair()
    with pytest.raises(ProtocolError, match="horizons"):
        run_trial(replace(original, train_targets=np.ones((50, 4, 8))))
    with pytest.raises(ProtocolError, match="selection targets"):
        run_trial(replace(original, selection_targets=np.ones((12, 4, 8))))
    failed, arrays = run_trial(replace(original, train=np.ones((49, 8))))
    assert failed.error and not arrays
    aggregate = summary((failed,))
    assert aggregate["failures"]
    paired = aggregate["paired"]
    assert isinstance(paired, list)
    first = paired[0]
    assert isinstance(first, dict) and first["excluded_seed_count"] == 1


def test_artifact_bounds_and_failed_publication_leave_no_bundle(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    content = tmp_path / "source"
    content.write_bytes(b"12345")
    link = tmp_path / "link"
    link.symlink_to(content)
    with pytest.raises(ProtocolError, match="non-symlink"):
        bounded_read(link)
    with pytest.raises(ProtocolError, match="regular"):
        bounded_read(tmp_path / "absent")
    monkeypatch.setattr(capacity_storage, "MAX_BYTES", 4)
    with pytest.raises(ProtocolError, match="limit"):
        bounded_read(content)
    with pytest.raises(ProtocolError, match="bound"):
        write_bundle(tmp_path / "large", {}, {"values": np.ones(1)})
    monkeypatch.setattr(capacity_storage, "MAX_BYTES", 128 * 1024 * 1024)
    with pytest.raises(ProtocolError, match="finite"):
        write_bundle(tmp_path / "invalid", {}, {"values": np.asarray([np.nan])})
    target = tmp_path / "failed"
    with patch.object(Path, "write_bytes", side_effect=OSError("disk fixture full")):
        with pytest.raises(OSError):
            write_bundle(target, {}, {})
    assert not target.exists()
    assert content.read_bytes() == b"12345"


def test_manifest_schema_and_walkforward_membership_refusals(tmp_path: Path) -> None:
    target = tmp_path / "manifest"
    write_bundle(target, {}, {})
    (target / "run-metadata.json").write_text('{"schema_version":2,"artifact_sha256":{}}')
    with pytest.raises(ProtocolError, match="schema"):
        load_bundle(target)
    with pytest.raises(ProtocolError, match="unique"):
        preregister_folds((date(2017, 1, 1), date(2017, 1, 1)), "a" * 64)
    with pytest.raises(ProtocolError, match="SHA"):
        preregister_folds((date(2017, 1, 1),), "bad")
    with pytest.raises(ProtocolError, match="empty"):
        preregister_folds((date(2017, 1, 1),), "a" * 64)
