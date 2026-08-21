from __future__ import annotations

import importlib
import re
import shlex
from pathlib import Path

import typer
from click import Group
from typer.main import get_command

WORKFLOWS = Path("docs/workflows")
REQUIRED_WORKFLOWS = ("discovery.md", "analysis.md", "querying.md")
_COMMAND_RE = re.compile(r"(?:uv run python -m papers\.cli|papers)\s+([^\n`]+)")
_CONTINUATION_RE = re.compile(r"\\\n\s*")
_CODE_RE = re.compile(r"```(?:bash|sh|shell|zsh|console)?\n(.*?)```|`([^`\n]+)`", re.DOTALL)
_COMMAND_NAME_RE = re.compile(r"[a-z][a-z0-9-]*")


def _registered_command_names(app: typer.Typer) -> set[str]:
    names: set[str] = set()
    for command in app.registered_commands:
        if command.name:
            names.add(command.name)
    for group in app.registered_groups:
        names |= _registered_command_names(group.typer_instance)
    return names


def _commands_in_text(text: str) -> list[tuple[str, set[str]]]:
    commands: list[tuple[str, set[str]]] = []
    for fenced, inline in _CODE_RE.findall(text):
        code = _CONTINUATION_RE.sub(" ", fenced or inline)
        for arguments in _COMMAND_RE.findall(code):
            tokens = shlex.split(arguments)
            if not tokens or _COMMAND_NAME_RE.fullmatch(tokens[0]) is None:
                continue
            options = {token.split("=", 1)[0] for token in tokens[1:] if token.startswith("-")}
            commands.append((tokens[0], options))
    return commands


def _registered_options(app: typer.Typer) -> dict[str, set[str]]:
    command = get_command(app)
    assert isinstance(command, Group)
    return {
        name: {
            option
            for parameter in subcommand.params
            for option in (*parameter.opts, *parameter.secondary_opts)
        }
        for name, subcommand in command.commands.items()
    }


def test_workflow_docs_exist() -> None:
    missing = [name for name in REQUIRED_WORKFLOWS if not (WORKFLOWS / name).is_file()]
    assert missing == [], f"missing workflow docs: {missing}"


def test_documented_papers_commands_are_registered() -> None:
    cli_app = importlib.import_module("papers.cli.app")
    registered = _registered_command_names(cli_app.app)
    registered_options = _registered_options(cli_app.app)
    documented: list[tuple[str, set[str]]] = []
    for name in REQUIRED_WORKFLOWS:
        documented.extend(_commands_in_text((WORKFLOWS / name).read_text(encoding="utf-8")))
    unknown = sorted({command for command, _ in documented} - registered)
    assert documented, "workflow docs must include at least one papers CLI command"
    assert unknown == [], f"documented commands not registered: {unknown}"
    unknown_options = {
        command: sorted(options - registered_options[command])
        for command, options in documented
        if options - registered_options[command]
    }
    assert unknown_options == {}, f"documented options not registered: {unknown_options}"
