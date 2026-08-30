from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from typer.testing import CliRunner

import nsqd.__main__ as main_module
from nsqd import cli as cli_module
from nsqd.cli import app
from nsqd.domain.tau_review import autonomous_tau_review_packet_digest
from nsqd.null_adapters import HashParaphraseEmbedder
from papers.domain.errors import ConfigurationError, ErrorCode, PipelineError
from papers.infra.piccolo.database import PiccoloDatabase

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "approved" / "nsqd"


def test_module_main_invokes_app(monkeypatch) -> None:
    called = {"ok": False}

    def fake_app() -> None:
        called["ok"] = True

    monkeypatch.setattr(main_module, "app", fake_app)
    monkeypatch.setattr(cli_module, "app", fake_app)
    main_module.main()
    cli_module.main()
    assert called["ok"] is True


def test_skeleton_help_lists_command() -> None:
    runner = CliRunner()
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "skeleton" in result.output
    assert "harvest" in result.output
    assert "project" in result.output
    assert "map" in result.output
    assert "diverge" in result.output
    assert "ground" in result.output
    assert "export-tau-measurements" in result.output
    assert "tau-measurement-inventory" in result.output
    assert "evaluate-autonomous-tau-reviews" in result.output
    assert "gate" in result.output
    assert "archive" in result.output
    assert "approve-digest" in result.output
    assert "acquire" in result.output
    assert "run-paper-jobs" in result.output


def test_diverge_cli_does_not_expose_operator_switch() -> None:
    result = CliRunner().invoke(app, ["diverge", "--help"])
    assert result.exit_code == 0
    assert "--operator" not in result.output


def test_score_cli_does_not_expose_tau_switch() -> None:
    result = CliRunner().invoke(app, ["gate", "--help"])
    assert result.exit_code == 0
    assert "--tau" not in result.output


def test_tau_measurement_commands_use_persisted_evidence_boundary(monkeypatch) -> None:
    captured: dict[str, object] = {}
    candidates = object()
    approved = frozenset({"a" * 64})
    container = SimpleNamespace(
        ctx=SimpleNamespace(
            candidates=candidates,
            approved_projection_digests=approved,
        )
    )

    class FakeEvidenceUseCase:
        def __init__(self, *, candidates: object, approved_projection_digests: object) -> None:
            captured["candidates"] = candidates
            captured["approved"] = approved_projection_digests

        def export_jsonl(self, hashes: list[str]) -> bytes:
            captured["export_hashes"] = hashes
            return b'{"pair_id":"pair-1"}\n'

        def inventory(self, hashes: list[str]) -> dict[str, object]:
            captured["inventory_hashes"] = hashes
            return {"qualified_pair_count": len(hashes)}

    monkeypatch.setattr(cli_module, "_container", lambda _db, _index, _config=None: container)
    monkeypatch.setattr(cli_module, "TauMeasurementEvidenceUseCase", FakeEvidenceUseCase)
    digest = "b" * 64

    exported = CliRunner().invoke(
        app,
        ["export-tau-measurements", "--candidate-artifact-hash", digest],
    )
    assert exported.exit_code == 0
    assert exported.output == '{"pair_id":"pair-1"}\n'

    inventoried = CliRunner().invoke(
        app,
        ["tau-measurement-inventory", "--candidate-artifact-hash", digest],
    )
    assert inventoried.exit_code == 0
    assert json.loads(inventoried.output) == {"qualified_pair_count": 1}
    assert captured == {
        "candidates": candidates,
        "approved": approved,
        "export_hashes": [digest],
        "inventory_hashes": [digest],
    }


