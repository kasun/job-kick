import asyncio
import json
import logging
import re
import sys
from datetime import timedelta

import click
import typer
from pydantic import BaseModel, ValidationError
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.progress import BarColumn, Progress, SpinnerColumn, TextColumn
from rich.table import Table

from job_kick.core.config import load_config, load_credentials, profile_file_path
from job_kick.core.profile import ensure_profile, load_profile
from job_kick.core.configure.registry import get_steps
from job_kick.core.configure.wizard import WizardRunner
from job_kick.core.errors import JobNotFoundError
from job_kick.core.guards import GuardError, llm_configured, uses_llm
from job_kick.core.models import Job, JobType, SearchQuery, SearchTemplate, SourceName
from job_kick.core.storage import Storage
from job_kick.llm import LLMClient
from job_kick.llm.prompts import (
    extract_search_query,
    match_job,
    score_job,
    summarize_job,
)
from job_kick.sources.registry import get_source
from job_kick.sources.base import JobSource

app = typer.Typer(no_args_is_help=True, add_completion=False)
bookmarks_app = typer.Typer(no_args_is_help=True, help="Manage bookmarked jobs.")
app.add_typer(bookmarks_app, name="bookmarks")
profile_app = typer.Typer(no_args_is_help=True, help="Manage your search profile.")
app.add_typer(profile_app, name="profile")
templates_app = typer.Typer(no_args_is_help=True, help="Manage saved search templates.")
app.add_typer(templates_app, name="templates")
console = Console()


def _configure_logging(*, verbose: bool) -> None:
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    )
    pkg_logger = logging.getLogger("job_kick")
    pkg_logger.handlers.clear()
    pkg_logger.addHandler(handler)
    pkg_logger.setLevel(logging.DEBUG if verbose else logging.WARNING)
    pkg_logger.propagate = False


@app.callback()
def _main_callback(
    verbose: bool = typer.Option(
        False, "--verbose", "-v", help="Enable debug logging to stderr."
    ),
) -> None:
    _configure_logging(verbose=verbose)


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
    since: str | None = typer.Option(
        None,
        "--since",
        help="Only jobs posted within this duration. e.g. 24h, 3d, 2w.",
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
    match: bool = typer.Option(
        False,
        "--match",
        help="Score each result against your profile (fetches descriptions; uses LLM).",
    ),
    template: str | None = typer.Option(
        None,
        "--template",
        help="Load saved search params from a template (CLI args still override).",
    ),
    save_template: str | None = typer.Option(
        None,
        "--save-template",
        help="Save the resolved search params under this template name.",
    ),
) -> None:
    """Search a job source."""
    posted_within: timedelta | None = _parse_duration(since) if since else None

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
        if posted_within is None and extracted.posted_within is not None:
            posted_within = _parse_duration(extracted.posted_within)

    if template is not None:
        tpl = _load_template(template)
        if source is None:
            source = tpl.source
        if keyword is None:
            keyword = tpl.keyword
        if location is None:
            location = tpl.location
        if limit is None:
            limit = tpl.limit
        if remote_only is None:
            remote_only = tpl.remote_only
        if not job_types:
            job_types = tpl.job_types
        if posted_within is None:
            posted_within = tpl.posted_within

    if not keyword:
        console.print(
            "[red]No search keyword provided.[/red] "
            "[dim]Pass --keyword/-k or --prompt/-p.[/dim]"
        )
        raise typer.Exit(code=1)

    resolved_source = _resolve_source(source)

    if save_template is not None:
        _save_search_template(
            name=save_template,
            source=resolved_source,
            keyword=keyword,
            location=location,
            limit=limit,
            remote_only=remote_only,
            job_types=job_types,
            posted_within=posted_within,
        )

    job_source = get_source(resolved_source)
    query = SearchQuery(
        keyword=keyword,
        location=location,
        limit=limit if limit is not None else 25,
        remote_only=bool(remote_only),
        job_types=job_types,
        posted_within=posted_within,
    )

    with console.status(f"Searching {job_source.display_name}…", spinner="dots"):
        jobs = asyncio.run(job_source.search(query))

    scores: dict[str, JobScore | None] | None = None
    if match and jobs:
        profile = _require_profile()
        cfg, creds = _ensure_llm()
        client = LLMClient.from_config(cfg, creds)
        scores = asyncio.run(_score_jobs(client, profile, job_source, jobs))
        jobs = sorted(
            jobs,
            key=lambda j: -(scores[j.id].score if scores.get(j.id) else -1),
        )

    if bookmark and jobs:
        with Storage() as store:
            saved = store.jobs.upsert_many(jobs)
        console.print(f"[dim]› Bookmarked {saved} job(s).[/dim]")

    _render_jobs(jobs, job_source=job_source, scores=scores)


