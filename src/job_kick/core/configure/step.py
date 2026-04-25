from dataclasses import dataclass
from typing import Protocol

from job_kick.core.config import Credentials, JobqConfig


@dataclass
class StepStatus:
    configured: bool
    summary: str | None = None


class ConfigureStep(Protocol):
    name: str
    title: str

    def status(self, cfg: JobqConfig, creds: Credentials) -> StepStatus: ...

    def run(
        self, cfg: JobqConfig, creds: Credentials
    ) -> tuple[JobqConfig, Credentials]: ...
