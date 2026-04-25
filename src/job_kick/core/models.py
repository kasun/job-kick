from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field, HttpUrl


class SourceName(StrEnum):
    LINKEDIN = "linkedin"


class SearchQuery(BaseModel):
    keyword: str
    location: str | None = None
    limit: int = 25
    remote_only: bool = False


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
