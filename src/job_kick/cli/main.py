import asyncio

import typer
from rich.console import Console
from rich.table import Table

from job_kick.core.models import Job, SearchQuery, SourceName
from job_kick.sources.registry import get_source

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

    _render_jobs(jobs, source_label=job_source.display_name)


def _render_jobs(jobs: list[Job], *, source_label: str) -> None:
    if not jobs:
        console.print(f"[yellow]No jobs found on {source_label}.[/yellow]")
        return

    table = Table(title=f"{source_label} — {len(jobs)} jobs", show_lines=False)
    table.add_column("Id", style="bold")
    table.add_column("Title", style="bold", overflow="fold")
    table.add_column("Company")
    table.add_column("Location")
    table.add_column("Posted")

    for id, job in enumerate(jobs, start=1):
        table.add_row(
            str(id),
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
