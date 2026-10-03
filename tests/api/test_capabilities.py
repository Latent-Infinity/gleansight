from pathlib import Path

from gleansight.api import ApiConfiguration, Failure, GleansightAPI, Success


def test_capabilities_report_configured_operators_without_storage(tmp_path: Path) -> None:
    config = tmp_path / "settings.toml"
    config.write_text('[nsqd]\nenabled_operators = ["A", "B", "E"]\n', encoding="utf-8")
    api = GleansightAPI(ApiConfiguration(repo_root=tmp_path, config_path=config))
    result = api.call("system.capabilities", {})
    assert isinstance(result, Success)
    assert isinstance(result.data, dict)
    assert result.data["enabled_operators"] == ["A", "B", "E"]
    assert result.data["approval_operations_enabled"] is False
    assert list(tmp_path.iterdir()) == [config]


def test_capabilities_configuration_errors_remain_sanitized(tmp_path: Path) -> None:
    api = GleansightAPI(ApiConfiguration(repo_root=tmp_path, config_path=Path("missing.toml")))
    result = api.call("system.capabilities", {})
    assert isinstance(result, Failure)
    assert result.error.code == "configuration_error"
    assert not list(tmp_path.iterdir())