def test_autonomous_tau_review_cli_uses_configured_boundary_and_persists_packet(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    captured: dict[str, object] = {}
    output = tmp_path / "tau-review.json"
    candidates = object()
    approved = frozenset({"a" * 64})
    container = SimpleNamespace(
        clock=object(),
        ctx=SimpleNamespace(candidates=candidates, approved_projection_digests=approved),
    )
    settings = SimpleNamespace(
        nsqd=SimpleNamespace(
            autonomous_tau=SimpleNamespace(
                writer=SimpleNamespace(base_url="http://127.0.0.1:11434"),
            )
        )
    )

    class FakeEvidenceUseCase:
        def __init__(self, *, candidates: object, approved_projection_digests: object) -> None:
            captured["candidates"] = candidates
            captured["approved"] = approved_projection_digests

    class FakeAutonomousUseCase:
        def __init__(
            self,
            *,
            measurement_evidence: object,
            llm_client: object,
            clock: object,
            settings: object,
        ) -> None:
            captured["measurement_evidence"] = measurement_evidence.__class__.__name__
            captured["llm_client"] = llm_client
            captured["clock"] = clock
            captured["settings"] = settings

        def run(self, hashes: list[str]) -> dict[str, object]:
            captured["hashes"] = hashes
            return {
                "packet_digest": "d" * 64,
                "packet": {"approved_pair_count": 1, "ambiguous_pair_count": 0},
                "rows": [{"pair_id": "finance/1:pair:1"}],
            }

    def fake_client(*, base_url: str, api_key: str | None = None) -> object:
        captured["client_base_url"] = base_url
        captured["client_api_key"] = api_key
        return object()

    monkeypatch.setattr(cli_module, "_container", lambda _db, _index, _config=None: container)
    monkeypatch.setattr(cli_module, "_standalone_settings", lambda _config=None: settings)
    monkeypatch.setattr(cli_module, "TauMeasurementEvidenceUseCase", FakeEvidenceUseCase)
    monkeypatch.setattr(cli_module, "AutonomousTauLabelingUseCase", FakeAutonomousUseCase)
    monkeypatch.setattr(cli_module, "build_openai_compat_client", fake_client)

    digest_a = "b" * 64
    digest_b = "c" * 64
    result = CliRunner().invoke(
        app,
        [
            "autonomous-tau-review",
            "--candidate-artifact-hash",
            digest_a,
            "--candidate-artifact-hash",
            digest_b,
            "--output",
            str(output),
        ],
    )

    assert result.exit_code == 0
    assert json.loads(output.read_text(encoding="utf-8")) == {
        "packet_digest": "d" * 64,
        "packet": {"approved_pair_count": 1, "ambiguous_pair_count": 0},
        "rows": [{"pair_id": "finance/1:pair:1"}],
    }
    assert "frontier-key" not in result.output
    assert captured == {
        "candidates": candidates,
        "approved": approved,
        "measurement_evidence": "FakeEvidenceUseCase",
        "llm_client": captured["llm_client"],
        "clock": captured["clock"],
        "settings": settings.nsqd.autonomous_tau,
        "hashes": [digest_a, digest_b],
        "client_base_url": "http://127.0.0.1:11434",
        "client_api_key": None,
    }


def test_evaluate_autonomous_tau_reviews_cli_revalidates_and_merges_packets(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    captured: dict[str, object] = {}
    rows = [
        {"candidate_artifact_hash": "b" * 64, "pair_id": "finance/1:pair:1"},
        {"candidate_artifact_hash": "c" * 64, "pair_id": "optimization/1:pair:1"},
    ]
    inputs: list[Path] = []
    for index, row in enumerate(rows):
        path = tmp_path / f"row-{index}.json"
        path.write_text(
            json.dumps(
                {
                    "rows": [row],
                    "packet_digest": autonomous_tau_review_packet_digest([row]),
                }
            ),
            encoding="utf-8",
        )
        inputs.append(path)
    output = tmp_path / "merged.json"
    container = SimpleNamespace(
        ctx=SimpleNamespace(candidates=object(), approved_projection_digests=frozenset())
    )
    settings = SimpleNamespace(
        nsqd=SimpleNamespace(
            autonomous_tau=SimpleNamespace(
                audit=SimpleNamespace(policy_revision="tau-audit/1", sample_rate=0.10)
            )
        )
    )

    class FakeEvidenceUseCase:
        def __init__(self, *, candidates: object, approved_projection_digests: object) -> None:
            captured["candidates"] = candidates
            captured["approved"] = approved_projection_digests

    class FakeEvaluationUseCase:
        def __init__(
            self,
            *,
            measurement_evidence: object,
            audit_policy_revision: str,
            audit_sample_rate: float,
        ) -> None:
            captured["evidence"] = measurement_evidence.__class__.__name__
            captured["audit_policy_revision"] = audit_policy_revision
            captured["audit_sample_rate"] = audit_sample_rate

        def run(
            self,
            hashes: list[str],
            reviewed_rows: list[dict[str, object]],
            *,
            require_balanced: bool = False,
        ) -> dict[str, object]:
            captured["hashes"] = hashes
            captured["rows"] = reviewed_rows
            captured["require_balanced"] = require_balanced
            return {
                "rows": reviewed_rows,
                "packet": {"approved_pair_count": 2, "ambiguous_pair_count": 0},
                "packet_digest": "d" * 64,
            }

    monkeypatch.setattr(cli_module, "_container", lambda _db, _index, _config=None: container)
    monkeypatch.setattr(cli_module, "_standalone_settings", lambda _config=None: settings)
    monkeypatch.setattr(cli_module, "TauMeasurementEvidenceUseCase", FakeEvidenceUseCase)
    monkeypatch.setattr(cli_module, "AutonomousTauPacketEvaluationUseCase", FakeEvaluationUseCase)
    result = CliRunner().invoke(
        app,
        [
            "evaluate-autonomous-tau-reviews",
            "--candidate-artifact-hash",
            "b" * 64,
            "--candidate-artifact-hash",
            "c" * 64,
            "--input",
            str(inputs[0]),
            "--input",
            str(inputs[1]),
            "--output",
            str(output),
            "--require-balanced",
        ],
    )

    assert result.exit_code == 0, result.output
    assert json.loads(output.read_text(encoding="utf-8"))["packet_digest"] == "d" * 64
    assert captured["rows"] == rows
    assert captured["hashes"] == ["b" * 64, "c" * 64]
    assert captured["audit_policy_revision"] == "tau-audit/1"
    assert captured["audit_sample_rate"] == 0.10
    assert captured["require_balanced"] is True


def test_load_autonomous_tau_rows_rejects_oversized_packet(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    packet = tmp_path / "oversized.json"
    packet.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(cli_module, "MAX_AUTONOMOUS_TAU_PACKET_BYTES", 1)

    with pytest.raises(ValueError, match="exceeds byte limit"):
        cli_module._load_autonomous_tau_rows([packet])


def test_autonomous_tau_review_cli_reports_frontier_config_error_only_on_escalation(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    output = tmp_path / "tau-review.json"
    container = SimpleNamespace(
        clock=object(),
        ctx=SimpleNamespace(candidates=object(), approved_projection_digests=frozenset()),
    )
    settings = SimpleNamespace(
        nsqd=SimpleNamespace(
            autonomous_tau=SimpleNamespace(
                writer=SimpleNamespace(base_url="http://127.0.0.1:11434")
            )
        )
    )

    class FakeEvidenceUseCase:
        def __init__(self, *, candidates: object, approved_projection_digests: object) -> None:
            pass

    class FailingAutonomousUseCase:
        def __init__(
            self,
            *,
            measurement_evidence: object,
            llm_client: object,
            clock: object,
            settings: object,
        ) -> None:
            pass

        def run(self, hashes: list[str]) -> dict[str, object]:
            raise ValueError("frontier adjudicator route is not configured")

    monkeypatch.setattr(cli_module, "_container", lambda _db, _index, _config=None: container)
    monkeypatch.setattr(cli_module, "_standalone_settings", lambda _config=None: settings)
    monkeypatch.setattr(cli_module, "TauMeasurementEvidenceUseCase", FakeEvidenceUseCase)
    monkeypatch.setattr(cli_module, "AutonomousTauLabelingUseCase", FailingAutonomousUseCase)
    monkeypatch.setattr(cli_module, "build_openai_compat_client", lambda **_kwargs: object())

    result = CliRunner().invoke(
        app,
        [
            "autonomous-tau-review",
            "--candidate-artifact-hash",
            "b" * 64,
            "--output",
            str(output),
        ],
        catch_exceptions=False,
    )

    assert result.exit_code == 1
    assert result.stdout == ""
    assert result.stderr == "error: frontier adjudicator route is not configured\n"


def test_container_uses_local_qwen_embedder_contract(monkeypatch, tmp_path: Path) -> None:
    captured: dict[str, object] = {}
    fake_embedder = object()

    def fake_standalone_embedder(config: Path | None = None) -> object:
        captured["config"] = config
        return fake_embedder

    def fake_build_container(**kwargs: object) -> object:
        captured.update(kwargs)
        return object()

    monkeypatch.setattr(cli_module, "_standalone_embedder", fake_standalone_embedder)
    monkeypatch.setattr(cli_module, "build_container", fake_build_container)

    cli_module._container(tmp_path / "nsqd.sqlite", tmp_path / "index")

    assert captured["db_path"] == tmp_path / "nsqd.sqlite"
    assert captured["index_path"] == tmp_path / "index"
    assert captured["embedder"] is fake_embedder
    assert captured["enabled_operators"] == frozenset({"A"})
    assert captured["novelty_threshold_tau"] == 0.45


def test_container_passes_config_operator_allowlist(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    captured: dict[str, object] = {}

    def fake_build_container(**kwargs: object) -> object:
        captured.update(kwargs)
        return object()

    monkeypatch.setattr(cli_module, "_standalone_embedder", lambda _config=None: object())
    monkeypatch.setattr(cli_module, "build_container", fake_build_container)
    monkeypatch.setattr(
        cli_module,
        "_standalone_settings",
        lambda _config=None: SimpleNamespace(
            nsqd=SimpleNamespace(enabled_operators=("A", "B"), novelty_threshold_tau=0.30)
        ),
    )

    cli_module._container(tmp_path / "nsqd.sqlite", tmp_path / "index")

    assert captured["enabled_operators"] == frozenset({"A", "B"})
    assert captured["novelty_threshold_tau"] == 0.30


def test_container_uses_config_override_for_standalone_embedding_settings(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    override = tmp_path / "nsqd-override.toml"
    override.write_text(
        """
[embeddings]
model = "custom-embed:dev"
dimension = 12
base_url = "http://localhost:9999"
text_slice_strategy = "markdown_full"
""".strip(),
        encoding="utf-8",
    )
    captured: dict[str, object] = {}
    fake_embedder = SimpleNamespace(
        model_id=lambda: "custom-embed",
        model_version=lambda: "dev",
        dimension=lambda: 12,
        normalization_policy=lambda: "l2",
        embed=lambda _text: [1.0, 0.0],
    )

    def fake_build_configured_ollama_embedder(embedding_settings) -> object:
        captured["model"] = embedding_settings.model
        captured["dimension"] = embedding_settings.dimension
        captured["base_url"] = embedding_settings.base_url
        return fake_embedder

    monkeypatch.setattr(
        cli_module,
        "build_local_ollama_embedder",
        fake_build_configured_ollama_embedder,
    )

    cli_module._container(tmp_path / "nsqd.sqlite", tmp_path / "index", override)

    assert captured == {
        "model": "custom-embed:dev",
        "dimension": 12,
        "base_url": "http://localhost:9999",
    }


def test_project_cli_supplies_production_embedder(monkeypatch, tmp_path: Path) -> None:
    runner = CliRunner()
    captured: dict[str, object] = {}
    fake_embedder = object()

    def fake_standalone_embedder(config: Path | None = None) -> object:
        captured["config"] = config
        captured["factory_called"] = True
        return fake_embedder

    def fake_run_project(**kwargs: object) -> dict[str, object]:
        captured.update(kwargs)
        return {
            "record_id": "rec-1",
            "created": True,
            "snapshot_id": "snap-1",
        }

    monkeypatch.setattr(cli_module, "_standalone_embedder", fake_standalone_embedder)
    monkeypatch.setattr(cli_module, "run_project", fake_run_project)

    result = runner.invoke(
        app,
        [
            "project",
            "--projection",
            str(FIXTURES / "paper-a.yaml"),
            "--manifest",
            str(FIXTURES / "manifest.toml"),
            "--db",
            str(tmp_path / "nsqd.sqlite"),
            "--index",
            str(tmp_path / "corpus.lancedb"),
        ],
    )

    assert result.exit_code == 0, result.output
    assert captured["factory_called"] is True
    assert captured["embedder"] is fake_embedder


def test_harvest_cli_supplies_production_embedder(monkeypatch, tmp_path: Path) -> None:
    runner = CliRunner()
    captured: dict[str, object] = {}
    fake_embedder = object()
    harvest_file = tmp_path / "records.yaml"
    harvest_file.write_text("records: []\n", encoding="utf-8")

    def fake_standalone_embedder(config: Path | None = None) -> object:
        captured["config"] = config
        captured["factory_called"] = True
        return fake_embedder

    def fake_run_harvest(**kwargs: object) -> dict[str, object]:
        captured.update(kwargs)
        return {"record_ids": ["rec-1"]}

    monkeypatch.setattr(cli_module, "_standalone_embedder", fake_standalone_embedder)
    monkeypatch.setattr(cli_module, "run_harvest", fake_run_harvest)

    result = runner.invoke(
        app,
        [
            "harvest",
            "--file",
            str(harvest_file),
            "--db",
            str(tmp_path / "nsqd.sqlite"),
            "--index",
            str(tmp_path / "corpus.lancedb"),
        ],
    )

    assert result.exit_code == 0, result.output
    assert captured["factory_called"] is True
    assert captured["embedder"] is fake_embedder


def test_project_cli_reports_unavailable_ollama_without_traceback(monkeypatch) -> None:
    runner = CliRunner()

    def unavailable(**_kwargs: object) -> dict[str, object]:
        raise PipelineError(ErrorCode.EMBEDDING_FAILED, "Ollama is unavailable")

    monkeypatch.setattr(cli_module, "run_project", unavailable)

    result = runner.invoke(
        app,
        [
            "project",
            "--projection",
            str(FIXTURES / "paper-a.yaml"),
            "--manifest",
            str(FIXTURES / "manifest.toml"),
        ],
    )

    assert result.exit_code == 1
    assert result.output == "error: Ollama is unavailable\n"


def test_skeleton_cli_runs_gamma_flow(tmp_path: Path) -> None:
    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "skeleton",
            "--candidate-fixture",
            str(FIXTURES / "gamma-flow.yaml"),
            "--axiom",
            "predictors assume stationary return signal",
            "--db",
            str(tmp_path / "nsqd.sqlite"),
            "--index",
            str(tmp_path / "corpus.lancedb"),
        ],
    )
    assert result.exit_code == 0, result.output
    assert "rejected" in result.output
    assert "viability=0" in result.output
    assert "archive_empty" in result.output


def test_skeleton_cli_reports_non_mapping_yaml_concisely(tmp_path: Path) -> None:
    runner = CliRunner()
    fixture = tmp_path / "candidate.yaml"
    fixture.write_text("- item\n", encoding="utf-8")

    result = runner.invoke(
        app,
        [
            "skeleton",
            "--candidate-fixture",
            str(fixture),
            "--axiom",
            "predictors assume stationary return signal",
            "--db",
            str(tmp_path / "nsqd.sqlite"),
            "--index",
            str(tmp_path / "corpus.lancedb"),
        ],
        catch_exceptions=False,
    )

    assert result.exit_code != 0
    assert result.stdout == ""
    assert result.stderr == "error: candidate fixture must be a mapping\n"


def test_skeleton_cli_reports_startup_errors_concisely(monkeypatch, tmp_path: Path) -> None:
    runner = CliRunner()

    def boom(**_: object) -> None:
        raise OSError("adapter startup failed")

    monkeypatch.setattr(cli_module, "run_skeleton", boom)
    result = runner.invoke(
        app,
        [
            "skeleton",
            "--candidate-fixture",
            str(FIXTURES / "gamma-flow.yaml"),
            "--axiom",
            "predictors assume stationary return signal",
            "--db",
            str(tmp_path / "nsqd.sqlite"),
            "--index",
            str(tmp_path / "corpus.lancedb"),
        ],
        catch_exceptions=False,
    )

    assert result.exit_code != 0
    assert result.stdout == ""
    assert result.stderr == "error: adapter startup failed\n"


def test_project_cli_runs_approved_projection(monkeypatch, tmp_path: Path) -> None:
    runner = CliRunner()
    cli_module._cli_options["config"] = None
    monkeypatch.setattr(
        cli_module,
        "_standalone_embedder",
        lambda _config=None: HashParaphraseEmbedder(),
    )
    result = runner.invoke(
        app,
        [
            "project",
            "--projection",
            str(FIXTURES / "paper-a.yaml"),
            "--manifest",
            str(FIXTURES / "manifest.toml"),
            "--db",
            str(tmp_path / "nsqd.sqlite"),
            "--index",
            str(tmp_path / "corpus.lancedb"),
        ],
    )
    assert result.exit_code == 0, result.output
    assert "projected" in result.output
    assert "created=True" in result.output


def test_standalone_root_config_changes_project_embedder(monkeypatch, tmp_path: Path) -> None:
    runner = CliRunner()
    override = tmp_path / "nsqd-override.toml"
    override.write_text(
        """
[embeddings]
model = "custom-embed:dev"
dimension = 12
base_url = "http://localhost:9999"
text_slice_strategy = "markdown_full"
""".strip(),
        encoding="utf-8",
    )
    captured: dict[str, object] = {}

    def fake_build_configured_ollama_embedder(embedding_settings) -> object:
        captured["model"] = embedding_settings.model
        captured["dimension"] = embedding_settings.dimension
        captured["base_url"] = embedding_settings.base_url
        return object()

    def fake_run_project(**kwargs: object) -> dict[str, object]:
        captured["embedder"] = kwargs["embedder"]
        return {"record_id": "rec-1", "created": True, "snapshot_id": "snap-1"}

    monkeypatch.setattr(
        cli_module,
        "build_local_ollama_embedder",
        fake_build_configured_ollama_embedder,
    )
    monkeypatch.setattr(cli_module, "run_project", fake_run_project)

    result = runner.invoke(
        app,
        [
            "--config",
            str(override),
            "project",
            "--projection",
            str(FIXTURES / "paper-a.yaml"),
            "--manifest",
            str(FIXTURES / "manifest.toml"),
        ],
    )

    assert result.exit_code == 0, result.output
    assert captured["model"] == "custom-embed:dev"
    assert captured["dimension"] == 12
    assert captured["base_url"] == "http://localhost:9999"


def test_project_cli_reports_manifest_rejection_concisely(tmp_path: Path) -> None:
    runner = CliRunner()
    fixture = tmp_path / "paper-a.yaml"
    fixture.write_text(
        (FIXTURES / "paper-a.yaml").read_text(encoding="utf-8") + "\n",
        encoding="utf-8",
    )

    result = runner.invoke(
        app,
        [
            "project",
            "--projection",
            str(fixture),
            "--manifest",
            str(FIXTURES / "manifest.toml"),
            "--db",
            str(tmp_path / "bad.sqlite"),
            "--index",
            str(tmp_path / "bad.lancedb"),
        ],
        catch_exceptions=False,
    )

    assert result.exit_code != 0
    assert result.stdout == ""
    assert "error:" in result.stderr
    assert "approved" in result.stderr or "content hash" in result.stderr


def test_map_and_archive_cli_on_empty_snapshot(tmp_path: Path) -> None:
    from datetime import UTC, datetime

    from nsqd.composition import build_container
    from nsqd.null_adapters import FixedClock

    db = tmp_path / "nsqd.sqlite"
    index = tmp_path / "index"
    container = build_container(
        db_path=db,
        index_path=index,
        clock=FixedClock(datetime(2024, 1, 1, tzinfo=UTC)),
    )
    assert container.ctx.snapshots.commit("snap", [], schema_version=1) == 1
    runner = CliRunner()
    mapped = runner.invoke(
        app,
        [
            "map",
            "--snapshot-id",
            "snap",
            "--domain-policy-id",
            "finance/1",
            "--snapshot-state",
            "calibration",
            "--db",
            str(db),
            "--index",
            str(index),
        ],
    )
    assert mapped.exit_code == 0, mapped.output
    assert "Unknown" in mapped.output
    archived = runner.invoke(
        app,
        [
            "archive",
            "--snapshot-id",
            "snap",
            "--domain-policy-id",
            "finance/1",
            "--db",
            str(db),
            "--index",
            str(index),
        ],
    )
    assert archived.exit_code == 0, archived.output
    assert "rank_guard_blocked" in archived.output


def test_map_cli_lists_window_days_override() -> None:
    from click import Group
    from typer.main import get_command

    click_app = get_command(app)
    assert isinstance(click_app, Group)
    command = click_app.commands["map"]
    opts = {opt for param in command.params for opt in param.opts}
    assert "--window-days" in opts


def test_diverge_ground_gate_cli_error_paths(tmp_path: Path) -> None:
    runner = CliRunner()
    fixture = tmp_path / "candidate.yaml"
    fixture.write_text("- item\n", encoding="utf-8")
    diverged = runner.invoke(
        app,
        [
            "diverge",
            "--candidate-fixture",
            str(fixture),
            "--axiom",
            "x",
            "--snapshot-id",
            "snap",
            "--domain-policy-id",
            "finance/1",
            "--db",
            str(tmp_path / "nsqd.sqlite"),
            "--index",
            str(tmp_path / "index"),
        ],
    )
    assert diverged.exit_code != 0
    ground = runner.invoke(
        app,
        [
            "ground",
            "--candidate-artifact-hash",
            "missing",
            "--snapshot-id",
            "snap",
            "--corpus-version",
            "1",
            "--db",
            str(tmp_path / "nsqd.sqlite"),
            "--index",
            str(tmp_path / "index"),
        ],
    )
    assert ground.exit_code != 0
    gated = runner.invoke(
        app,
        [
            "gate",
            "--candidate-artifact-hash",
            "missing",
            "--snapshot-id",
            "snap",
            "--corpus-version",
            "1",
            "--evaluator-run-id",
            "eval-1",
            "--db",
            str(tmp_path / "nsqd.sqlite"),
            "--index",
            str(tmp_path / "index"),
        ],
    )
    assert gated.exit_code != 0


def test_default_paper_runtime_uses_papers_settings(monkeypatch, tmp_path: Path) -> None:
    from types import SimpleNamespace

    from nsqd.infra.paper_runtime import NsqdPaperRuntime

    settings = SimpleNamespace(
        data=SimpleNamespace(db_path=tmp_path / "app.sqlite", root=tmp_path / "data"),
        llm=SimpleNamespace(default_profile="default", default_model="runtime-model-x"),
    )
    papers = SimpleNamespace(
        settings=settings,
        candidate_store=SimpleNamespace(
            create_candidate=lambda fields: fields["candidate_id"],
            get_candidate=lambda _cid: None,
            get_candidate_by_source=lambda *_a: None,
        ),
        paper_store=SimpleNamespace(get=lambda _pid: None),
        job_queue=SimpleNamespace(enqueue=lambda **_k: "job"),
        scholar_client=SimpleNamespace(search=lambda **_k: []),
        prompt_store=SimpleNamespace(
            get_prompt=lambda _pid: {"prompt_id": "nsqd-acquisition"},
            get_latest_version=lambda _pid: {"prompt_version_id": "v1"},
            create_prompt=lambda *_a, **_k: None,
            create_version=lambda *_a, **_k: None,
        ),
        profile_store=SimpleNamespace(
            get=lambda _pid: {
                "profile_id": "nsqd-acquisition",
                "name": "default",
                "base_url": "http://localhost:9",
            },
            create_profile=lambda *_a, **_k: None,
            update_profile=lambda *_a, **_k: None,
        ),
        analysis_store=SimpleNamespace(),
        blob_store=SimpleNamespace(get_markdown_path=lambda _pid: None),
        job_runner=SimpleNamespace(run_next=lambda _now: False),
        atomic_candidate_import=None,
        project_store=None,
        tag_store=None,
        external_id_store=None,
    )
    loaded_kwargs: dict[str, object] = {}
    built: dict[str, object] = {}

    def fake_load_settings(**kwargs: object) -> object:
        loaded_kwargs.update(kwargs)
        return settings

    def fake_build_papers(loaded: object, **kwargs: object) -> object:
        built["settings"] = loaded
        built["kwargs"] = kwargs
        return papers

    monkeypatch.setattr("papers.config.settings.load_settings", fake_load_settings)
    monkeypatch.setattr("papers.app.composition_root.build_container", fake_build_papers)
    runtime = cli_module._default_paper_runtime(
        config=tmp_path / "cfg.toml",
        db=tmp_path / "nsqd.sqlite",
        index=tmp_path / "index",
        llm_base_url="http://localhost:9",
        llm_api_key="k",
    )
    assert isinstance(runtime, NsqdPaperRuntime)
    assert loaded_kwargs["override_path"] == tmp_path / "cfg.toml"
    assert built["settings"] is settings
    assert runtime.nsqd.database.path == tmp_path / "nsqd.sqlite"


def test_acquire_and_run_paper_jobs_use_composed_runtime(monkeypatch, tmp_path: Path) -> None:
    from types import SimpleNamespace

    calls: list[tuple[str, object]] = []

    class _Runtime:
        def __init__(self) -> None:
            self.nsqd = SimpleNamespace(clock=SimpleNamespace(now=lambda: None))
            self.paper_runner = SimpleNamespace(run_next=lambda _now: False)

    def fake_runtime(**_kwargs: object) -> _Runtime:
        return _Runtime()

    def fake_run_job(
        container: object, job_type: str, payload: dict[str, object], now: object
    ) -> dict[str, object]:
        calls.append((job_type, payload))
        return {
            "stopped": "pending_human_approval",
            "route": "search",
            "projected": False,
            "snapshot_id": payload["snapshot_id"],
            "drafts": [
                {
                    "paper_id": "paper-1",
                    "source_paper_id": "source-1",
                    "paraphrase": "review me",
                    "paraphrase_source": "model",
                    "review_status": "pending",
                }
            ],
            "draft_count": 1,
        }

    monkeypatch.setattr(cli_module, "_default_paper_runtime", fake_runtime)
    monkeypatch.setattr(cli_module, "run_job", fake_run_job)
    runner = CliRunner()
    acquired = runner.invoke(
        app,
        [
            "acquire",
            "--snapshot-id",
            "snap",
            "--domain-policy-id",
            "finance/1",
            "--index",
            str(tmp_path / "index"),
        ],
    )
    assert acquired.exit_code == 0, acquired.output
    payload = __import__("json").loads(acquired.stdout)
    assert payload["stopped"] == "pending_human_approval"
    assert payload["draft_count"] == 1
    assert payload["drafts"] == [{"paper_id": "paper-1", "source_paper_id": "source-1"}]
    assert "review me" not in acquired.output
    assert calls[0][0] == "acquire"
    processed = runner.invoke(app, ["run-paper-jobs", "--max-jobs", "2"])
    assert processed.exit_code == 0, processed.output
    assert "processed 0 paper jobs" in processed.output


def test_acquire_show_drafts_opt_in_emits_bounded_draft_bodies(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    import json
    from types import SimpleNamespace

    class _Runtime:
        def __init__(self) -> None:
            self.nsqd = SimpleNamespace(clock=SimpleNamespace(now=lambda: None))
            self.paper_runner = SimpleNamespace(run_next=lambda _now: False)

    def fake_runtime(**_kwargs: object) -> _Runtime:
        return _Runtime()

    def fake_run_job(
        _container: object, _job_type: str, _payload: dict[str, object], _now: object
    ) -> dict[str, object]:
        return {
            "stopped": "pending_human_approval",
            "route": "search",
            "projected": False,
            "snapshot_id": "snap",
            "drafts": [
                {
                    "paper_id": "paper-1",
                    "source_paper_id": "source-1",
                    "paraphrase": "review me",
                    "paraphrase_source": "model",
                    "review_status": "pending",
                }
            ],
            "draft_count": 1,
        }

    monkeypatch.setattr(cli_module, "_default_paper_runtime", fake_runtime)
    monkeypatch.setattr(cli_module, "run_job", fake_run_job)

    acquired = CliRunner().invoke(
        app,
        [
            "acquire",
            "--snapshot-id",
            "snap",
            "--domain-policy-id",
            "finance/1",
            "--show-drafts",
            "--index",
            str(tmp_path / "index"),
        ],
    )

    assert acquired.exit_code == 0, acquired.output
    payload = json.loads(acquired.stdout)
    assert payload["draft_count"] == 1
    assert payload["drafts"][0]["paraphrase"] == "review me"
    assert payload["drafts"][0]["review_status"] == "pending"


def test_run_paper_jobs_refreshes_time_for_each_attempt(monkeypatch) -> None:
    from types import SimpleNamespace

    ticks = iter(("first", "second", "third"))
    seen: list[str] = []

    def run_next(now: str) -> bool:
        seen.append(now)
        return len(seen) < 3

    runtime = SimpleNamespace(
        nsqd=SimpleNamespace(clock=SimpleNamespace(now=lambda: next(ticks))),
        paper_runner=SimpleNamespace(run_next=run_next),
    )
    monkeypatch.setattr(cli_module, "_default_paper_runtime", lambda **_kwargs: runtime)

    result = CliRunner().invoke(app, ["run-paper-jobs", "--max-jobs", "3"])

    assert result.exit_code == 0, result.output
    assert "processed 2 paper jobs" in result.output
    assert seen == ["first", "second", "third"]


def test_run_paper_jobs_rejects_non_positive_limit() -> None:
    result = CliRunner().invoke(app, ["run-paper-jobs", "--max-jobs", "0"])

    assert result.exit_code == 2
    assert "range x>=1" in result.output


def test_default_paper_runtime_derives_nsqd_paths_from_config_root(
    monkeypatch, tmp_path: Path
) -> None:
    from types import SimpleNamespace

    root = tmp_path / "custom-data"
    settings = SimpleNamespace(data=SimpleNamespace(root=root))
    papers = SimpleNamespace(settings=settings)
    captured: dict[str, object] = {}

    monkeypatch.setattr("papers.config.settings.load_settings", lambda **_kwargs: settings)
    monkeypatch.setattr(
        "papers.app.composition_root.build_container", lambda *_args, **_kwargs: papers
    )

    def fake_compose(**kwargs: object) -> object:
        captured.update(kwargs)
        return object()

    monkeypatch.setattr("nsqd.infra.paper_runtime.compose_default_runtime", fake_compose)

    cli_module._default_paper_runtime(
        config=tmp_path / "config.toml",
        db=None,
        index=None,
        llm_base_url="http://localhost:8000",
        llm_api_key=None,
    )

    assert captured["nsqd_db_path"] == root / "nsqd" / "nsqd.sqlite"
    assert captured["nsqd_index_path"] == root / "nsqd" / "corpus.lancedb"


def test_acquire_forwards_approved_projection_file(monkeypatch, tmp_path: Path) -> None:
    from types import SimpleNamespace

    projection = FIXTURES / "paper-a.yaml"
    manifest = FIXTURES / "manifest.toml"
    captured: dict[str, object] = {}

    def fake_runtime(**kwargs: object) -> object:
        captured["runtime_kwargs"] = kwargs
        return SimpleNamespace(nsqd=SimpleNamespace(clock=SimpleNamespace(now=lambda: None)))

    def fake_run_job(
        _container: object, _job_type: str, payload: dict[str, object], _now: object
    ) -> dict[str, object]:
        captured["payload"] = payload
        return {
            "stopped": "sufficient",
            "route": "search",
            "projected": True,
            "snapshot_id": "new-snapshot",
        }

    monkeypatch.setattr(cli_module, "_default_paper_runtime", fake_runtime)
    monkeypatch.setattr(cli_module, "run_job", fake_run_job)
    result = CliRunner().invoke(
        app,
        [
            "acquire",
            "--snapshot-id",
            "snap",
            "--domain-policy-id",
            "finance/1",
            "--human-decision",
            "approve",
            "--approved-projection",
            str(projection),
            "--approval-manifest",
            str(manifest),
        ],
    )

    assert result.exit_code == 0, result.output
    payload = captured["payload"]
    assert isinstance(payload, dict)
    assert payload["snapshot_id"] == "snap"
    assert payload["human_decision"] == "approve"
    projections = payload["approved_projections"]
    assert isinstance(projections, list)
    projection_payload = projections[0]
    assert isinstance(projection_payload, dict)
    assert projection_payload["id"] == "DATA-NSQD-04"
    assert projection_payload["review_status"] == "approved"
    from nsqd.domain.project import canonical_reviewed_projection_digest

    assert captured["runtime_kwargs"] == {
        "config": None,
        "db": None,
        "index": None,
        "llm_base_url": "http://127.0.0.1:11434",
        "llm_api_key": None,
        "approved_projection_digests": frozenset(
            {canonical_reviewed_projection_digest(projection_payload)}
        ),
    }


def test_acquire_approval_projects_on_fresh_runtime(monkeypatch, tmp_path: Path) -> None:
    import json
    from dataclasses import replace
    from datetime import UTC, datetime
    from types import SimpleNamespace

    from nsqd.composition import build_container
    from nsqd.domain.policy import OPTIMIZATION_POLICY
    from nsqd.null_adapters import FixedClock
    from tests.facts.test_nsqd_acquisition_fallback import FakePaperBridge

    db = tmp_path / "nsqd.sqlite"
    index = tmp_path / "index"
    as_of = datetime(2024, 1, 1, tzinfo=UTC)
    source_paper_id = "7dbcef75-2d52-49a6-86a3-471be71f0fd7"
    policy = replace(
        OPTIMIZATION_POLICY,
        recall_probes=(("approved-paper", f"paper:{source_paper_id}", "paper"),),
    )
    bridge = FakePaperBridge(
        [
            {
                "paper_id": "paper-20",
                "source_paper_id": source_paper_id,
                "title": "Approved paper",
            }
        ]
    )
    seed = build_container(db_path=db, index_path=index, clock=FixedClock(as_of))
    seed.ctx.policies = {policy.policy_id: policy}
    assert seed.ctx.snapshots.commit("snap", [], schema_version=1) == 1

    def fake_runtime(**kwargs: object) -> object:
        raw_digests = kwargs.get("approved_projection_digests")
        assert raw_digests is None or isinstance(raw_digests, frozenset)
        container = build_container(
            db_path=db,
            index_path=index,
            clock=FixedClock(as_of),
            approved_projection_digests=raw_digests,
        )
        container.ctx.policies = {policy.policy_id: policy}
        container.ctx.bridge = bridge
        return SimpleNamespace(
            nsqd=container,
            paper_runner=SimpleNamespace(run_next=lambda _now: False),
        )

    monkeypatch.setattr(cli_module, "_default_paper_runtime", fake_runtime)
    runner = CliRunner()
    staged = runner.invoke(
        app,
        [
            "acquire",
            "--snapshot-id",
            "snap",
            "--domain-policy-id",
            "optimization/1",
        ],
    )
    assert staged.exit_code == 0, staged.output
    assert json.loads(staged.stdout)["stopped"] == "pending_human_approval"

    approved = runner.invoke(
        app,
        [
            "acquire",
            "--snapshot-id",
            "snap",
            "--domain-policy-id",
            "optimization/1",
            "--human-decision",
            "approve",
            "--approved-projection",
            str(FIXTURES / "paper-a.yaml"),
            "--approval-manifest",
            str(FIXTURES / "manifest.toml"),
        ],
    )

    assert approved.exit_code == 0, approved.output
    approved_payload = json.loads(approved.stdout)
    assert approved_payload["projected"] is True
    assert approved_payload["stopped"] == "sufficient"


def test_acquire_requires_manifest_for_approved_projection(tmp_path: Path) -> None:
    projection = FIXTURES / "paper-a.yaml"
    result = CliRunner().invoke(
        app,
        [
            "acquire",
            "--snapshot-id",
            "snap",
            "--domain-policy-id",
            "finance/1",
            "--approved-projection",
            str(projection),
        ],
    )

    assert result.exit_code == 1
    assert "--approval-manifest is required" in result.output


def test_default_runtime_commands_report_configuration_errors(monkeypatch) -> None:
    def fail_runtime(**_kwargs: object) -> object:
        raise ConfigurationError("paper runtime is not configured")

    monkeypatch.setattr(cli_module, "_default_paper_runtime", fail_runtime)
    runner = CliRunner()
    acquire_result = runner.invoke(
        app,
        [
            "acquire",
            "--snapshot-id",
            "snap",
            "--domain-policy-id",
            "finance/1",
        ],
    )
    worker_result = runner.invoke(app, ["run-paper-jobs"])

    assert acquire_result.exit_code == 1
    assert "error: Startup configuration failed" in acquire_result.output
    assert "paper runtime is not configured" not in acquire_result.output
    assert worker_result.exit_code == 1
    assert "error: Startup configuration failed" in worker_result.output
    assert "paper runtime is not configured" not in worker_result.output


def test_approve_digest_rejects_invalid_digest(tmp_path: Path) -> None:
    result = CliRunner().invoke(
        app,
        [
            "approve-digest",
            "--digest",
            "not-a-digest",
            "--db",
            str(tmp_path / "nsqd.sqlite"),
            "--index",
            str(tmp_path / "index"),
        ],
    )
    assert result.exit_code != 0
    assert "error" in result.output.lower()
    assert not (tmp_path / "nsqd.sqlite").exists()
    assert not (tmp_path / "index").exists()


def test_approve_digest_persists_allowlist(tmp_path: Path) -> None:
    digest = "cd" * 32
    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "approve-digest",
            "--digest",
            digest,
            "--db",
            str(tmp_path / "nsqd.sqlite"),
            "--index",
            str(tmp_path / "index"),
        ],
    )
    assert result.exit_code == 0, result.output
    assert digest in result.output
    assert not (tmp_path / "index").exists()
    from nsqd.composition import build_container

    container = build_container(
        db_path=tmp_path / "nsqd.sqlite",
        index_path=tmp_path / "index",
    )
    assert digest in container.ctx.approved_projection_digests


def test_approve_digest_reports_partial_schema_error(tmp_path: Path) -> None:
    db_path = tmp_path / "nsqd.sqlite"
    database = PiccoloDatabase(db_path)
    database.initialize_schema()
    database.execute(
        "DELETE FROM schema_migrations WHERE version = ?",
        ["010_nsqd_approval_bootstrap"],
    )
    database.execute("DROP TABLE nsqd_pre_digest_projections")

    result = CliRunner().invoke(
        app,
        [
            "approve-digest",
            "--digest",
            "ab" * 32,
            "--db",
            str(db_path),
            "--index",
            str(tmp_path / "index"),
        ],
    )

    assert result.exit_code == 1
    assert "error: existing NSQD approval bootstrap schema is partial" in result.output
    assert result.exception is not None
