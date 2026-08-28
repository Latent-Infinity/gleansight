from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from nsqd.app.handlers import NsqdHandlerContext
from nsqd.domain.diverge import DEFAULT_ENABLED_OPERATORS, require_enabled_operators
from nsqd.domain.policy import POLICIES
from nsqd.infra.lancedb.index import LanceDBCorpusIndex
from nsqd.infra.piccolo.stores import (
    PiccoloAcquisitionCycleStore,
    PiccoloApprovedDigestStore,
    PiccoloCorpusRecordStore,
    PiccoloCorpusSnapshotStore,
    PiccoloFrontierCardStore,
    PiccoloHarvestStore,
    PiccoloMorphospaceStore,
    PiccoloNsqdCandidateStore,
    PiccoloNsqdJobQueue,
    PiccoloPolicyVerdictStore,
)
from nsqd.null_adapters import (
    FixedClock,
    NullPaperAcquisitionBridge,
    SystemClock,
)
from nsqd.ports import (
    Clock,
    HybridPaperSearch,
    LivePaperSearch,
    PaperAcquisitionBridge,
    ParaphraseEmbedder,
)
from papers.config.settings import EmbeddingSettings
from papers.infra.embedder_ollama.adapter import build_configured_ollama_embedder
from papers.infra.piccolo.database import PiccoloDatabase


@dataclass(frozen=True)
class NsqdContainer:
    clock: Clock
    database: PiccoloDatabase
    queue: PiccoloNsqdJobQueue
    ctx: NsqdHandlerContext


def build_local_ollama_embedder(settings: EmbeddingSettings) -> ParaphraseEmbedder:
    return build_configured_ollama_embedder(settings)


def build_container(
    *,
    db_path: Path,
    index_path: Path,
    clock: Clock | None = None,
    approved_projection_digests: frozenset[str] | None = None,
    scholar_client: LivePaperSearch | None = None,
    paper_hybrid_search: HybridPaperSearch | None = None,
    paper_bridge: PaperAcquisitionBridge | None = None,
    embedder: ParaphraseEmbedder | None = None,
    enabled_operators: frozenset[str] = DEFAULT_ENABLED_OPERATORS,
) -> NsqdContainer:
    allowlist = require_enabled_operators(enabled_operators)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    index_path.parent.mkdir(parents=True, exist_ok=True)
    database = PiccoloDatabase(db_path, bind_on_init=False)
    database.initialize_schema()
    resolved_clock = clock if clock is not None else SystemClock()
    records = PiccoloCorpusRecordStore(database)
    snapshots = PiccoloCorpusSnapshotStore(database)
    digest_store = PiccoloApprovedDigestStore(database)
    if approved_projection_digests:
        now = resolved_clock.now()
        for digest in approved_projection_digests:
            digest_store.add(digest, approved_at=now)
    index = LanceDBCorpusIndex(
        index_path,
        embedding_model=None
        if embedder is None
        else f"{embedder.model_id()}:{embedder.model_version()}",
        embedding_dimension=None if embedder is None else embedder.dimension(),
    )
    ctx = NsqdHandlerContext(
        clock=resolved_clock,
        candidates=PiccoloNsqdCandidateStore(database),
        cards=PiccoloFrontierCardStore(database),
        snapshots=snapshots,
        records=records,
        harvest=PiccoloHarvestStore(database),
        index=index,
        morph=PiccoloMorphospaceStore(database),
        approved_projection_digests=digest_store.list_digests(),
        scholar_client=scholar_client,
        paper_vector_index=paper_hybrid_search,
        cycles=PiccoloAcquisitionCycleStore(database),
        verdicts=PiccoloPolicyVerdictStore(database),
        bridge=paper_bridge if paper_bridge is not None else NullPaperAcquisitionBridge(),
        policies=POLICIES,
        embedder=embedder,
        enabled_operators=allowlist,
    )
    return NsqdContainer(
        clock=resolved_clock,
        database=database,
        queue=PiccoloNsqdJobQueue(database, clock=resolved_clock),
        ctx=ctx,
    )


def fixed_clock(as_of: datetime) -> FixedClock:
    return FixedClock(as_of)
