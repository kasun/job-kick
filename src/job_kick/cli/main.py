import asyncio
import json

import typer
from pydantic import BaseModel, ValidationError
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from job_kick.core.config import load_config, load_credentials
from job_kick.core.configure.registry import get_steps
from job_kick.core.configure.wizard import WizardRunner
from job_kick.core.errors import JobNotFoundError
from job_kick.core.guards import GuardError, llm_configured, uses_llm
from job_kick.core.models import Job, JobType, SearchQuery, SourceName
from job_kick.core.storage import Storage
from job_kick.llm import LLMClient
from job_kick.llm.prompts import extract_search_query, summarize_job
from job_kick.sources.registry import get_source
from job_kick.sources.base import JobSource

app = typer.Typer(no_args_is_help=True, add_completion=False)
bookmarks_app = typer.Typer(no_args_is_help=True, help="Manage bookmarked jobs.")
app.add_typer(bookmarks_app, name="bookmarks")
console = Console()


@app.command()
def search(
    source: SourceName | None = typer.Option(
        None,
        "--source",
        "-s",
        help="Job source to search. Falls back to the configured default.",
    ),
    keyword: str | None = typer.Option(None, "--keyword", "-k", help="Search keyword."),
    location: str | None = typer.Option(
        None, "--location", "-l", help="Location filter."
    ),
    limit: int | None = typer.Option(
        None, "--limit", help="Max number of jobs to return."
    ),
    remote_only: bool | None = typer.Option(
        None,
        "--remote-only/--no-remote-only",
        help="Only include remote jobs.",
    ),
    job_types: list[JobType] = typer.Option(
        [],
        "--job-type",
        "-j",
        help="Filter by job type. Repeatable: -j part_time -j contract.",
    ),
    prompt: str | None = typer.Option(
        None,
        "--prompt",
        "-p",
        help="Natural-language prompt; fills any arguments not explicitly provided.",
    ),
    bookmark: bool = typer.Option(
        False, "--bookmark", help="Persist results to the local job store."
    ),
) -> None:
    """Search a job source."""
    if prompt is not None:
        extracted = _extract_search_args(prompt)
        if source is None and extracted.source is not None:
            source = _coerce_extracted_source(extracted.source)
        if keyword is None:
            keyword = extracted.keyword
        if location is None:
            location = extracted.location
        if limit is None:
            limit = extracted.limit
        if remote_only is None:
            remote_only = extracted.remote_only
        if not job_types and extracted.job_types:
            job_types = extracted.job_types

    if not keyword:
        console.print(
            "[red]No search keyword provided.[/red] "
            "[dim]Pass --keyword/-k or --prompt/-p.[/dim]"
        )
        raise typer.Exit(code=1)

    job_source = get_source(_resolve_source(source))
    query = SearchQuery(
        keyword=keyword,
        location=location,
        limit=limit if limit is not None else 25,
        remote_only=bool(remote_only),
        job_types=job_types,
    )

    with console.status(f"Searching {job_source.display_name}…", spinner="dots"):
        jobs = asyncio.run(job_source.search(query))

    if bookmark and jobs:
        with Storage() as store:
            saved = store.jobs.upsert_many(jobs)
        console.print(f"[dim]› Bookmarked {saved} job(s).[/dim]")

    _render_jobs(jobs, job_source=job_source)


def _coerce_extracted_source(value: str) -> SourceName:
    try:
        return SourceName(value)
    except ValueError:
        available = ", ".join(s.value for s in SourceName)
        console.print(
            f"[red]LLM extracted source '{value}' which isn't supported.[/red] "
            f"[dim]Available: {available}. Pass --source/-s explicitly or rephrase.[/dim]"
        )
        raise typer.Exit(code=1) from None


def _resolve_source(passed: SourceName | None) -> SourceName:
    if passed is not None:
        return passed
    cfg = load_config()
    if cfg.default_source is not None:
        return cfg.default_source
    console.print(
        "[red]No source specified.[/red] "
        "[dim]Pass --source/-s or run `jobq configure` to set a default.[/dim]"
    )
    raise typer.Exit(code=1)


class _ExtractedSearchArgs(BaseModel):
    source: str | None = None
    keyword: str | None = None
    location: str | None = None
    limit: int | None = None
    remote_only: bool | None = None
    job_types: list[JobType] = []


