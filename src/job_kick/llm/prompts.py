from job_kick.core.models import Job

Message = dict[str, str]


def extract_search_query(prompt: str) -> list[Message]:
    system = (
        "You extract structured job-search parameters from a natural-language "
        "request. Respond with a single JSON object containing only these "
        "optional keys:\n"
        "- keyword (string): job title, role, or technology to search for\n"
        "- location (string): city, region, or country to filter by\n"
        "- limit (integer): max number of jobs to return\n"
        "- remote_only (boolean): true if the user only wants remote jobs\n"
        "- job_types (array of strings, subset of: full_time, part_time, "
        "contract, temporary, internship, volunteer, other): employment "
        "types the user wants\n"
        "Omit any field the user did not specify. Do not invent values. "
        "Return JSON only — no prose, no code fences."
    )
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": prompt},
    ]


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
