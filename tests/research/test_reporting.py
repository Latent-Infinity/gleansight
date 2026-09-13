from __future__ import annotations

import json

from research.financial_jepa.contracts import ExperimentConfig
from research.financial_jepa.reporting import protocol_record


def test_protocol_record_serializes_complete_frozen_scientific_policy() -> None:
    protocol = json.loads(json.dumps(protocol_record(ExperimentConfig.canonical())))

    assert protocol["protocol_version"] == "yield-jepa/1"
    assert protocol["dataset"]["segmentation"] == {
        "window_scope": "within_partition_and_segment",
        "missing_tenor_row": "drop_and_hard_boundary",
        "maximum_calendar_gap_days": 4,
        "methodology_change_boundary": "2021-12-06",
        "interpolation": "none",
        "weekend_filling": False,
    }
    assert protocol["dataset"]["scaling"]["fit_rows"] == "retained_training_rows_only"
    assert protocol["architecture"]["target_encoder"]["ema_decay"] == 0.99
    assert protocol["loss"] == {
        "prediction": "mean((predicted_future_latent-target_future_latent)^2)",
        "regularizer": {
            "name": "independent_VICReg_style_not_SIGReg",
            "variance": "mean(relu(1-sqrt(population_variance+1e-4))^2)",
            "covariance": "sum(off_diagonal(sample_covariance)^2)/(16*15)",
            "weight": 0.1,
        },
    }
    assert protocol["training"]["batch_order"] == "seeded_randperm_per_epoch"
    assert protocol["training"]["selection"] == {
        "metric": "aligned_validation_latent_mse",
        "tie_break": "earliest_epoch",
    }
    assert protocol["evaluation"]["ridge"]["alpha_policy"] == ("one_shared_alpha_per_model_seed")
    assert protocol["evaluation"]["ridge"]["selection_metric"] == (
        "aggregate_validation_rmse_all_horizons_and_tenors"
    )
    assert protocol["evaluation"]["ridge"]["objective"] == "SSE/n + alpha*L2"
    assert protocol["evaluation"]["ridge"]["refit_train_plus_validation"] is False
    assert set(protocol["evaluation"]["raw_baselines"]) == {
        "last_level_persistence",
        "training_row_mean",
        "direct_ridge",
    }
    assert protocol["evaluation"]["metrics"]["raw_rmse_unit"] == "basis_points"
    assert protocol["evaluation"]["collapse"] == {
        "population": "unique_retained_rows_per_split",
        "standard_deviation": "sample",
        "covariance": "sample",
        "trace_zero_threshold": 1e-12,
        "collapsed_when": "mean_std<0.1 OR effective_rank<2",
    }
    assert protocol["execution"] == {
        "device": "cpu",
        "intraop_threads": 4,
        "interop_threads": 1,
        "deterministic_algorithms": True,
        "data_loader_workers": 0,
        "whole_command_budget_seconds": 900.0,
    }
    assert protocol["source_and_rights"]["license_expression"] == "NOASSERTION"
    assert len(protocol["deviations_from_exact_replication"]) == 6
