from __future__ import annotations

import json
import signal
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Any, cast

import pytest

from papers.domain.errors import ErrorCode, PipelineError
from papers.infra.llm_codex_subscription.client import (
    CodexCommandResult,
    CodexSubscriptionClient,
    RoutedLLMClient,
    SubprocessCodexCommandRunner,
)


class FakeRunner:
    def __init__(
        self, handler: Callable[[list[str], Path, str | None, int | None], CodexCommandResult]
    ):
        self.handler = handler
        self.calls: list[dict[str, object]] = []

    def run(
        self,
        argv: list[str],
        *,
        cwd: Path,
        stdin_text: str | None = None,
        timeout_s: int | None = None,
    ) -> CodexCommandResult:
        self.calls.append(
            {
                "argv": list(argv),
                "cwd": cwd,
                "stdin_text": stdin_text,
                "timeout_s": timeout_s,
            }
        )
        return self.handler(argv, cwd, stdin_text, timeout_s)


def _schema_profile() -> dict[str, Any]:
    return {
        "provider": "codex_subscription",
        "executable_path": "codex",
        "reasoning_effort": "high",
        "chat_options": {
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": "tau_label",
                    "strict": True,
                    "schema": {
                        "type": "object",
                        "properties": {
                            "pair_id": {"type": "string"},
                            "label": {
                                "type": "string",
                                "enum": ["near_duplicate", "novel", "ambiguous"],
                            },
                            "rationale": {"type": "string"},
                        },
                        "required": ["pair_id", "label", "rationale"],
                        "additionalProperties": False,
                    },
                },
            }
        },
    }


def _ok_result() -> CodexCommandResult:
    return CodexCommandResult(returncode=0, stdout="", stderr="")


def test_codex_subscription_uses_argv_stdin_schema_and_temp_cleanup(tmp_path: Path) -> None:
    def handler(
        argv: list[str], cwd: Path, stdin_text: str | None, timeout_s: int | None
    ) -> CodexCommandResult:
        if argv == ["codex", "--version"]:
            return CodexCommandResult(returncode=0, stdout="codex 0.150.1\n", stderr="")
        if argv == ["codex", "login", "status"]:
            return CodexCommandResult(
                returncode=0,
                stdout="Logged in using ChatGPT\n",
                stderr="",
            )
        assert argv[:13] == [
            "codex",
            "exec",
            "--json",
            "--model",
            "gpt-5-codex",
            "--sandbox",
            "read-only",
            "--output-schema",
            argv[8],
            "--output-last-message",
            argv[10],
            "--ephemeral",
            "--ignore-user-config",
        ]
        assert argv[13:18] == [
            "--ignore-rules",
            "--skip-git-repo-check",
            "-c",
            "model_reasoning_effort=high",
            "-",
        ]
        assert stdin_text == "prompt body"
        assert timeout_s == 45
        assert cwd.exists()
        schema = json.loads(Path(argv[8]).read_text(encoding="utf-8"))
        assert schema["additionalProperties"] is False
        Path(argv[10]).write_text(
            json.dumps(
                {"pair_id": "pair-1", "label": "novel", "rationale": "distinct"},
                separators=(",", ":"),
            ),
            encoding="utf-8",
        )
        return CodexCommandResult(
            returncode=0,
            stdout='{"type":"thread.started"}\n{"type":"turn.completed"}\n',
            stderr="",
        )

    runner = FakeRunner(handler)
    client = CodexSubscriptionClient(command_runner=runner, temp_root=tmp_path)

    response = client.complete(
        prompt="prompt body",
        profile=_schema_profile(),
        model="gpt-5-codex",
        timeout_s=45,
    )

    assert response.text == '{"pair_id":"pair-1","label":"novel","rationale":"distinct"}'
    assert response.response_metadata == {
        "provider": "codex_subscription",
        "requested_model": "gpt-5-codex",
        "codex_cli_version": "0.150.1",
        "reasoning_effort": "high",
        "auth_mode": "chatgpt",
        "identity_source": "requested_and_reroute_checked",
    }
    assert not list(tmp_path.iterdir())


def test_codex_subscription_rejects_login_failure_without_leaking_stderr(tmp_path: Path) -> None:
    def handler(
        argv: list[str], cwd: Path, stdin_text: str | None, timeout_s: int | None
    ) -> CodexCommandResult:
        if argv == ["codex", "--version"]:
            return CodexCommandResult(returncode=0, stdout="codex 0.150.1\n", stderr="")
        return CodexCommandResult(returncode=1, stdout="", stderr="secret-token")

    client = CodexSubscriptionClient(command_runner=FakeRunner(handler), temp_root=tmp_path)
    with pytest.raises(PipelineError, match="codex login status failed") as exc:
        client.complete(prompt="x", profile=_schema_profile(), model="gpt-5-codex")
    assert exc.value.code == ErrorCode.LLM_ERROR
    assert "secret-token" not in str(exc.value)


