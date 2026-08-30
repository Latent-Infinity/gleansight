from __future__ import annotations

from pathlib import Path

import pytest

from papers.config.settings import NsqdAutonomousTauRouteSettings, load_settings


def _write_defaults(path: Path) -> None:
    path.write_text(
        """
[data]
root = "data"
db_path = "data/db/app.sqlite"
blobs_dir = "data/blobs"
blobs_pdf_dir = "data/blobs/pdf"
blobs_md_dir = "data/blobs/md"
blobs_analysis_dir = "data/blobs/analysis"
lancedb_dir = "data/lancedb"

[embeddings]
model = "qwen3-embedding:latest"
dimension = 4096
text_slice_strategy = "markdown_full"
base_url = "http://127.0.0.1:11434"

[llm]
default_profile = "default"
default_model = "qwen3.6:35b-a3b-q4_K_M"

[scholar]
api_key = ""
rate_limit_per_second = 1

[ui]
search_max_results = 10

[nsqd]
enabled_operators = ["A"]

[nsqd.autonomous_tau.writer]
agent_id = "tau-writer-local-v1"
provider = "ollama"
model = "qwen3.6:35b-a3b-q4_K_M"
version = "2026-08-24"
profile = "tau-writer-local"
base_url = "http://127.0.0.1:11434"
api_key = ""

[nsqd.autonomous_tau.reviewer]
agent_id = "tau-reviewer-local-v1"
provider = "ollama"
model = "qwen3.6:35b-a3b-q4_K_M"
version = "2026-08-24"
profile = "tau-reviewer-local"
base_url = "http://127.0.0.1:11434"
api_key = ""

[nsqd.autonomous_tau.adjudicator]
agent_id = "tau-adjudicator-frontier-v1"
provider = "codex_subscription"
model = "gpt-5.6-terra"
version = "config-2026-08-29"
profile = "tau-adjudicator-frontier"
base_url = ""
api_key = ""
executable_path = "codex"
reasoning_effort = "high"

[nsqd.autonomous_tau.audit]
sample_rate = 0.10
policy_revision = "tau-audit/1"
""".strip(),
        encoding="utf-8",
    )


def test_load_settings_reads_autonomous_tau_defaults(tmp_path: Path) -> None:
    defaults_path = tmp_path / "defaults.toml"
    _write_defaults(defaults_path)

    settings = load_settings(defaults_path=defaults_path, base_dir=tmp_path)

    assert settings.nsqd.autonomous_tau.rounds == 4
    assert settings.nsqd.autonomous_tau.audit.sample_rate == 0.10
    assert settings.nsqd.autonomous_tau.writer.agent_id == "tau-writer-local-v1"
    assert settings.nsqd.autonomous_tau.reviewer.api_key == ""
    assert settings.nsqd.autonomous_tau.adjudicator.provider == "codex_subscription"
    assert settings.nsqd.autonomous_tau.adjudicator.executable_path == "codex"
    assert settings.nsqd.autonomous_tau.adjudicator.model == "gpt-5.6-terra"


def test_load_settings_allows_blank_adjudicator_route_until_escalation(tmp_path: Path) -> None:
    defaults_path = tmp_path / "defaults.toml"
    _write_defaults(defaults_path)
    contents = defaults_path.read_text(encoding="utf-8")
    defaults_path.write_text(contents, encoding="utf-8")

    settings = load_settings(defaults_path=defaults_path, base_dir=tmp_path)

    assert settings.nsqd.autonomous_tau.adjudicator.base_url == ""
    assert settings.nsqd.autonomous_tau.adjudicator.executable_path == "codex"


def test_autonomous_tau_route_settings_reject_non_string_base_url() -> None:
    with pytest.raises(ValueError, match="base_url must be a string"):
        NsqdAutonomousTauRouteSettings.model_validate(
            {
                "agent_id": "tau-writer-local-v1",
                "provider": "ollama",
                "model": "qwen3.6:35b-a3b-q4_K_M",
                "version": "2026-08-24",
                "profile": "tau-writer-local",
                "base_url": 42,
                "api_key": "",
            }
        )


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("agent_id", 1, "agent_id must be a string"),
        ("executable_path", 1, "executable_path must be a string"),
        ("reasoning_effort", 1, "reasoning_effort must be a string"),
        ("api_key", 1, "api_key must be a string"),
    ],
)
def test_autonomous_tau_route_settings_reject_invalid_field_types(
    field: str,
    value: object,
    message: str,
) -> None:
    payload: dict[str, object] = {
        "agent_id": "tau-writer-local-v1",
        "provider": "ollama",
        "model": "qwen3.6:35b-a3b-q4_K_M",
        "version": "2026-08-24",
        "profile": "tau-writer-local",
        "base_url": "http://127.0.0.1:11434",
        "api_key": "",
        "executable_path": "",
        "reasoning_effort": "",
    }
    payload[field] = value
    with pytest.raises(ValueError, match=message):
        NsqdAutonomousTauRouteSettings.model_validate(payload)


def test_autonomous_tau_route_settings_allow_blank_codex_model_and_version() -> None:
    settings = NsqdAutonomousTauRouteSettings.model_validate(
        {
            "agent_id": "tau-adjudicator-frontier-v1",
            "provider": "codex_subscription",
            "model": None,
            "version": None,
            "profile": "tau-adjudicator-frontier",
            "base_url": None,
            "api_key": None,
            "executable_path": None,
            "reasoning_effort": None,
        }
    )
    assert settings.model == ""
    assert settings.version == ""
    assert settings.base_url == ""


def test_autonomous_tau_route_settings_reject_blank_non_codex_model_and_version() -> None:
    with pytest.raises(ValueError, match="model must not be blank"):
        NsqdAutonomousTauRouteSettings.model_validate(
            {
                "agent_id": "tau-writer-local-v1",
                "provider": "ollama",
                "model": "",
                "version": "2026-08-24",
                "profile": "tau-writer-local",
                "base_url": "http://127.0.0.1:11434",
                "api_key": "",
            }
        )
    with pytest.raises(ValueError, match="version must not be blank"):
        NsqdAutonomousTauRouteSettings.model_validate(
            {
                "agent_id": "tau-writer-local-v1",
                "provider": "ollama",
                "model": "qwen3.6:35b-a3b-q4_K_M",
                "version": "",
                "profile": "tau-writer-local",
                "base_url": "http://127.0.0.1:11434",
                "api_key": "",
            }
        )


def test_autonomous_tau_route_settings_reject_unknown_provider() -> None:
    with pytest.raises(ValueError, match="provider must be ollama"):
        NsqdAutonomousTauRouteSettings.model_validate(
            {
                "agent_id": "tau-writer-local-v1",
                "provider": "olama",
                "model": "qwen3:8b",
                "version": "2026-08-24",
                "profile": "tau-writer-local",
            }
        )


def test_load_settings_rejects_overlapping_autonomous_agent_ids(tmp_path: Path) -> None:
    defaults_path = tmp_path / "defaults.toml"
    _write_defaults(defaults_path)
    override_path = tmp_path / "override.toml"
    override_path.write_text(
        """
[nsqd.autonomous_tau.reviewer]
agent_id = "tau-writer-local-v1"
provider = "ollama"
model = "qwen3.6:35b-a3b-q4_K_M"
version = "2026-08-24"
profile = "tau-reviewer-local"
base_url = "http://127.0.0.1:11434"
api_key = ""
""".strip(),
        encoding="utf-8",
    )

    with pytest.raises(Exception, match="writer and reviewer agent_id values must differ"):
        load_settings(defaults_path=defaults_path, override_path=override_path, base_dir=tmp_path)
