from pathlib import Path

import pytest

from gleansight.api.client import GleansightAPI
from gleansight.api.papers import operations
from gleansight.api.runtime import ApiConfiguration, ApiRuntime
from papers.infra.piccolo.stores import PiccoloPaperStore, PiccoloProfileStore


@pytest.fixture
def runtime(tmp_path: Path) -> ApiRuntime:
    return ApiRuntime(ApiConfiguration(repo_root=tmp_path))


@pytest.fixture
def api(tmp_path: Path) -> GleansightAPI:
    return GleansightAPI(ApiConfiguration(repo_root=tmp_path), operations=operations())


@pytest.fixture
def populated(runtime: ApiRuntime) -> ApiRuntime:
    runtime.paper_database.bind_tables()
    PiccoloPaperStore().create_paper({"paper_id": "paper-1", "title": "Adaptive learning"})
    PiccoloProfileStore().create_profile("local", "Local", "http://localhost:1234")
    return runtime


@pytest.fixture
def providers(monkeypatch: pytest.MonkeyPatch) -> None:
    from gleansight.api.papers import candidates
    from papers.app import composition_root
    from tests.api.papers.fakes import LLM, Converter, Embedder, Index, Scholar

    monkeypatch.setattr(composition_root, "build_docling_converter", Converter)
    monkeypatch.setattr(
        composition_root, "build_configured_ollama_embedder", lambda settings: Embedder()
    )
    monkeypatch.setattr(composition_root, "LanceDBVectorIndex", Index)
    monkeypatch.setattr(composition_root, "build_openai_compat_client", lambda **kwargs: LLM())
    monkeypatch.setattr(composition_root, "build_s2_client", lambda **kwargs: Scholar())
    monkeypatch.setattr(candidates, "build_s2_client", lambda **kwargs: Scholar())
