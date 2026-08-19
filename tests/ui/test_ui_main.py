from __future__ import annotations

from unittest.mock import MagicMock, patch

import papers.ui.__main__ as main_module
from papers.ui.app import UIServices


def test_build_ui_services_returns_ui_services(tmp_path):
    """Test that build_ui_services creates a UIServices instance with all dependencies."""
    # Create mock settings and container
    mock_settings = MagicMock()
    mock_settings.data.root = tmp_path
    mock_settings.data.db_path = tmp_path / "test.db"
    mock_settings.data.blobs_dir = tmp_path / "blobs"
    mock_settings.data.blobs_pdf_dir = tmp_path / "blobs" / "pdf"
    mock_settings.data.blobs_md_dir = tmp_path / "blobs" / "md"
    mock_settings.data.blobs_analysis_dir = tmp_path / "blobs" / "analysis"
    mock_settings.data.lancedb_dir = tmp_path / "lancedb"

    mock_container = MagicMock()
    mock_container.scholar_client = MagicMock()
    mock_container.paper_store = MagicMock()
    mock_container.paper_store.get = MagicMock(return_value=None)
    mock_container.job_queue = MagicMock()
    mock_container.job_queue.list_jobs = MagicMock(return_value=[])
    mock_container.analysis_store = MagicMock()
    mock_container.analysis_store.list_runs = MagicMock(return_value=[])
    mock_container.blob_store = MagicMock()
    mock_container.blob_store.get_markdown_path = MagicMock(return_value=None)

    with (
        patch.object(main_module, "load_settings", return_value=mock_settings),
        patch.object(main_module, "build_container", return_value=mock_container),
        patch.object(main_module, "PiccoloCandidateStore"),
        patch.object(main_module, "PiccoloExtractionStore"),
        patch.object(main_module, "PiccoloPaperExternalIdStore"),
        patch.object(main_module, "PiccoloPaperProjectStore"),
        patch.object(main_module, "PiccoloPaperFTS"),
    ):
        services = main_module.build_ui_services()

    assert isinstance(services, UIServices)
    assert services.list_paper is mock_container.paper_store.get
    assert services.list_runs is mock_container.analysis_store.list_runs
    # list_jobs is a lambda wrapper that delegates to job_queue.list_jobs
    services.list_jobs("pending", 50)
    mock_container.job_queue.list_jobs.assert_called_with(status="pending", limit=50)
    # cancel_job, delete_job, and bulk ops are direct references
    assert services.cancel_job is mock_container.job_queue.cancel
    assert services.delete_job is mock_container.job_queue.delete_job
    assert services.bulk_delete_jobs is mock_container.job_queue.bulk_delete_jobs
    assert services.bulk_cancel_jobs is mock_container.job_queue.bulk_cancel_jobs


def test_main_calls_run_app_with_services(tmp_path):
    """Test that main() builds services and calls run_app."""
    mock_services = MagicMock(spec=UIServices)

    with (
        patch.object(main_module, "build_ui_services", return_value=mock_services) as mock_build,
        patch.object(main_module, "run_app") as mock_run_app,
    ):
        main_module.main(
            config=str(tmp_path / "config.toml"),
            llm_base_url="http://test:8000",
            llm_api_key="test-key",
        )

    mock_build.assert_called_once()
    mock_run_app.assert_called_once_with(mock_services)