def test_codex_subscription_accepts_chatgpt_login_status_on_stderr(tmp_path: Path) -> None:
    def handler(
        argv: list[str], cwd: Path, stdin_text: str | None, timeout_s: int | None
    ) -> CodexCommandResult:
        if argv == ["codex", "--version"]:
            return CodexCommandResult(returncode=0, stdout="codex 0.150.1\n", stderr="")
        if argv == ["codex", "login", "status"]:
            return CodexCommandResult(returncode=0, stdout="", stderr="Logged in using ChatGPT\n")
        Path(argv[10]).write_text(
            '{"pair_id":"pair-1","label":"novel","rationale":"ok"}',
            encoding="utf-8",
        )
        return CodexCommandResult(returncode=0, stdout='{"type":"turn.completed"}\n', stderr="")

    client = CodexSubscriptionClient(command_runner=FakeRunner(handler), temp_root=tmp_path)
    response = client.complete(prompt="x", profile=_schema_profile(), model="gpt-5-codex")
    assert response.response_metadata is not None
    assert response.response_metadata["auth_mode"] == "chatgpt"


def test_codex_subscription_rejects_blank_model_before_preflight(tmp_path: Path) -> None:
    runner = FakeRunner(lambda *_args: _ok_result())
    client = CodexSubscriptionClient(command_runner=runner, temp_root=tmp_path)
    with pytest.raises(PipelineError, match="requested model is required") as exc:
        client.complete(prompt="x", profile=_schema_profile(), model="   ")
    assert exc.value.code == ErrorCode.LLM_ERROR
    assert runner.calls == []


def test_codex_subscription_uses_default_executable_and_reasoning_effort(tmp_path: Path) -> None:
    profile = _schema_profile()
    profile["executable_path"] = 7
    profile["reasoning_effort"] = None

    def handler(
        argv: list[str], cwd: Path, stdin_text: str | None, timeout_s: int | None
    ) -> CodexCommandResult:
        if argv == ["codex", "--version"]:
            return CodexCommandResult(returncode=0, stdout="codex 0.150.1\n", stderr="")
        if argv == ["codex", "login", "status"]:
            return CodexCommandResult(returncode=0, stdout="Logged in using ChatGPT\n", stderr="")
        assert argv[0] == "codex"
        assert argv[-3:] == ["-c", "model_reasoning_effort=medium", "-"]
        Path(argv[10]).write_text(
            '{"pair_id":"pair-1","label":"novel","rationale":"ok"}',
            encoding="utf-8",
        )
        return CodexCommandResult(returncode=0, stdout='{"type":"turn.completed"}\n', stderr="")

    client = CodexSubscriptionClient(
        command_runner=FakeRunner(handler),
        temp_root=tmp_path,
        default_reasoning_effort="medium",
    )
    response = client.complete(prompt="x", profile=profile, model="gpt-5.6-terra")
    assert response.response_metadata is not None
    assert response.response_metadata["reasoning_effort"] == "medium"


def test_codex_subscription_rejects_preflight_version_failure(tmp_path: Path) -> None:
    def handler(
        argv: list[str], cwd: Path, stdin_text: str | None, timeout_s: int | None
    ) -> CodexCommandResult:
        return CodexCommandResult(returncode=1, stdout="", stderr="hidden-secret")

    client = CodexSubscriptionClient(command_runner=FakeRunner(handler), temp_root=tmp_path)
    with pytest.raises(PipelineError, match="codex --version failed") as exc:
        client.complete(prompt="x", profile=_schema_profile(), model="gpt-5.6-terra")
    assert exc.value.code == ErrorCode.LLM_ERROR
    assert "hidden-secret" not in str(exc.value)


def test_codex_subscription_rejects_invalid_version_output(tmp_path: Path) -> None:
    def handler(
        argv: list[str], cwd: Path, stdin_text: str | None, timeout_s: int | None
    ) -> CodexCommandResult:
        if argv == ["codex", "--version"]:
            return CodexCommandResult(returncode=0, stdout="codex version unknown\n", stderr="")
        return _ok_result()

    client = CodexSubscriptionClient(command_runner=FakeRunner(handler), temp_root=tmp_path)
    with pytest.raises(PipelineError, match="version output is invalid") as exc:
        client.complete(prompt="x", profile=_schema_profile(), model="gpt-5.6-terra")
    assert exc.value.code == ErrorCode.OUTPUT_PARSE_FAILED


