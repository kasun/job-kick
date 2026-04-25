from typing import Protocol

from job_kick.core.models import Job, SearchQuery, SourceName


class JobSource(Protocol):
    name: SourceName
    display_name: str

    def job_url(self, job_id: str) -> str: ...

    async def search(self, query: SearchQuery) -> list[Job]: ...

    async def fetch_job(self, job_id: str) -> Job: ...
