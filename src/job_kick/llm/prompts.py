from job_kick.core.models import Job

Message = dict[str, str]


def summarize_job(job: Job) -> list[Message]:
    system = (
        "You are a concise job analyzer. Given a job posting, produce a tight "
        "summary in plain text with short sections covering: the role in one "
        "line, key responsibilities, must-have requirements, and any red flags "
        "or unclear points. Avoid filler and marketing language."
    )

    fields = [
        f"Title: {job.title}",
        f"Company: {job.company.name}",
    ]
    if job.location:
        fields.append(f"Location: {job.location}")
    fields.append("")
    fields.append("Description:")
    fields.append(job.description or "(no description available)")

    return [
        {"role": "system", "content": system},
        {"role": "user", "content": "\n".join(fields)},
    ]
