import asyncio

import httpx

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)


class LinkedInPublicClient:
    WORLDWIDE_LOCATION = "Worldwide"
    SEARCH_GEO_ID = "92000000"
    SEARCH_URL = (
        "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"
    )
    WORK_TYPE_REMOTE = "2"

    def __init__(
        self,
        *,
        timeout: float = 15.0,
        user_agent: str = DEFAULT_USER_AGENT,
        max_retries: int = 3,
    ) -> None:
        self._client = httpx.AsyncClient(
            timeout=timeout,
            headers={
                "User-Agent": user_agent,
                "Accept": "text/html,application/xhtml+xml",
                "Accept-Language": "en-US,en;q=0.9",
            },
            follow_redirects=True,
        )
        self._max_retries = max_retries

    async def __aenter__(self) -> "LinkedInPublicClient":
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        await self._client.aclose()

    async def fetch_page(
        self,
        *,
        keywords: str,
        location: str | None,
        start: int,
        remote_only: bool = False,
    ) -> str:
        params: dict[str, str | int] = {
            "keywords": keywords,
            "start": start,
            "trk": "public_jobs_jobs-search-bar_search-submit",
        }
        if location:
            params["location"] = location
        else:
            params["location"] = self.WORLDWIDE_LOCATION
        if remote_only:
            params["f_WT"] = self.WORK_TYPE_REMOTE

        backoff = 1.0
        for attempt in range(self._max_retries):
            response = await self._client.get(self.SEARCH_URL, params=params)
            print(response.url, response.status_code)
            if response.status_code == 200:
                return response.text
            if response.status_code in (429, 500, 502, 503, 504):
                if attempt == self._max_retries - 1:
                    response.raise_for_status()
                await asyncio.sleep(backoff)
                backoff *= 2
                continue
            response.raise_for_status()
        return ""
