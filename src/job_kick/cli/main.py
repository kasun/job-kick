import asyncio

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from job_kick.core.configure.registry import get_steps
from job_kick.core.configure.wizard import WizardRunner
from job_kick.core.errors import JobNotFoundError
from job_kick.core.models import Job, SearchQuery, SourceName
from job_kick.sources.registry import get_source
from job_kick.sources.base import JobSource

app = typer.Typer(no_args_is_help=True, add_completion=False)
console = Console()


@app.command()
def search(
    source: SourceName = typer.Argument(..., help="Job source to search."),
    keyword: str = typer.Option(..., "--keyword", "-k", help="Search keyword."),
    location: str | None = typer.Option(
        None, "--location", "-l", help="Location filter."
    ),
    limit: int = typer.Option(25, "--limit", help="Max number of jobs to return."),
    remote_only: bool = typer.Option(
        False, "--remote-only", help="Only include remote jobs."
    ),
) -> None:
    """Search a job source."""
    job_source = get_source(source)
    query = SearchQuery(
        keyword=keyword, location=location, limit=limit, remote_only=remote_only
    )

    with console.status(f"Searching {job_source.display_name}…", spinner="dots"):
        jobs = asyncio.run(job_source.search(query))

    _render_jobs(jobs, job_source=job_source)


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
    source: SourceName = typer.Argument(..., help="Job source the id belongs to."),
    job_id: str = typer.Argument(..., help="Source-specific job id."),
) -> None:
    """Print the public URL for a job."""
    job_source = get_source(source)
    typer.echo(job_source.job_url(job_id))


@app.command()
def describe(
    source: SourceName = typer.Argument(..., help="Job source the id belongs to."),
    job_id: str = typer.Argument(..., help="Source-specific job id."),
) -> None:
    """Show the full description for a job."""
    job_source = get_source(source)

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
def configure() -> None:
    """Walk through configuration steps."""
    WizardRunner(steps=get_steps(), console=console).run()


def main() -> None:
    app()


if __name__ == "__main__":
    main()
