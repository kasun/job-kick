import click

from job_kick.core.config import Credentials, JobqConfig, profile_file_path
from job_kick.core.configure.step import StepStatus
from job_kick.core.profile import ensure_profile, load_profile


class ProfileStep:
    name: str = "profile"
    title: str = "Search profile"

    def status(self, cfg: JobqConfig, creds: Credentials) -> StepStatus:
        path = profile_file_path(cfg)
        content = load_profile(path)
        if content is None or not content.strip():
            return StepStatus(configured=False)
        word_count = len(content.split())
        return StepStatus(configured=True, summary=f"{path} ({word_count} words)")

    def run(
        self, cfg: JobqConfig, creds: Credentials
    ) -> tuple[JobqConfig, Credentials]:
        path = profile_file_path(cfg)
        if ensure_profile(path):
            click.echo(f"  Created profile at {path}")
        click.echo(f"  Opening {path} in your editor…")
        click.edit(filename=str(path))
        return cfg, creds
