from __future__ import annotations

import json
import os
import re
import signal
import subprocess
import tempfile
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from papers.app import ports
from papers.domain.errors import ErrorCode, PipelineError


@dataclass(frozen=True)
class CodexCommandResult:
    returncode: int
    stdout: str
    stderr: str
    timed_out: bool = False


class CodexCommandRunner(Protocol):
    def run(
        self,
        argv: list[str],
        *,
        cwd: Path,
        stdin_text: str | None = None,
        timeout_s: int | None = None,
    ) -> CodexCommandResult: ...


@dataclass(frozen=True)
class SubprocessCodexCommandRunner:
    popen_factory: Any = subprocess.Popen
    killpg_func: Any = os.killpg
    termination_grace_s: float = 5.0

    def run(
        self,
        argv: list[str],
        *,
        cwd: Path,
        stdin_text: str | None = None,
        timeout_s: int | None = None,
    ) -> CodexCommandResult:
        process = self.popen_factory(
            argv,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            cwd=str(cwd),
            shell=False,
            start_new_session=True,
        )
        try:
            stdout, stderr = process.communicate(input=stdin_text, timeout=_timeout(timeout_s))
            return CodexCommandResult(
                returncode=int(process.returncode),
                stdout=str(stdout or ""),
                stderr=str(stderr or ""),
            )
        except subprocess.TimeoutExpired:
            self.killpg_func(int(process.pid), signal.SIGTERM)
            try:
                stdout, stderr = process.communicate(timeout=self.termination_grace_s)
            except subprocess.TimeoutExpired:
                self.killpg_func(int(process.pid), signal.SIGKILL)
                stdout, stderr = process.communicate(timeout=self.termination_grace_s)
            return CodexCommandResult(
                returncode=-1,
                stdout=str(stdout or ""),
                stderr=str(stderr or ""),
                timed_out=True,
            )


