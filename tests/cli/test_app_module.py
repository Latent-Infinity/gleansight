from __future__ import annotations

from dataclasses import dataclass

import importlib


@dataclass
class FakeBase:
    scholar_client: object
    paper_store: object
    job_queue: object
    prompt_store: object
    profile_store: object
    analysis_store: object
    vector_index: object
    embedder: object
    blob_store: object
    job_runner: object


def test_get_container_builds_cli_container(monkeypatch) -> None:
    cli_app = importlib.import_module("papers.cli.app")
    fake_base = FakeBase(
        scholar_client=object(),
        paper_store=object(),
        job_queue=object(),
        prompt_store=object(),
        profile_store=object(),
        analysis_store=object(),
        vector_index=object(),
        embedder=object(),
        blob_store=object(),
        job_runner=object(),
    )

    def fake_build_container(settings, *, llm_base_url: str, llm_api_key=None):
        assert llm_base_url == "http://example.com"
        return fake_base

    monkeypatch.setattr(cli_app, "build_container", fake_build_container)
    monkeypatch.setattr(cli_app, "load_settings", lambda **kwargs: object())
    cli_app._container = None
    cli_app._cli_options["llm_base_url"] = "http://example.com"
    cli_app._cli_options["llm_api_key"] = None
    cli_app._cli_options["config"] = None

    container = cli_app.get_container()

    assert container.job_runner is fake_base.job_runner
    assert container.job_queue is fake_base.job_queue


def test_get_container_caches_instance(monkeypatch) -> None:
    cli_app = importlib.import_module("papers.cli.app")
    fake_base = FakeBase(
        scholar_client=object(),
        paper_store=object(),
        job_queue=object(),
        prompt_store=object(),
        profile_store=object(),
        analysis_store=object(),
        vector_index=object(),
        embedder=object(),
        blob_store=object(),
        job_runner=object(),
    )

    build_calls = {"count": 0}

    def fake_build_container(settings, *, llm_base_url: str, llm_api_key=None):
        build_calls["count"] += 1
        return fake_base

    monkeypatch.setattr(cli_app, "build_container", fake_build_container)
    monkeypatch.setattr(cli_app, "load_settings", lambda **kwargs: object())
    cli_app._container = None
    cli_app._cli_options["llm_base_url"] = "http://localhost:8000"
    cli_app._cli_options["llm_api_key"] = None
    cli_app._cli_options["config"] = None

    container1 = cli_app.get_container()
    container2 = cli_app.get_container()

    assert container1 is container2
    assert build_calls["count"] == 1