def test_codex_subscription_rejects_non_chatgpt_login_status(tmp_path: Path) -> None:
    def handler(
        argv: list[str], cwd: Path, stdin_text: str | None, timeout_s: int | None
    ) -> CodexCommandResult:
        if argv == ["codex", "--version"]:
            return CodexCommandResult(returncode=0, stdout="codex 0.150.1\n", stderr="")
        return CodexCommandResult(returncode=0, stdout="Logged in with API key\n", stderr="")

    client = CodexSubscriptionClient(command_runner=FakeRunner(handler), temp_root=tmp_path)
    with pytest.raises(PipelineError, match="must use ChatGPT") as exc:
        client.complete(prompt="x", profile=_schema_profile(), model="gpt-5.6-terra")
    assert exc.value.code == ErrorCode.LLM_ERROR


def test_codex_subscription_rejects_missing_or_empty_output_file(tmp_path: Path) -> None:
    @pytest.mark.parametrize("write_empty", [False, True])
    def _unused() -> None:
        pass

    for write_empty in (False, True):

        def handler(
            argv: list[str], cwd: Path, stdin_text: str | None, timeout_s: int | None
        ) -> CodexCommandResult:
            if argv == ["codex", "--version"]:
                return CodexCommandResult(returncode=0, stdout="codex 0.150.1\n", stderr="")
            if argv == ["codex", "login", "status"]:
                return CodexCommandResult(
                    returncode=0,
                    stdout="Logged in using ChatGPT\n",
                    stderr="",
                )
            if write_empty:
                Path(argv[10]).write_text("   ", encoding="utf-8")
            return CodexCommandResult(returncode=0, stdout='{"type":"turn.completed"}\n', stderr="")

        client = CodexSubscriptionClient(command_runner=FakeRunner(handler), temp_root=tmp_path)
        with pytest.raises(PipelineError, match="missing final agent message") as exc:
            client.complete(prompt="x", profile=_schema_profile(), model="gpt-5.6-terra")
        assert exc.value.code == ErrorCode.OUTPUT_PARSE_FAILED


@pytest.mark.parametrize(
    "profile",
    [
        {},
        {"chat_options": {}},
        {"chat_options": {"response_format": {"type": "text"}}},
        {"chat_options": {"response_format": {"type": "json_schema"}}},
        {
            "chat_options": {
                "response_format": {
                    "type": "json_schema",
                    "json_schema": {"name": "tau_label", "strict": False, "schema": {}},
                }
            }
        },
    ],
)
def test_codex_subscription_rejects_missing_or_invalid_schema_profile(
    tmp_path: Path,
    profile: dict[str, Any],
) -> None:
    if profile:
        merged = {**_schema_profile(), **profile}
        if "chat_options" in profile:
            merged["chat_options"] = profile["chat_options"]
    else:
        merged = profile

    def handler(
        argv: list[str], cwd: Path, stdin_text: str | None, timeout_s: int | None
    ) -> CodexCommandResult:
        if argv == ["codex", "--version"]:
            return CodexCommandResult(returncode=0, stdout="codex 0.150.1\n", stderr="")
        if argv == ["codex", "login", "status"]:
            return CodexCommandResult(returncode=0, stdout="Logged in using ChatGPT\n", stderr="")
        return _ok_result()

    client = CodexSubscriptionClient(command_runner=FakeRunner(handler), temp_root=tmp_path)
    with pytest.raises(PipelineError, match="response_format json_schema is required"):
        client.complete(prompt="x", profile=merged, model="gpt-5.6-terra")


@pytest.mark.parametrize(
    "stdout", ['\n\n{"type":"turn.completed"}\n', '[]\n{"type":"turn.completed"}\n']
)
def test_codex_subscription_handles_empty_lines_and_rejects_non_mapping_jsonl(
    tmp_path: Path,
    stdout: str,
) -> None:
    def handler(
        argv: list[str], cwd: Path, stdin_text: str | None, timeout_s: int | None
    ) -> CodexCommandResult:
        if argv == ["codex", "--version"]:
            return CodexCommandResult(returncode=0, stdout="codex 0.150.1\n", stderr="")
        if argv == ["codex", "login", "status"]:
            return CodexCommandResult(returncode=0, stdout="Logged in using ChatGPT\n", stderr="")
        Path(argv[10]).write_text(
            '{"pair_id":"pair-1","label":"novel","rationale":"ok"}',
            encoding="utf-8",
        )
        return CodexCommandResult(returncode=0, stdout=stdout, stderr="")

    client = CodexSubscriptionClient(command_runner=FakeRunner(handler), temp_root=tmp_path)
    if stdout.startswith("\n"):
        response = client.complete(prompt="x", profile=_schema_profile(), model="gpt-5.6-terra")
        assert response.text
    else:
        with pytest.raises(PipelineError, match="malformed jsonl"):
            client.complete(prompt="x", profile=_schema_profile(), model="gpt-5.6-terra")


