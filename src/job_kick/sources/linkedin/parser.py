from datetime import datetime

from parsel import Selector

from job_kick.core.models import Company, Job, SourceName


def parse_public_search_page(html: str) -> list[Job]:
    selector = Selector(text=html)
    jobs: list[Job] = []

    for card in selector.css("li"):
        urn = card.css("[data-entity-urn]::attr(data-entity-urn)").get()
        job_id = urn.rsplit(":", 1)[-1]

        title = _clean(card.css(".base-search-card__title::text").get())
        company = _clean(
            card.css(".base-search-card__subtitle a::text").get()
        ) or _clean(card.css(".base-search-card__subtitle::text").get())
        company_url = card.css(".base-search-card__subtitle a::attr(href)").get()
        location = _clean(card.css(".job-search-card__location::text").get())
        url = card.css("a.base-card__full-link::attr(href)").get()
        posted_raw = card.css("time::attr(datetime)").get()

        if not (job_id and title and company and url):
            continue

        jobs.append(
            Job(
                id=job_id,
                source=SourceName.LINKEDIN,
                title=title,
                company=Company(name=company, url=company_url),
                url=url.split("?", 1)[0],
                location=location,
                posted_at=_parse_date(posted_raw),
            )
        )

    return jobs


def _clean(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    return cleaned or None


def _parse_date(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None