@dataclass(frozen=True)
class CodexSubscriptionClient(ports.LLMClient):
    executable_path: str = "codex"
    default_reasoning_effort: str = "high"
    command_runner: CodexCommandRunner = field(default_factory=SubprocessCodexCommandRunner)
    temp_root: Path | None = None

    def complete(
        self,
        *,
        prompt: str,
        profile: dict[str, Any],
        model: str,
        timeout_s: int | None = None,
    ) -> ports.LLMResponse:
        executable = _profile_string(profile, "executable_path") or self.executable_path
        reasoning_effort = (
            _profile_string(profile, "reasoning_effort") or self.default_reasoning_effort
        )
        if not model.strip():
            raise PipelineError(ErrorCode.LLM_ERROR, "codex requested model is required")
        cli_version = self._preflight_version(executable, timeout_s=timeout_s)
        auth_mode = self._preflight_auth_mode(executable, timeout_s=timeout_s)
        schema_payload = _strict_output_schema(profile)
        with tempfile.TemporaryDirectory(
            dir=None if self.temp_root is None else str(self.temp_root)
        ) as temp_dir:
            cwd = Path(temp_dir)
            schema_path = cwd / "output-schema.json"
            output_path = cwd / "output-last-message.json"
            schema_path.write_text(_canonical_json(schema_payload), encoding="utf-8")
            result = self.command_runner.run(
                [
                    executable,
                    "exec",
                    "--json",
                    "--model",
                    model,
                    "--sandbox",
                    "read-only",
                    "--output-schema",
                    str(schema_path),
                    "--output-last-message",
                    str(output_path),
                    "--ephemeral",
                    "--ignore-user-config",
                    "--ignore-rules",
                    "--skip-git-repo-check",
                    "-c",
                    f"model_reasoning_effort={reasoning_effort}",
                    "-",
                ],
                cwd=cwd,
                stdin_text=prompt,
                timeout_s=timeout_s,
            )
            if result.timed_out:
                raise PipelineError(ErrorCode.LLM_TIMEOUT, "codex exec timed out")
            if result.returncode != 0:
                raise PipelineError(ErrorCode.LLM_ERROR, "codex exec failed")
            _validate_codex_jsonl(result.stdout)
            if not output_path.exists():
                raise PipelineError(ErrorCode.OUTPUT_PARSE_FAILED, "missing final agent message")
            output_text = output_path.read_text(encoding="utf-8").strip()
            if not output_text:
                raise PipelineError(ErrorCode.OUTPUT_PARSE_FAILED, "missing final agent message")
            payload = _validate_output_payload(output_text)
            return ports.LLMResponse(
                text=json.dumps(payload, separators=(",", ":"), ensure_ascii=False),
                tokens_in=None,
                tokens_out=None,
                cost_usd=None,
                response_metadata={
                    "provider": "codex_subscription",
                    "requested_model": model,
                    "codex_cli_version": cli_version,
                    "reasoning_effort": reasoning_effort,
                    "auth_mode": auth_mode,
                    "identity_source": "requested_and_reroute_checked",
                },
            )

    def _preflight_version(self, executable: str, *, timeout_s: int | None) -> str:
        with tempfile.TemporaryDirectory(
            dir=None if self.temp_root is None else str(self.temp_root)
        ) as temp_dir:
            result = self.command_runner.run(
                [executable, "--version"],
                cwd=Path(temp_dir),
                timeout_s=timeout_s,
            )
        if result.timed_out:
            raise PipelineError(ErrorCode.LLM_TIMEOUT, "codex --version timed out")
        if result.returncode != 0:
            raise PipelineError(ErrorCode.LLM_ERROR, "codex --version failed")
        match = re.search(r"(\d+\.\d+\.\d+)", result.stdout)
        if match is None:
            raise PipelineError(ErrorCode.OUTPUT_PARSE_FAILED, "codex version output is invalid")
        return match.group(1)

    def _preflight_auth_mode(self, executable: str, *, timeout_s: int | None) -> str:
        with tempfile.TemporaryDirectory(
            dir=None if self.temp_root is None else str(self.temp_root)
        ) as temp_dir:
            result = self.command_runner.run(
                [executable, "login", "status"],
                cwd=Path(temp_dir),
                timeout_s=timeout_s,
            )
        if result.timed_out:
            raise PipelineError(ErrorCode.LLM_TIMEOUT, "codex login status timed out")
        if result.returncode != 0:
            raise PipelineError(ErrorCode.LLM_ERROR, "codex login status failed")
        combined_output = f"{result.stdout}\n{result.stderr}"
        if "Logged in using ChatGPT" not in combined_output:
            raise PipelineError(ErrorCode.LLM_ERROR, "codex login status must use ChatGPT")
        return "chatgpt"


@dataclass(frozen=True)
class RoutedLLMClient(ports.LLMClient):
    default_client: ports.LLMClient
    provider_clients: Mapping[str, ports.LLMClient]
    default_providers: frozenset[str] = frozenset({"ollama", "frontier"})

    def complete(
        self,
        *,
        prompt: str,
        profile: dict[str, Any],
        model: str,
        timeout_s: int | None = None,
    ) -> ports.LLMResponse:
        provider = str(profile.get("provider") or "").strip()
        client = self.provider_clients.get(provider)
        if client is None:
            if provider not in self.default_providers:
                raise PipelineError(ErrorCode.LLM_ERROR, "unsupported LLM provider")
            client = self.default_client
        return client.complete(prompt=prompt, profile=profile, model=model, timeout_s=timeout_s)


def _timeout(timeout_s: int | None) -> float | None:
    if timeout_s is None:
        return None
    return float(timeout_s)


def _profile_string(profile: Mapping[str, Any], key: str) -> str:
    value = profile.get(key)
    if not isinstance(value, str):
        return ""
    return value.strip()