def _load_template(name: str) -> SearchTemplate:
    with Storage() as store:
        tpl = store.templates.get(name)
    if tpl is None:
        console.print(f"[red]Template {name!r} not found.[/red]")
        raise typer.Exit(code=1)
    return tpl


def _save_search_template(
    *,
    name: str,
    source: SourceName,
    keyword: str,
    location: str | None,
    limit: int | None,
    remote_only: bool | None,
    job_types: list[JobType],
    posted_within: timedelta | None,
) -> None:
    with Storage() as store:
        existing = store.templates.get(name)
        if existing is not None and not typer.confirm(
            f"Template {name!r} exists. Overwrite?", default=False
        ):
            console.print("[dim]› Skipped saving template.[/dim]")
            return
        store.templates.upsert(
            SearchTemplate(
                name=name,
                source=source,
                keyword=keyword,
                location=location,
                limit=limit,
                remote_only=remote_only,
                job_types=job_types,
                posted_within=posted_within,
            )
        )
    console.print(f"[dim]› Saved template {name!r}.[/dim]")


class JobScore(BaseModel):
    score: int
    verdict: str


_SCORE_RE = re.compile(r"^\s*(\d+)\s*/\s*10\s*[—–-]\s*(.+?)\s*$")


def _parse_score(raw: str) -> JobScore | None:
    if not raw:
        return None
    line = raw.strip().splitlines()[0]
    m = _SCORE_RE.match(line)
    if not m:
        return None
    n = int(m.group(1))
    if not 0 <= n <= 10:
        return None
    return JobScore(score=n, verdict=m.group(2))


def _require_profile() -> str:
    path = profile_file_path()
    profile = load_profile(path)
    if profile is None or not profile.strip():
        console.print(
            f"[red]No profile found at {path}.[/red] "
            "[dim]Run `jobq profile edit` to create one.[/dim]"
        )
        raise typer.Exit(code=1)
    return profile


def _ensure_llm() -> tuple[object, object]:
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
    return cfg, creds


async def _score_jobs(
    client: LLMClient,
    profile: str,
    job_source: JobSource,
    jobs: list[Job],
) -> dict[str, JobScore | None]:
    sem = asyncio.Semaphore(5)
    results: dict[str, JobScore | None] = {}

    async def one(job: Job) -> tuple[str, JobScore | None]:
        async with sem:
            try:
                full = await job_source.fetch_job(job.id)
            except Exception:
                full = job
            try:
                raw = await client.complete(score_job(profile, full))
                return job.id, _parse_score(raw)
            except Exception:
                return job.id, None

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("{task.completed}/{task.total}"),
        console=console,
        transient=True,
    ) as progress:
        task_id = progress.add_task("Scoring matches", total=len(jobs))
        tasks = [asyncio.create_task(one(j)) for j in jobs]
        for done in asyncio.as_completed(tasks):
            jid, score = await done
            results[jid] = score
            progress.update(task_id, advance=1)

    return results


_DURATION_RE = re.compile(r"^(\d+)([hdw])$")


def _parse_duration(s: str) -> timedelta:
    m = _DURATION_RE.match(s.strip().lower())
    if not m:
        console.print(
            f"[red]Invalid duration {s!r}.[/red] "
            "[dim]Expected number + h/d/w, e.g. 24h, 3d, 2w.[/dim]"
        )
        raise typer.Exit(code=1)
    n, unit = int(m.group(1)), m.group(2)
    if unit == "h":
        return timedelta(hours=n)
    if unit == "d":
        return timedelta(days=n)
    return timedelta(weeks=n)


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
    posted_within: str | None = None


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


def _render_jobs(
    jobs: list[Job],
    *,
    job_source: JobSource,
    scores: dict[str, JobScore | None] | None = None,
) -> None:
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
    if scores is not None:
        table.add_column("Match", style="bold", overflow="fold")

    for id, job in enumerate(jobs, start=1):
        row = [
            str(id),
            job.id,
            f"[link={job.url}]{job.title}[/link]",
            job.company.name,
            job.location or "—",
            job.posted_at.strftime("%Y-%m-%d") if job.posted_at else "—",
        ]
        if scores is not None:
            row.append(_format_score(scores.get(job.id)))
        table.add_row(*row)

    console.print(table)


