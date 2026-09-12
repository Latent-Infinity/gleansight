from __future__ import annotations

EXPECTED_F_PROTOCOL: dict[str, object] = {
    "status": "predeclared_not_executed",
    "execution_blocker": "insufficient_eligible_source_groups",
    "split_unit": "source_paper_group",
    "temporal_split_status": "unsupported_by_current_provenance",
    "fixed_seed": "operator-f/F-PROP-001/source-grouped-evaluation/v1",
    "split_assignment_algorithm": {
        "algorithm": "sha256_seeded_source_group_round_robin/v1",
        "preimage": "utf8(fixed_seed + ':' + source_paper_id)",
        "digest": "sha256",
        "ordering": "ascending_digest_then_source_paper_id",
        "assignment": "zero_based_rank_modulo_fold_count",
    },
    "split_size_policy": {
        "scheme": "five_fold_source_group_cross_validation",
        "fold_count": 5,
        "training_fold_count_per_evaluation": 4,
        "held_out_fold_count_per_evaluation": 1,
        "minimum_eligible_source_group_count": 5,
        "current_eligible_source_group_count": 3,
        "current_split_instantiable": False,
    },
    "missingness_exclusion": {
        "exclusion_unit": "source_paper_group",
        "required_fields": ["registered_coordinates", "validation_target"],
        "apply_before_split_assignment": True,
        "apply_identically_to_all_tracks": True,
        "imputation_authorized": False,
        "current_excluded_record_ids": ["N11-FIN-01", "N11-FIN-05"],
    },
    "tracks": [
        "current_registered_axes",
        "current_axes_plus_validation_target",
        "current_axes_plus_shuffled_validation_target",
    ],
    "identical_eligible_record_ids_across_tracks": [
        "N11-FIN-02",
        "N11-FIN-03",
        "N11-FIN-04",
    ],
    "leakage_controls": [
        "group_all_versions_of_a_source_paper_together",
        "adjudicate_labels_before_split_assignment",
        "fit_preprocessing_within_training_groups_only",
        "blind_candidate_labels_during_quality_review",
        "lock_eligible_set_before_track_comparison",
        "never_assign_from_downstream_outcomes_or_abstract_inference",
    ],
    "metrics": [
        "held_out_archive_coverage_gain",
        "cell_density",
        "quality_weighted_diversity",
        "stability_across_resamples",
        "redundancy_with_existing_axes",
        "residual_variation",
        "confound_sensitivity",
        "interpretability_review",
    ],
    "metric_definitions": {
        "held_out_archive_coverage_gain": (
            "track_occupied_held_out_cells_minus_current_occupied_held_out_cells"
        ),
        "cell_density": "eligible_held_out_records_divided_by_occupied_held_out_cells",
        "quality_weighted_diversity": (
            "sum_blinded_pre_split_quality_weight_per_occupied_held_out_cell"
        ),
        "stability_across_resamples": (
            "distribution_of_track_metric_differences_across_valid_held_out_folds"
        ),
        "redundancy_with_existing_axes": (
            "training_group_candidate_to_registered_axis_association_replayed_on_held_out_group"
        ),
        "residual_variation": (
            "held_out_candidate_variation_after_training_group_registered_axis_adjustment"
        ),
        "confound_sensitivity": (
            "track_metric_differences_by_predeclared_provenance_supported_strata"
        ),
        "interpretability_review": "blinded_protocol_adherence_review_before_track_outcomes",
    },
    "derived_metric_mappings": {},
    "resampling": {
        "unit": "source_paper_group",
        "method": "deterministic_held_out_fold_rotation/v1",
        "repetitions": "one_per_valid_fold",
        "shared_assignments_across_tracks": True,
        "current_status": "not_executable_with_three_eligible_source_groups",
    },
    "comparison_declarations": {
        "baseline_track": "current_registered_axes",
        "candidate_track": "current_axes_plus_validation_target",
        "negative_control_track": "current_axes_plus_shuffled_validation_target",
        "eligible_set_locked_before_assignment": True,
        "all_directional_results_retained": True,
        "outcomes_available": False,
    },
}

EXPECTED_G_CONTRACT_APPLICATION: dict[str, object] = {
    "source_class": "registered_experiment_artifact",
    "required_identity_fields": [
        "failure_record_id",
        "domain_policy_id",
        "experiment_id",
        "source_class",
        "immutable_source_artifact_digests",
    ],
    "required_original_condition_fields": [
        "code_revision",
        "data_snapshot_ids",
        "configuration_digest",
        "model_or_method_identity",
        "started_at_utc",
        "completed_at_utc",
    ],
    "original_conditions_scope": "complete_registered_experiment_conditions_only",
    "required_outcome_fields": [
        "failure_class",
        "bounded_observation",
        "measured_results",
        "evidence_artifact_digests",
    ],
    "outcome_scope": "measured_failure_evidence_not_absence_of_success",
    "required_review_fields": [
        "review_status",
        "human_reviewer",
        "human_approved_at_utc",
        "approved_record_digest",
    ],
    "digest_bound_artifacts_required": True,
    "independent_human_approval_required": True,
    "measurable_changed_condition_trigger_required": True,
    "explicit_restart_condition_required": True,
    "allowed_resurrection_scopes": ["review_only", "test_only"],
    "approved_record_immutable": True,
    "approved_record_mutation_rule": "corrections_create_new_record_with_supersession_link",
    "supersession_link_field": "supersedes_failure_record_id",
    "decision_separation": {
        "record_admission": "canonical_contract_validation_only",
        "operator_g_eligibility": "separate_changed_trigger_and_restart_gate",
        "packet_inclusion": "separate_independent_human_authorization",
        "restart_authorization": "separate_human_review_without_runtime_authority",
    },
}
