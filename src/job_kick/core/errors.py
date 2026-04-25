class JobNotFoundError(Exception):
    def __init__(self, source: str, job_id: str) -> None:
        super().__init__(f"Job {job_id!r} not found on {source}.")
        self.source = source
        self.job_id = job_id
