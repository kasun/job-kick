import typer

from job_kick.core.config import Credentials, JobqConfig
from job_kick.core.configure.step import StepStatus
from job_kick.core.models import SourceName


class DefaultSourceStep:
    name: str = "default_source"
    title: str = "Default job source"

    def status(self, cfg: JobqConfig, creds: Credentials) -> StepStatus:
        if cfg.default_source is None:
            return StepStatus(configured=False)
        return StepStatus(configured=True, summary=cfg.default_source.value)

    def run(
        self, cfg: JobqConfig, creds: Credentials
    ) -> tuple[JobqConfig, Credentials]:
        choices = [s.value for s in SourceName]
        current = cfg.default_source.value if cfg.default_source else None

        typer.echo("  Source:")
        default_idx: int | None = None
        for i, c in enumerate(choices, 1):
            marker = ""
            if current == c:
                marker = " (current)"
                default_idx = i
            typer.echo(f"    {i}. {c}{marker}")

        while True:
            raw = typer.prompt(
                "  Select",
                default=str(default_idx) if default_idx else None,
                show_default=bool(default_idx),
            )
            try:
                idx = int(raw)
                if 1 <= idx <= len(choices):
                    chosen = SourceName(choices[idx - 1])
                    break
            except ValueError:
                pass
            typer.echo(f"  Invalid. Enter 1-{len(choices)}.")

        new_cfg = cfg.model_copy(update={"default_source": chosen})
        return new_cfg, creds
