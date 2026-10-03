from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def test_core_registry_discovery_is_lazy_and_missing_research_group_is_actionable(
    tmp_path: Path,
) -> None:
    script = r"""
import importlib.abc
import importlib.machinery
import json
import sys
from collections.abc import Sequence
from types import ModuleType
from pathlib import Path

class WithoutResearch(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname: str, path: Sequence[str] | None = None,
                  target: ModuleType | None = None) -> importlib.machinery.ModuleSpec | None:
        if fullname.partition('.')[0] in {'numpy', 'torch'}:
            raise ModuleNotFoundError('Optional research dependency absent', name=fullname)
        return None

sys.meta_path.insert(0, WithoutResearch())
from gleansight.api import GleansightAPI
from gleansight.api.runtime import ApiConfiguration
api = GleansightAPI(ApiConfiguration(repo_root=Path(sys.argv[1])))
assert len(api.operations()) > 100
assert api.describe('research.runs.compare').name == 'research.runs.compare'
result = api.call('research.runs.verify', {'bundle_path':'output/missing'}).model_dump(mode='json')
assert result['status'] == 'error', result
assert result['error']['code'] == 'missing_dependency', result
assert 'uv sync --group research' in result['error']['message'], result
print(json.dumps(result))
"""
    result = subprocess.run(
        [sys.executable, "-c", script, str(tmp_path)], capture_output=True, text=True, check=False
    )
    assert result.returncode == 0, result.stderr + result.stdout
    assert not list(tmp_path.rglob("*.sqlite"))
