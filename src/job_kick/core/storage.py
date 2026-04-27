from collections.abc import Iterable
from pathlib import Path
from types import TracebackType

from tinydb import Query, TinyDB

from job_kick.core.config import config_dir
from job_kick.core.models import Job, SourceName


def data_path() -> Path:
    return config_dir() / "data.json"


class JobsTable:
    TABLE = "jobs"

    def __init__(self, db: TinyDB) -> None:
        self._table = db.table(self.TABLE)

    def upsert(self, job: Job) -> None:
        q = Query()
        self._table.upsert(
            job.model_dump(mode="json"),
            (q.source == job.source.value) & (q.id == job.id),
        )

    def upsert_many(self, jobs: Iterable[Job]) -> int:
        count = 0
        for job in jobs:
            self.upsert(job)
            count += 1
        return count

    def get(self, source: SourceName, job_id: str) -> Job | None:
        q = Query()
        doc = self._table.get((q.source == source.value) & (q.id == job_id))
        return Job.model_validate(doc) if doc else None

    def all(self) -> list[Job]:
        return [Job.model_validate(d) for d in self._table.all()]

    def find_by_source(self, source: SourceName) -> list[Job]:
        q = Query()
        return [
            Job.model_validate(d) for d in self._table.search(q.source == source.value)
        ]

    def delete(self, source: SourceName, job_id: str) -> bool:
        q = Query()
        removed = self._table.remove((q.source == source.value) & (q.id == job_id))
        return bool(removed)

    def clear(self, source: SourceName | None = None) -> int:
        if source is None:
            count = len(self._table)
            self._table.truncate()
            return count
        q = Query()
        removed = self._table.remove(q.source == source.value)
        return len(removed)


class Storage:
    def __init__(self, path: Path | None = None) -> None:
        resolved = path or data_path()
        resolved.parent.mkdir(parents=True, exist_ok=True)
        self._db = TinyDB(resolved, indent=2, ensure_ascii=False)
        self.jobs = JobsTable(self._db)

    def close(self) -> None:
        self._db.close()

    def __enter__(self) -> "Storage":
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.close()
