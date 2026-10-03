from pathlib import Path

from pydantic import TypeAdapter

from gleansight.api.client import GleansightAPI
from gleansight.api.models import Success
from gleansight.api.runtime import ApiConfiguration
from gleansight.api.workspaces import operations


def api(root: Path, *, approval: bool = False) -> GleansightAPI:
    return GleansightAPI(
        ApiConfiguration(repo_root=root, allow_approvals=approval), operations=operations()
    )


def backup(root: Path) -> Path:
    result = api(root).call("workspaces.backup", {})
    assert isinstance(result, Success), result
    fields = TypeAdapter(dict[str, str]).validate_python(result.data)
    return Path(fields["backup_path"])
