from datetime import datetime

from inscriptis import get_text
from parsel import Selector

from job_kick.core.errors import JobNotFoundError
from job_kick.core.models import Company, Job, SourceName


def parse_job_posting(html: str, job_id: str, *, url: str) -> Job:
    selector = Selector(text=html)

    title = _clean(selector.css(".top-card-layout__title::text").get()) or _clean(
        selector.css(".topcard__title::text").get()
    )
    company_name = _clean(
        selector.css(".topcard__org-name-link::text").get()
    ) or _clean(selector.css(".topcard__flavor a::text").get())
    company_url = selector.css(".topcard__org-name-link::attr(href)").get()
    location = _clean(selector.css(".topcard__flavor--bullet::text").get())
    posted_raw = selector.css("time::attr(datetime)").get()
    description = _extract_description(selector)

    if not (title and company_name):
        raise JobNotFoundError(SourceName.LINKEDIN, job_id)

    return Job(
        id=job_id,
        source=SourceName.LINKEDIN,
        title=title,
        company=Company(name=company_name, url=company_url),
        url=url,
        location=location,
        description=description,
        posted_at=_parse_date(posted_raw),
    )


def _extract_description(selector: Selector) -> str | None:
    container = selector.css(".show-more-less-html__markup")
    if not container:
        container = selector.css(".description__text")
    if not container:
        return None
    html = container.get()
    if html is None:
        return None
    return _clean(get_text(html))


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
