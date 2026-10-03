from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from gleansight.api.models import OperationError
from nsqd.composition import NsqdContainer
from nsqd.composition import build_container as build_nsqd
from papers.app.composition_root import AppContainer
from papers.app.composition_root import build_container as build_papers
from papers.config.settings import (
    DEFAULT_OLLAMA_BASE_URL,
    Settings,
    load_settings,
    packaged_defaults_path,
)
from papers.infra.embedder_ollama.adapter import build_configured_ollama_embedder
from papers.infra.piccolo.database import PiccoloDatabase


class ApiConfiguration(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    repo_root: Path = Field(default_factory=Path.cwd)
    config_path: Path | None = None
    nsqd_db: Path | None = None
    nsqd_index: Path | None = None
    llm_base_url: str = DEFAULT_OLLAMA_BASE_URL
    allow_approvals: bool = False


class ApiRuntime:
    """Cache composition within one client; operation discovery creates no resources."""

    def __init__(self, configuration: ApiConfiguration) -> None:
        self.configuration = configuration
        self._settings: Settings | None = None
        self._database: PiccoloDatabase | None = None
        self._papers: AppContainer | None = None
        self._nsqd: NsqdContainer | None = None

    @property
    def repo_root(self) -> Path:
        return self.configuration.repo_root.resolve()

    @property
    def settings(self) -> Settings:
        if self._settings is None:
            override = self.configuration.config_path
            self._settings = load_settings(
                defaults_path=packaged_defaults_path(),
                override_path=None if override is None else self.resolve(override),
                base_dir=self.repo_root,
            )
        return self._settings

    def resolve(self, path: Path) -> Path:
        return path.resolve() if path.is_absolute() else (self.repo_root / path).resolve()

    @property
    def nsqd_db(self) -> Path:
        return self.resolve(self.configuration.nsqd_db or Path("data/nsqd/nsqd.sqlite"))

    @property
    def nsqd_index(self) -> Path:
        return self.resolve(self.configuration.nsqd_index or Path("data/nsqd/corpus.lancedb"))

    @property
    def paper_database(self) -> PiccoloDatabase:
        if self._database is None:
            path = self.settings.data.db_path
            path.parent.mkdir(parents=True, exist_ok=True)
            self._database = PiccoloDatabase(path)
            self._database.initialize_schema()
        self._database.bind_tables()
        return self._database

    @property
    def papers(self) -> AppContainer:
        if self._papers is None:
            self._papers = build_papers(self.settings, llm_base_url=self.configuration.llm_base_url)
        self._papers.db.bind_tables()
        return self._papers

    @property
    def nsqd(self) -> NsqdContainer:
        if self._nsqd is None:
            self._nsqd = build_nsqd(
                db_path=self.nsqd_db,
                index_path=self.nsqd_index,
                embedder=build_configured_ollama_embedder(self.settings.embeddings),
                enabled_operators=frozenset(self.settings.nsqd.enabled_operators),
                novelty_threshold_tau=self.settings.nsqd.novelty_threshold_tau,
            )
        return self._nsqd

    def require_approval(self) -> None:
        if not self.configuration.allow_approvals:
            raise OperationError(
                "approval_required", "This operation requires explicit human approval."
            )
