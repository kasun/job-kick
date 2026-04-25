from job_kick.core.models import SourceName
from job_kick.sources.base import JobSource
from job_kick.sources.linkedin.source import LinkedInSource


def get_source(name: SourceName) -> JobSource:
    match name:
        case SourceName.LINKEDIN:
            return LinkedInSource()
