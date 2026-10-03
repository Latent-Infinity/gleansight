from pathlib import Path

from papers.app.use_cases.saved_discovery import SavedDiscoveryService
from papers.domain.screening import SaveSearch
from papers.infra.piccolo.database import PiccoloDatabase
from papers.infra.piccolo.stores import PiccoloProjectStore


def test_saved_query_survives_service_restart(tmp_path: Path) -> None:
    database = PiccoloDatabase(tmp_path / "papers.sqlite")
    database.initialize_schema()
    PiccoloProjectStore().create_project("project-1", "Persistent literature review")
    service = SavedDiscoveryService(database)
    saved = service.save(
        SaveSearch(project_id="project-1", name="Methods", query="causal learning")
    )
    restarted = SavedDiscoveryService(database)
    assert restarted.get(saved.search_id).search == saved
    assert restarted.list("project-1") == (saved,)