def _strict_output_schema(profile: Mapping[str, Any]) -> dict[str, object]:
    chat_options = profile.get("chat_options")
    if not isinstance(chat_options, Mapping):
        raise PipelineError(ErrorCode.LLM_ERROR, "codex response_format json_schema is required")
    response_format = chat_options.get("response_format")
    if not isinstance(response_format, Mapping) or response_format.get("type") != "json_schema":
        raise PipelineError(ErrorCode.LLM_ERROR, "codex response_format json_schema is required")
    json_schema = response_format.get("json_schema")
    if not isinstance(json_schema, Mapping):
        raise PipelineError(ErrorCode.LLM_ERROR, "codex response_format json_schema is required")
    name = json_schema.get("name")
    strict = json_schema.get("strict")
    schema = json_schema.get("schema")
    if (
        not isinstance(name, str)
        or not name.strip()
        or strict is not True
        or not isinstance(schema, Mapping)
    ):
        raise PipelineError(ErrorCode.LLM_ERROR, "codex response_format json_schema is required")
    return _mapping_to_dict(schema)


def _validate_codex_jsonl(stdout: str) -> None:
    saw_completed = False
    for raw_line in stdout.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError as exc:
            raise PipelineError(
                ErrorCode.OUTPUT_PARSE_FAILED, "codex emitted malformed jsonl"
            ) from exc
        if not isinstance(event, Mapping):
            raise PipelineError(ErrorCode.OUTPUT_PARSE_FAILED, "codex emitted malformed jsonl")
        event_dict = _mapping_to_dict(event)
        event_type = str(event_dict.get("type") or "").strip().lower()
        serialized = _canonical_json(event_dict).lower()
        if "reroute" in serialized:
            raise PipelineError(ErrorCode.OUTPUT_PARSE_FAILED, "codex reported a reroute event")
        if event_type == "error":
            raise PipelineError(ErrorCode.LLM_ERROR, "codex emitted an error event")
        if event_type == "turn.failed":
            raise PipelineError(ErrorCode.LLM_ERROR, "codex turn failed")
        if event_type == "turn.completed":
            saw_completed = True
    if not saw_completed:
        raise PipelineError(ErrorCode.OUTPUT_PARSE_FAILED, "codex output missing turn.completed")


def _validate_output_payload(output_text: str) -> dict[str, object]:
    try:
        payload = json.loads(output_text)
    except json.JSONDecodeError as exc:
        raise PipelineError(ErrorCode.OUTPUT_PARSE_FAILED, "invalid schema output") from exc
    if not isinstance(payload, Mapping):
        raise PipelineError(ErrorCode.OUTPUT_PARSE_FAILED, "invalid schema output")
    value = _mapping_to_dict(payload)
    expected_keys = {"pair_id", "label", "rationale"}
    missing_keys = expected_keys - set(value)
    extra_keys = set(value) - expected_keys
    if missing_keys:
        missing = sorted(missing_keys)[0]
        raise PipelineError(ErrorCode.OUTPUT_PARSE_FAILED, f"invalid schema output {missing}")
    if extra_keys:
        raise PipelineError(
            ErrorCode.OUTPUT_PARSE_FAILED, "invalid schema output contains extra keys"
        )
    pair_id = value.get("pair_id")
    label = value.get("label")
    rationale = value.get("rationale")
    if not isinstance(pair_id, str) or not pair_id.strip():
        raise PipelineError(ErrorCode.OUTPUT_PARSE_FAILED, "invalid schema output pair_id")
    if label not in {"near_duplicate", "novel", "ambiguous"}:
        raise PipelineError(ErrorCode.OUTPUT_PARSE_FAILED, "invalid schema output label")
    if not isinstance(rationale, str) or not rationale.strip():
        raise PipelineError(ErrorCode.OUTPUT_PARSE_FAILED, "invalid schema output rationale")
    return {
        "pair_id": pair_id.strip(),
        "label": str(label),
        "rationale": rationale.strip(),
    }


def _mapping_to_dict(value: Mapping[object, object]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, item in value.items():
        if isinstance(key, str):
            result[key] = item
    return result


def _canonical_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
