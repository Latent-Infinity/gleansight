from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer
from pydantic import TypeAdapter

import papers.cli.app as cli_app
from papers.app.ideation_contracts import IdeateProjectRequest, LLMProfile, PlanIdeaRequest

app = typer.Typer(add_completion=False)

_PROFILE_KEYS = frozenset(
    {
        "api_key",
        "base_url",
        "chat_options",
        "executable_path",
        "profile_id",
        "provider",
        "reasoning_effort",
    }
)
_PROFILE_ADAPTER = TypeAdapter(LLMProfile)


def _profile(container: cli_app.CLIContainer, profile_id: str | None) -> LLMProfile:
    resolved_id = profile_id or container.settings.llm.default_profile
    profile = container.profile_store.get(resolved_id)
    if profile is None:
        cli_app.console.print(f"[red]Error:[/red] profile not found: {resolved_id}")
        raise typer.Exit(code=1)
    return _PROFILE_ADAPTER.validate_python(
        {key: value for key, value in profile.items() if key in _PROFILE_KEYS}
    )


@app.command("ideate-project")
def ideate_project(
    project_id: Annotated[str, typer.Argument(help="Project ID whose members are enumerated")],
    question: Annotated[str, typer.Argument(help="Project-wide ideation question")],
    profile_id: Annotated[str | None, typer.Option(help="Endpoint profile ID")] = None,
    model: Annotated[str | None, typer.Option(help="Generation model override")] = None,
    critic_model: Annotated[
        str | None, typer.Option(help="Independent critic model override")
    ] = None,
    max_papers: Annotated[int, typer.Option(min=1, help="Explicit project size bound")] = 12,
    excerpt_bytes: Annotated[int, typer.Option(min=200, help="Maximum bytes per excerpt")] = 1200,
    max_excerpts_per_paper: Annotated[
        int, typer.Option(min=1, max=12, help="Maximum section-aware excerpts per paper")
    ] = 6,
    timeout_s: Annotated[int, typer.Option(min=1, max=600, help="Per-call timeout seconds")] = 300,
    max_tokens: Annotated[int, typer.Option(min=256, help="Per-call output token bound")] = 8000,
) -> None:
    container = cli_app.get_container()
    try:
        bundle = container.ideate_project.run(
            IdeateProjectRequest(
                project_id=project_id,
                question=question,
                profile=_profile(container, profile_id),
                model=model or container.settings.llm.default_model,
                critic_model=critic_model,
                max_papers=max_papers,
                excerpt_bytes=excerpt_bytes,
                max_excerpts_per_paper=max_excerpts_per_paper,
                timeout_s=timeout_s,
                max_tokens=max_tokens,
            )
        )
    except typer.Exit:
        raise
    except Exception as exc:
        cli_app.console.print(f"[red]Error:[/red] {exc}")
        raise typer.Exit(code=1) from exc
    cli_app.console.print(f"Ideation bundle: {bundle}")


@app.command("plan-idea")
def plan_idea(
    bundle: Annotated[Path, typer.Argument(help="Verified project-ideation bundle")],
    idea_id: Annotated[str, typer.Argument(help="Explicit draft idea ID")],
    profile_id: Annotated[str | None, typer.Option(help="Endpoint profile ID")] = None,
    model: Annotated[str | None, typer.Option(help="Planning model override")] = None,
    timeout_s: Annotated[int, typer.Option(min=1, max=600, help="Call timeout seconds")] = 300,
    max_tokens: Annotated[int, typer.Option(min=256, help="Output token bound")] = 8000,
    selection_note: Annotated[
        str, typer.Option(help="Non-approval selection context recorded in provenance")
    ] = "operator-selected draft idea",
) -> None:
    container = cli_app.get_container()
    try:
        plan_bundle = container.plan_idea.run(
            PlanIdeaRequest(
                bundle=bundle,
                idea_id=idea_id,
                profile=_profile(container, profile_id),
                model=model or container.settings.llm.default_model,
                timeout_s=timeout_s,
                max_tokens=max_tokens,
                selection_note=selection_note,
            )
        )
    except typer.Exit:
        raise
    except Exception as exc:
        cli_app.console.print(f"[red]Error:[/red] {exc}")
        raise typer.Exit(code=1) from exc
    cli_app.console.print(f"Investigation plan bundle: {plan_bundle}")
