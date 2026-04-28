from datetime import datetime, timedelta
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field, HttpUrl


class SourceName(StrEnum):
    LINKEDIN = "linkedin"


class JobType(StrEnum):
    FULL_TIME = "full_time"
    PART_TIME = "part_time"
    CONTRACT = "contract"
    TEMPORARY = "temporary"
    INTERNSHIP = "internship"
    VOLUNTEER = "volunteer"
    OTHER = "other"


class SearchQuery(BaseModel):
    keyword: str
    location: str | None = None
    limit: int = 25
    remote_only: bool = False
    job_types: list[JobType] = Field(default_factory=list)
    posted_within: timedelta | None = None


class Company(BaseModel):
    name: str
    url: HttpUrl | None = None


class Job(BaseModel):
    id: str
    source: SourceName
    title: str
    company: Company
    url: HttpUrl
    location: str | None = None
    description: str | None = None
    posted_at: datetime | None = None
    discovered_at: datetime = Field(default_factory=datetime.now)
    raw: dict[str, Any] = Field(default_factory=dict)
