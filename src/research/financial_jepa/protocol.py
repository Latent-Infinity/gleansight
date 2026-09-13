from __future__ import annotations

from typing import Final

from pydantic import TypeAdapter

from research.financial_jepa.contracts import TENOR_FIELDS, ExperimentConfig, JsonValue

PROTOCOL_VERSION: Final = "yield-jepa/1"
_PROTOCOL_RECORD_ADAPTER: Final = TypeAdapter(dict[str, JsonValue])


def protocol_record(config: ExperimentConfig) -> dict[str, JsonValue]:
    dataset = {
        "source": "U.S. Treasury Daily Treasury Par Yield Curve Rates yearly XML",
        "years": list(config.years),
        "fields": list(TENOR_FIELDS),
        "yield_unit": "percentage_points",
        "splits": {"train": "2001-2017", "validation": "2018-2021", "test": "2022-2025"},
        "segmentation": {
            "window_scope": "within_partition_and_segment",
            "missing_tenor_row": "drop_and_hard_boundary",
            "maximum_calendar_gap_days": 4,
            "methodology_change_boundary": "2021-12-06",
            "interpolation": "none",
            "weekend_filling": False,
        },
        "scaling": {
            "statistic": "population_mean_and_standard_deviation",
            "fit_rows": "retained_training_rows_only",
            "applied_to": "all_partitions",
            "zero_training_standard_deviation": "fatal",
        },
    }
    architecture = {
        "encoder": {
            "layers": ["Linear(8,32)", "GELU", "Linear(32,16)", "LayerNorm(16)"],
        },
        "predictor": {
            "position_embedding": [config.context_length, 16],
            "transformer_layers": 2,
            "attention_heads": 4,
            "feedforward_dimension": 64,
            "activation": "GELU",
            "dropout": 0.0,
            "mask": "causal",
            "readout_token": "last_context_token",
            "future_head": [16, config.future_length * 16],
            "output_shape": ["batch", config.future_length, 16],
        },
        "target_encoder": {
            "initialization": "online_encoder_copy",
            "gradient": False,
            "ema_decay": 0.99,
            "update": "after_each_optimizer_step",
        },
    }
    loss = {
        "prediction": "mean((predicted_future_latent-target_future_latent)^2)",
        "regularizer": {
            "name": "independent_VICReg_style_not_SIGReg",
            "variance": "mean(relu(1-sqrt(population_variance+1e-4))^2)",
            "covariance": "sum(off_diagonal(sample_covariance)^2)/(16*15)",
            "weight": 0.1,
        },
    }
    training = {
        "variants": [variant.value for variant in config.variants],
        "shuffled_target": "seeded_nonzero_cyclic_batch_offset_sequence_intact_training_only",
        "seeds": list(config.seeds),
        "epochs": config.epochs,
        "batch_size": config.batch_size,
        "batch_order": "seeded_randperm_per_epoch",
        "drop_last": True,
        "optimizer": {
            "name": "AdamW",
            "learning_rate": 1e-3,
            "betas": [0.9, 0.999],
            "epsilon": 1e-8,
            "weight_decay": 1e-4,
        },
        "scheduler": "none",
        "early_stopping": False,
        "selection": {
            "metric": "aligned_validation_latent_mse",
            "tie_break": "earliest_epoch",
        },
    }
    evaluation = {
        "freeze_before_test": ["checkpoints", "readouts", "alphas"],
        "ridge": {
            "readout_count": config.future_length,
            "mapping": "predicted_latent_to_raw_future_yields_one_readout_per_horizon",
            "input_standardization": "training_only_population_mean_and_std",
            "constant_learned_column": "normalized_zero_with_zero_coefficient",
            "intercept": "unpenalized",
            "alpha_grid": list(config.ridge_alphas),
            "alpha_policy": "one_shared_alpha_per_model_seed",
            "selection_metric": "aggregate_validation_rmse_all_horizons_and_tenors",
            "tie_break": "smallest_alpha",
            "objective": "SSE/n + alpha*L2",
            "refit_train_plus_validation": False,
        },
        "raw_baselines": {
            "last_level_persistence": "repeat_last_raw_context_yield_for_each_horizon",
            "training_row_mean": "repeat_retained_training_row_raw_mean",
            "direct_ridge": "flattened_standardized_30x8_context_to_5x8_raw_yields",
        },
        "metrics": {
            "raw_rmse_unit": "basis_points",
            "conversion": "100*sqrt(MSE_in_percentage_points)",
            "axes": ["overall", "per_horizon", "per_tenor", "horizon_by_tenor"],
            "aggregate": "per_variant_seed_mean_and_population_std",
            "date_identity": (
                "SHA256_of_ordered_origin_and_target_dates_common_to_all_models_and_baselines"
            ),
        },
        "latent_comparison": "each_model_against_its_own_EMA_last_context_persistence",
        "collapse": {
            "population": "unique_retained_rows_per_split",
            "standard_deviation": "sample",
            "covariance": "sample",
            "trace_zero_threshold": 1e-12,
            "collapsed_when": "mean_std<0.1 OR effective_rank<2",
        },
        "verdict": {
            "positive_label": "preliminary_descriptive_signal",
            "fallback_label": "negative_or_inconclusive",
            "all_required": [
                "regularized_mean_beats_all_raw_baselines",
                "every_regularized_seed_beats_paired_shuffle",
                "every_regularized_latent_beats_persistence",
                "no_regularized_collapse",
            ],
        },
    }
    record = {
        "name": "YieldJEPA",
        "protocol_version": PROTOCOL_VERSION,
        "status": config.label,
        "scientific_boundary": "independent mechanism study; not an exact Fin-JEPA replication",
        "dataset": dataset,
        "window": {"context": config.context_length, "future": config.future_length, "stride": 1},
        "architecture": architecture,
        "loss": loss,
        "training": training,
        "evaluation": evaluation,
        "execution": {
            "device": "cpu",
            "intraop_threads": 4,
            "interop_threads": 1,
            "deterministic_algorithms": True,
            "data_loader_workers": 0,
            "whole_command_budget_seconds": config.deadline_seconds,
        },
        "source_and_rights": {
            "publisher": "U.S. Department of the Treasury",
            "license_expression": "NOASSERTION",
            "underlying_dealer_quotes_downloaded": False,
        },
        "deviations_from_exact_replication": [
            "Treasury yield curves replace private equity features",
            "latent dimension 16 replaces reported 64",
            "future length five replaces reported ten",
            "two predictor layers replace reported four-layer or six-layer descriptions",
            "ten epochs replace reported 50",
            "independent VICReg-style regularizer replaces SIGReg",
        ],
    }
    return _PROTOCOL_RECORD_ADAPTER.validate_python(record)