@pytest.mark.parametrize("output_text", ["not-json", "[]"])
def test_codex_subscription_rejects_invalid_json_or_nonmapping_output(
    tmp_path: Path,
    output_text: str,
) -> None:
    def handler(
        argv: list[str], cwd: Path, stdin_text: str | None, timeout_s: int | None
    ) -> CodexCommandResult:
        if argv == ["codex", "--version"]:
            return CodexCommandResult(returncode=0, stdout="codex 0.150.1\n", stderr="")
        if argv == ["codex", "login", "status"]:
            return CodexCommandResult(returncode=0, stdout="Logged in using ChatGPT\n", stderr="")
        Path(argv[10]).write_text(output_text, encoding="utf-8")
        return CodexCommandResult(returncode=0, stdout='{"type":"turn.completed"}\n', stderr="")

    client = CodexSubscriptionClient(command_runner=FakeRunner(handler), temp_root=tmp_path)
    with pytest.raises(PipelineError, match="invalid schema output"):
        client.complete(prompt="x", profile=_schema_profile(), model="gpt-5.6-terra")


def test_codex_subscription_rejects_timeout_and_nonzero_exec(tmp_path: Path) -> None:
    for result in (
        CodexCommandResult(returncode=-1, stdout="", stderr="", timed_out=True),
        CodexCommandResult(returncode=2, stdout="", stderr="private-secret", timed_out=False),
    ):

        def handler(
            argv: list[str], cwd: Path, stdin_text: str | None, timeout_s: int | None
        ) -> CodexCommandResult:
            if argv == ["codex", "--version"]:
                return CodexCommandResult(returncode=0, stdout="codex 0.150.1\n", stderr="")
            if argv == ["codex", "login", "status"]:
                return CodexCommandResult(
                    returncode=0, stdout="Logged in using ChatGPT\n", stderr=""
                )
            return result

        client = CodexSubscriptionClient(command_runner=FakeRunner(handler), temp_root=tmp_path)
        expected = "timed out" if result.timed_out else "exec failed"
        with pytest.raises(PipelineError, match=expected) as exc:
            client.complete(prompt="x", profile=_schema_profile(), model="gpt-5.6-terra")
        assert "private-secret" not in str(exc.value)


@pytest.mark.parametrize(
    ("stdout", "message"),
    [
        ('{"type":"turn.failed"}\n', "turn failed"),
        ('{"type":"error","message":"bad"}\n', "error event"),
        (
            '{"type":"item.completed","message":"model rerouted"}\n{"type":"turn.completed"}\n',
            "reroute",
        ),
        ("not-json\n", "malformed jsonl"),
        ('{"type":"thread.started"}\n', "turn.completed"),
    ],
)
def test_codex_subscription_rejects_bad_jsonl_events(
    tmp_path: Path,
    stdout: str,
    message: str,
) -> None:
    def handler(
        argv: list[str], cwd: Path, stdin_text: str | None, timeout_s: int | None
    ) -> CodexCommandResult:
        if argv == ["codex", "--version"]:
            return CodexCommandResult(returncode=0, stdout="codex 0.150.1\n", stderr="")
        if argv == ["codex", "login", "status"]:
            return CodexCommandResult(returncode=0, stdout="Logged in using ChatGPT\n", stderr="")
        Path(argv[10]).write_text(
            json.dumps({"pair_id": "pair-1", "label": "novel", "rationale": "ok"}),
            encoding="utf-8",
        )
        return CodexCommandResult(returncode=0, stdout=stdout, stderr="")

    client = CodexSubscriptionClient(command_runner=FakeRunner(handler), temp_root=tmp_path)
    with pytest.raises(PipelineError, match=message):
        client.complete(prompt="x", profile=_schema_profile(), model="gpt-5-codex")


