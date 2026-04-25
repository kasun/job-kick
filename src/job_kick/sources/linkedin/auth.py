from pathlib import Path
from typing import Protocol

from pydantic import BaseModel


class Cookie(BaseModel):
    name: str
    value: str
    domain: str
    path: str = "/"


class LinkedInAuth(Protocol):
    async def cookies(self) -> list[Cookie]: ...


class CookieFileAuth:
    def __init__(self, path: Path) -> None:
        self._path = path

    async def cookies(self) -> list[Cookie]:
        raise NotImplementedError