def _format_score(score: JobScore | None) -> str:
    if score is None:
        return "[dim]—[/dim]"
    if score.score >= 8:
        color = "green"
    elif score.score >= 5:
        color = "yellow"
    else:
        color = "red"
    return f"[{color}]{score.score}/10[/{color}]  [dim]{score.verdict}[/dim]"


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
@uses_llm
def match(
    job_id: str = typer.Argument(..., help="Source-specific job id."),
    source: SourceName | None = typer.Option(
        None,
        "--source",
        "-s",
        help="Job source the id belongs to. Falls back to the configured default.",
    ),
) -> None:
    """Match a job against your search profile."""
    cfg = load_config()
    creds = load_credentials()

    path = profile_file_path(cfg)
    profile = load_profile(path)
    if profile is None or not profile.strip():
        console.print(
            f"[red]No profile found at {path}.[/red] "
            "[dim]Run `jobq profile edit` to create one.[/dim]"
        )
        raise typer.Exit(code=1)

    client = LLMClient.from_config(cfg, creds)
    job_source = get_source(_resolve_source(source))

    try:
        with console.status(
            f"Fetching job {job_id} from {job_source.display_name}…", spinner="dots"
        ):
            job = asyncio.run(job_source.fetch_job(job_id))
    except JobNotFoundError as exc:
        console.print(f"[yellow]{exc}[/yellow]")
        raise typer.Exit(code=1) from None

    console.print(
        f"\n[bold cyan]Match — {job.title} @ {job.company.name}[/bold cyan]\n"
    )
    asyncio.run(_stream_match(client, profile, job))
    console.print()


async def _stream_match(client: LLMClient, profile: str, job: Job) -> None:
    async for chunk in client.stream(match_job(profile, job)):
        print(chunk, end="", flush=True)


@app.command()
def configure() -> None:
    """Walk through configuration steps."""
    WizardRunner(steps=get_steps(), console=console).run()


@profile_app.command("path")
def profile_path() -> None:
    """Print the absolute path to the profile file."""
    typer.echo(str(profile_file_path()))


@profile_app.command("show")
def profile_show() -> None:
    """Render the profile."""
    path = profile_file_path()
    content = load_profile(path)
    if content is None:
        console.print(
            f"[yellow]No profile yet at {path}.[/yellow] "
            "[dim]Run `jobq profile edit` to create one.[/dim]"
        )
        raise typer.Exit(code=1)
    console.print(Markdown(content))


@profile_app.command("edit")
def profile_edit() -> None:
    """Open the profile in $EDITOR (creates from template if missing)."""
    path = profile_file_path()
    if ensure_profile(path):
        console.print(f"[dim]› Created profile at {path}[/dim]")
    click.edit(filename=str(path))


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


@templates_app.command("list")
def templates_list() -> None:
    """List saved search templates."""
    with Storage() as store:
        templates = store.templates.all()

    if not templates:
        console.print("[yellow]No templates yet.[/yellow]")
        return

    templates = sorted(templates, key=lambda t: t.name)

    table = Table(title=f"Templates — {len(templates)}", show_lines=False)
    table.add_column("Name", style="bold")
    table.add_column("Source")
    table.add_column("Keyword", style="bold")
    table.add_column("Location")
    table.add_column("Filters")
    table.add_column("Created")

    for tpl in templates:
        table.add_row(
            tpl.name,
            tpl.source.value,
            tpl.keyword,
            tpl.location or "—",
            _format_template_filters(tpl) or "—",
            tpl.created_at.strftime("%Y-%m-%d"),
        )

    console.print(table)


def _format_template_filters(tpl: SearchTemplate) -> str:
    parts: list[str] = []
    if tpl.remote_only:
        parts.append("remote")
    if tpl.job_types:
        parts.append("/".join(t.value for t in tpl.job_types))
    if tpl.posted_within is not None:
        secs = int(tpl.posted_within.total_seconds())
        if secs % 604800 == 0:
            parts.append(f"since {secs // 604800}w")
        elif secs % 86400 == 0:
            parts.append(f"since {secs // 86400}d")
        else:
            parts.append(f"since {secs // 3600}h")
    if tpl.limit is not None:
        parts.append(f"limit {tpl.limit}")
    return ", ".join(parts)


@templates_app.command("remove")
def templates_remove(
    names: list[str] = typer.Argument(
        ..., help="One or more template names to remove."
    ),
) -> None:
    """Remove one or more saved templates by name."""
    removed = 0
    missing: list[str] = []
    with Storage() as store:
        for name in names:
            if store.templates.delete(name):
                removed += 1
            else:
                missing.append(name)

    if removed:
        console.print(f"[dim]› Removed {removed} template(s).[/dim]")
    if missing:
        console.print(f"[yellow]Not found: {', '.join(missing)}[/yellow]")
    if not removed:
        raise typer.Exit(code=1)


def main() -> None:
    app()


if __name__ == "__main__":
    main()