@pytest.mark.parametrize(
    ("output_text", "message"),
    [
        ('{"pair_id":"pair-1","label":"novel"}', "rationale"),
        ('{"pair_id":"pair-1","label":"novel","rationale":"ok","extra":"x"}', "extra"),
        ('{"pair_id":7,"label":"novel","rationale":"ok"}', "pair_id"),
        ('{"pair_id":"pair-1","label":"blocked","rationale":"ok"}', "label"),
        ('{"pair_id":"pair-1","label":"novel","rationale":"   "}', "rationale"),
    ],
)
def test_codex_subscription_rejects_invalid_schema_output(
    tmp_path: Path,
    output_text: str,
    message: str,
) -> None:
    def handler(
        argv: list[str], cwd: Path, stdin_text: str | None, timeout_s: int | None
    ) -> CodexCommandResult:
        if argv == ["codex", "--version"]:
            return CodexCommandResult(returncode=0, stdout="codex 0.150.1\n", stderr="")
        if argv == ["codex", "login", "status"]:
            return CodexCommandResult(returncode=0, stdout="Logged in using ChatGPT\n", stderr="")
        Path(argv[10]).write_text(output_text, encoding="utf-8")
        return CodexCommandResult(returncode=0, stdout='{"type":"turn.completed"}\n', stderr="")

    client = CodexSubscriptionClient(command_runner=FakeRunner(handler), temp_root=tmp_path)
    with pytest.raises(PipelineError, match=message):
        client.complete(prompt="x", profile=_schema_profile(), model="gpt-5-codex")


def test_routed_llm_client_dispatches_by_provider() -> None:
    calls: list[str] = []

    class FakeClient:
        def __init__(self, name: str) -> None:
            self.name = name

        def complete(
            self,
            *,
            prompt: str,
            profile: dict[str, Any],
            model: str,
            timeout_s: int | None = None,
        ):
            calls.append(self.name)
            from papers.app.ports import LLMResponse

            return LLMResponse(text="ok", tokens_in=None, tokens_out=None, cost_usd=None)

    client = RoutedLLMClient(
        default_client=cast(Any, FakeClient("default")),
        provider_clients={"codex_subscription": cast(Any, FakeClient("codex"))},
    )
    client.complete(prompt="x", profile={"provider": "ollama"}, model="m")
    client.complete(prompt="x", profile={"provider": "codex_subscription"}, model="m")
    with pytest.raises(PipelineError, match="unsupported LLM provider"):
        client.complete(prompt="x", profile={"provider": 7}, model="m")
    assert calls == ["default", "codex"]


def test_subprocess_runner_uses_no_shell_and_kills_process_group_on_timeout() -> None:
    captured: dict[str, object] = {}
    communicate_calls: list[tuple[str | None, float | None]] = []
    killed: list[tuple[int, int]] = []

    class FakeProcess:
        pid = 321

        def communicate(self, input: str | None = None, timeout: float | None = None):
            communicate_calls.append((input, timeout))
            captured["communicate"] = list(communicate_calls)
            if len(communicate_calls) == 1:
                raise subprocess.TimeoutExpired(cmd=["codex"], timeout=timeout or 0)
            return ("", "stderr-secret")

    def fake_popen(argv: list[str], **kwargs: object) -> FakeProcess:
        captured["argv"] = argv
        captured["kwargs"] = kwargs
        return FakeProcess()

    runner = SubprocessCodexCommandRunner(
        popen_factory=fake_popen,
        killpg_func=lambda pid, sig: killed.append((pid, sig)),
    )

    result = runner.run(["codex", "exec"], cwd=Path("/tmp"), stdin_text="prompt", timeout_s=1)

    assert captured["argv"] == ["codex", "exec"]
    kwargs = cast(dict[str, object], captured["kwargs"])
    assert kwargs["shell"] is False
    assert kwargs["start_new_session"] is True
    assert result.timed_out is True
    assert killed == [(321, signal.SIGTERM)]
    assert communicate_calls == [("prompt", 1.0), (None, 5.0)]


def test_subprocess_runner_escalates_to_sigkill_after_timeout_grace() -> None:
    killed: list[tuple[int, int]] = []
    communicate_calls = 0

    class FakeProcess:
        pid = 321

        def communicate(self, input: str | None = None, timeout: float | None = None):
            nonlocal communicate_calls
            communicate_calls += 1
            if communicate_calls < 3:
                raise subprocess.TimeoutExpired(cmd=["codex"], timeout=timeout or 0)
            return ("", "")

    runner = SubprocessCodexCommandRunner(
        popen_factory=lambda *_args, **_kwargs: FakeProcess(),
        killpg_func=lambda pid, sig: killed.append((pid, sig)),
    )

    result = runner.run(["codex", "exec"], cwd=Path("/tmp"), timeout_s=1)

    assert result.timed_out is True
    assert killed == [(321, signal.SIGTERM), (321, signal.SIGKILL)]
