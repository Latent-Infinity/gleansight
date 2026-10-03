from __future__ import annotations

from dataclasses import fields
from unittest.mock import Mock

import flet as ft

from papers.ui.app import UIServices


def built_column(control: ft.Control) -> ft.Column:
    assert isinstance(control, ft.Column)
    return control


def built_row(control: ft.Control) -> ft.Row:
    assert isinstance(control, ft.Row)
    return control


def built_text(control: ft.Control) -> ft.Text:
    assert isinstance(control, ft.Text)
    return control


def built_field(control: ft.Control) -> ft.TextField:
    assert isinstance(control, ft.TextField)
    return control


def row_fields_and_button(row: ft.Row) -> tuple[list[ft.TextField], ft.Button]:
    assert row.controls
    fields = row.controls[:-1]
    button = row.controls[-1]
    assert all(isinstance(field, ft.TextField) for field in fields)
    assert isinstance(button, ft.Button)
    return [field for field in fields if isinstance(field, ft.TextField)], button


def complete_ui_services[T](partial: T | None = None) -> UIServices:
    services = UIServices(
        discover=Mock(),
        import_candidate=Mock(),
        reject_candidate=Mock(),
        search=Mock(),
        filter_extractions=Mock(),
        aggregate_extractions=Mock(),
        get_candidate=lambda _candidate_id: None,
        list_paper=lambda _paper_id: None,
        list_runs=lambda _paper_id: [],
        list_jobs=lambda _paper_id, _limit: [],
        run_next_job=lambda: False,
        enqueue_job=lambda _job_type, _paper_id, _run_id, _payload: "job-id",
        cancel_job=lambda _job_id: None,
        delete_job=lambda _job_id: None,
        bulk_delete_jobs=lambda _job_ids: 0,
        bulk_cancel_jobs=lambda _job_ids: 0,
        get_paper_markdown=lambda _paper_id: None,
        list_extractions=lambda _paper_id, _prompt_version: [],
        delete_paper=lambda _paper_id: None,
        reset_pipeline_stage=lambda _paper_id, _stage: None,
        synthesize_from_corpus=Mock(),
        ui_settings={},
    )
    if partial is not None:
        for field in fields(UIServices):
            if hasattr(partial, field.name):
                setattr(services, field.name, getattr(partial, field.name))
    return services
