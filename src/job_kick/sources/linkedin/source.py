from job_kick.core.models import Job, SearchQuery, SourceName
from job_kick.sources.linkedin.client import LinkedInPublicClient
from job_kick.sources.linkedin.parser import (
    parse_job_posting,
    parse_public_search_page,
)


class LinkedInSource:
    name: SourceName = SourceName.LINKEDIN
    display_name: str = "LinkedIn"
    JOB_VIEW_URL = "https://www.linkedin.com/jobs/view/{job_id}"

    def job_url(self, job_id: str) -> str:
        return self.JOB_VIEW_URL.format(job_id=job_id)

    async def fetch_job(self, job_id: str) -> Job:
        async with LinkedInPublicClient() as client:
            html = await client.fetch_job_posting(job_id)
        return parse_job_posting(html, job_id, url=self.job_url(job_id))

    async def search(self, query: SearchQuery) -> list[Job]:
        results: list[Job] = []
        seen: set[str] = set()

        async with LinkedInPublicClient() as client:
            start = 0
            while len(results) < query.limit:
                html = await client.fetch_page(
                    keywords=query.keyword,
                    location=query.location,
                    start=start,
                    remote_only=query.remote_only,
                    job_types=query.job_types,
                )
                page = parse_public_search_page(html)
                if not page:
                    break

                new_this_page = 0
                for job in page:
                    if job.id in seen:
                        continue
                    seen.add(job.id)
                    results.append(job)
                    new_this_page += 1
                    if len(results) >= query.limit:
                        break

                if new_this_page == 0:
                    break
                start += len(page)

        return results
