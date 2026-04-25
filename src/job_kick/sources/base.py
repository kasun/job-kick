from typing import Protocol

from job_kick.core.models import Job, SearchQuery, SourceName


class JobSource(Protocol):
    name: SourceName
    display_name: str

    async def search(self, query: SearchQuery) -> list[Job]: ...