def _extract_search_args(prompt: str) -> _ExtractedSearchArgs:
    cfg = load_config()
    creds = load_credentials()
    try:
        llm_configured(cfg, creds)
    except GuardError as exc:
        console.print(f"[red]{exc.message}[/red]")
        if exc.hint:
            console.print(f"[dim]{exc.hint}[/dim]")
        raise typer.Exit(code=1) from None

    assert cfg.llm is not None
    console.print(f"[dim]› Using LLM: {cfg.llm.provider}/{cfg.llm.model}[/dim]")

    client = LLMClient.from_config(cfg, creds)
    with console.status("Parsing prompt…", spinner="dots"):
        raw = asyncio.run(client.complete(extract_search_query(prompt)))

    return _parse_extracted_args(raw)


def _parse_extracted_args(raw: str) -> _ExtractedSearchArgs:
    text = raw.strip()
    if text.startswith("```"):
        lines = text.splitlines()[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines).strip()

    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        console.print("[red]LLM returned a non-JSON response.[/red]")
        raise typer.Exit(code=1) from None

    if not isinstance(data, dict):
        console.print("[red]LLM response was not a JSON object.[/red]")
        raise typer.Exit(code=1)

    try:
        return _ExtractedSearchArgs.model_validate(data)
    except ValidationError as exc:
        console.print(f"[red]LLM response failed validation:[/red]\n{exc}")
        raise typer.Exit(code=1) from None


def _render_jobs(jobs: list[Job], *, job_source: JobSource) -> None:
    if not jobs:
        console.print(f"[yellow]No jobs found on {job_source.display_name}.[/yellow]")
        return

    table = Table(
        title=f"{job_source.display_name} — {len(jobs)} jobs", show_lines=False
    )
    table.add_column("Id", style="bold")
    table.add_column(f"{job_source.display_name} Job ID", style="bold")
    table.add_column("Title", style="bold", overflow="fold")
    table.add_column("Company")
    table.add_column("Location")
    table.add_column("Posted")

    for id, job in enumerate(jobs, start=1):
        table.add_row(
            str(id),
            job.id,
            f"[link={job.url}]{job.title}[/link]",
            job.company.name,
            job.location or "—",
            job.posted_at.strftime("%Y-%m-%d") if job.posted_at else "—",
        )

    console.print(table)


@app.command()
def url(
    job_id: str = typer.Argument(..., help="Source-specific job id."),
    source: SourceName | None = typer.Option(
        None,
        "--source",
        "-s",
        help="Job source the id belongs to. Falls back to the configured default.",
    ),
) -> None:
    """Print the public URL for a job."""
    job_source = get_source(_resolve_source(source))
    typer.echo(job_source.job_url(job_id))


@app.command()
def describe(
    job_id: str = typer.Argument(..., help="Source-specific job id."),
    source: SourceName | None = typer.Option(
        None,
        "--source",
        "-s",
        help="Job source the id belongs to. Falls back to the configured default.",
    ),
) -> None:
    """Show the full description for a job."""
    job_source = get_source(_resolve_source(source))

    try:
        with console.status(
            f"Fetching job {job_id} from {job_source.display_name}…", spinner="dots"
        ):
            job = asyncio.run(job_source.fetch_job(job_id))
    except JobNotFoundError as exc:
        console.print(f"[yellow]{exc}[/yellow]")
        raise typer.Exit(code=1) from None

    _render_job(job, job_source=job_source)


def _render_job(job: Job, *, job_source: JobSource) -> None:
    header_lines = [
        f"[bold]{job.title}[/bold]",
        f"{job.company.name} · {job.location or '—'}",
    ]
    if job.posted_at:
        header_lines.append(f"Posted {job.posted_at.strftime('%Y-%m-%d')}")
    header_lines.append(f"[link={job.url}]{job.url}[/link]")

    body = job.description or "[dim](No description available.)[/dim]"

    console.print(
        Panel(
            "\n".join(header_lines) + "\n\n" + body,
            title=job_source.display_name,
            border_style="cyan",
        )
    )


@app.command()
@uses_llm
def summarize(
    job_id: str = typer.Argument(..., help="Source-specific job id."),
    source: SourceName | None = typer.Option(
        None,
        "--source",
        "-s",
        help="Job source the id belongs to. Falls back to the configured default.",
    ),
) -> None:
    """Summarize a job description using the configured LLM."""
    client = LLMClient.from_config(load_config(), load_credentials())
    job_source = get_source(_resolve_source(source))

    try:
        with console.status(
            f"Fetching job {job_id} from {job_source.display_name}…", spinner="dots"
        ):
            job = asyncio.run(job_source.fetch_job(job_id))
    except JobNotFoundError as exc:
        console.print(f"[yellow]{exc}[/yellow]")
        raise typer.Exit(code=1) from None

    console.print(f"\n[bold cyan]Summary — {job.title}[/bold cyan]\n")
    asyncio.run(_stream_summary(client, job))
    console.print()


