from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from nsqd.app.handlers import NsqdHandlerContext
from nsqd.infra.lancedb.index import LanceDBCorpusIndex
from nsqd.infra.piccolo.stores import (
    PiccoloCorpusRecordStore,
    PiccoloCorpusSnapshotStore,
    PiccoloFrontierCardStore,
    PiccoloHarvestStore,
    PiccoloMorphospaceStore,
    PiccoloNsqdCandidateStore,
    PiccoloNsqdJobQueue,
)
from nsqd.null_adapters import FixedClock, SystemClock
from nsqd.ports import Clock, HybridPaperSearch, LivePaperSearch
from papers.infra.piccolo.database import PiccoloDatabase


@dataclass(frozen=True)
class NsqdContainer:
    clock: Clock
    database: PiccoloDatabase
    queue: PiccoloNsqdJobQueue
    ctx: NsqdHandlerContext


def build_container(
    *,
    db_path: Path,
    index_path: Path,
    clock: Clock | None = None,
    approved_projection_digests: frozenset[str] | None = None,
    scholar_client: LivePaperSearch | None = None,
    paper_hybrid_search: HybridPaperSearch | None = None,
) -> NsqdContainer:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    index_path.parent.mkdir(parents=True, exist_ok=True)
    database = PiccoloDatabase(db_path)
    database.initialize_schema()
    resolved_clock = clock if clock is not None else SystemClock()
    records = PiccoloCorpusRecordStore(database)
    snapshots = PiccoloCorpusSnapshotStore(database)
    ctx = NsqdHandlerContext(
        clock=resolved_clock,
        candidates=PiccoloNsqdCandidateStore(database),
        cards=PiccoloFrontierCardStore(database),
        snapshots=snapshots,
        records=records,
        harvest=PiccoloHarvestStore(database),
        index=LanceDBCorpusIndex(index_path),
        morph=PiccoloMorphospaceStore(database),
        approved_projection_digests=(
            approved_projection_digests if approved_projection_digests is not None else frozenset()
        ),
        scholar_client=scholar_client,
        paper_vector_index=paper_hybrid_search,
    )
    return NsqdContainer(
        clock=resolved_clock,
        database=database,
        queue=PiccoloNsqdJobQueue(database, clock=resolved_clock),
        ctx=ctx,
    )


def fixed_clock(as_of: datetime) -> FixedClock:
    return FixedClock(as_of)