async def _stream_summary(client: LLMClient, job: Job) -> None:
    async for chunk in client.stream(summarize_job(job)):
        print(chunk, end="", flush=True)


@app.command()
def configure() -> None:
    """Walk through configuration steps."""
    WizardRunner(steps=get_steps(), console=console).run()


@bookmarks_app.command("add")
def bookmarks_add(
    job_ids: list[str] = typer.Argument(
        ..., help="One or more source-specific job ids to bookmark."
    ),
    source: SourceName | None = typer.Option(
        None,
        "--source",
        "-s",
        help="Job source the ids belong to. Falls back to the configured default.",
    ),
) -> None:
    """Bookmark one or more jobs by job id."""
    job_source = get_source(_resolve_source(source))

    with console.status(
        f"Fetching {len(job_ids)} job(s) from {job_source.display_name}…",
        spinner="dots",
    ):
        results = asyncio.run(_fetch_many(job_source, job_ids))

    saved = 0
    missing: list[str] = []
    failed: list[tuple[str, str]] = []
    with Storage() as store:
        for job_id, outcome in zip(job_ids, results):
            if isinstance(outcome, JobNotFoundError):
                missing.append(job_id)
            elif isinstance(outcome, Exception):
                failed.append((job_id, str(outcome)))
            else:
                store.jobs.upsert(outcome)
                saved += 1

    if saved:
        console.print(f"[dim]› Bookmarked {saved} job(s).[/dim]")
    if missing:
        console.print(f"[yellow]Not found: {', '.join(missing)}[/yellow]")
    for jid, err in failed:
        console.print(f"[red]Failed {jid}:[/red] {err}")
    if not saved:
        raise typer.Exit(code=1)


async def _fetch_many(
    job_source: JobSource, job_ids: list[str]
) -> list[Job | BaseException]:
    return await asyncio.gather(
        *(job_source.fetch_job(jid) for jid in job_ids),
        return_exceptions=True,
    )


@bookmarks_app.command("remove")
def bookmarks_remove(
    source: SourceName = typer.Argument(..., help="Job source the ids belong to."),
    job_ids: list[str] = typer.Argument(
        ..., help="One or more source-specific job ids to remove."
    ),
) -> None:
    """Remove one or more bookmarks by job id."""
    removed = 0
    missing: list[str] = []
    with Storage() as store:
        for job_id in job_ids:
            if store.jobs.delete(source, job_id):
                removed += 1
            else:
                missing.append(job_id)

    if removed:
        console.print(f"[dim]› Removed {removed} bookmark(s).[/dim]")
    if missing:
        console.print(f"[yellow]Not bookmarked: {', '.join(missing)}[/yellow]")
    if not removed:
        raise typer.Exit(code=1)


@bookmarks_app.command("clear")
def bookmarks_clear(
    source: SourceName | None = typer.Option(
        None, "--source", "-s", help="Only clear bookmarks from this source."
    ),
    yes: bool = typer.Option(
        False, "--yes", "-y", help="Skip the confirmation prompt."
    ),
) -> None:
    """Remove all bookmarks (optionally scoped to a single source)."""
    scope = f"all bookmarks from {source.value}" if source else "all bookmarks"
    if not yes and not typer.confirm(f"Remove {scope}?", default=False):
        raise typer.Exit(code=1)

    with Storage() as store:
        removed = store.jobs.clear(source)

    console.print(f"[dim]› Removed {removed} bookmark(s).[/dim]")


@bookmarks_app.command("list")
def bookmarks_list() -> None:
    """List bookmarked jobs."""
    with Storage() as store:
        jobs = store.jobs.all()

    if not jobs:
        console.print("[yellow]No bookmarks yet.[/yellow]")
        return

    table = Table(title=f"Bookmarks — {len(jobs)} jobs", show_lines=False)
    table.add_column("Id", style="bold")
    table.add_column("Source", style="bold")
    table.add_column("Job ID", style="bold")
    table.add_column("Title", style="bold", overflow="fold")
    table.add_column("Company")
    table.add_column("Location")
    table.add_column("Posted")

    for idx, job in enumerate(jobs, start=1):
        table.add_row(
            str(idx),
            job.source.value,
            job.id,
            f"[link={job.url}]{job.title}[/link]",
            job.company.name,
            job.location or "—",
            job.posted_at.strftime("%Y-%m-%d") if job.posted_at else "—",
        )

    console.print(table)


def main() -> None:
    app()


if __name__ == "__main__":
    main()
