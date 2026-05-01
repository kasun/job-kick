from job_kick.core.models import Job, SourceName

Message = dict[str, str]


def extract_search_query(prompt: str) -> list[Message]:
    sources = ", ".join(s.value for s in SourceName)
    system = (
        "You extract structured job-search parameters from a natural-language "
        "request. Respond with a single JSON object containing only these "
        "optional keys:\n"
        f"- source (string, one of: {sources}): job source to search\n"
        "- keyword (string): job title, role, or technology to search for\n"
        "- location (string): city, region, or country to filter by\n"
        "- limit (integer): max number of jobs to return\n"
        "- remote_only (boolean): true if the user only wants remote jobs\n"
        "- job_types (array of strings, subset of: full_time, part_time, "
        "contract, temporary, internship, volunteer, other): employment "
        "types the user wants\n"
        "- posted_within (string, format: number + h/d/w, e.g. '24h', '3d', "
        "'2w'): only jobs posted within this duration\n"
        "Omit any field the user did not specify. Do not invent values. "
        "Return JSON only — no prose, no code fences."
    )
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": prompt},
    ]


def score_job(profile: str, job: Job) -> list[Message]:
    system = (
        'You score how well a job posting fits the user\'s "looking for" '
        "profile. Output EXACTLY ONE LINE in this format:\n"
        "\n"
        "N/10 — <verdict in 8 words or fewer>\n"
        "\n"
        "Score anchors: 1-4 poor fit, 5-6 fair, 7-8 strong, 9-10 exceptional. "
        "The verdict should name the dominant reason for the score (e.g. "
        "stack match, comp gap, on-site only, level mismatch). No preamble, "
        "no headings, no extra lines."
    )
    fields = [
        f"PROFILE:\n{profile.strip()}",
        "",
        "JOB POSTING:",
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


def match_job(profile: str, job: Job) -> list[Message]:
    system = (
        "You are a precise career analyst writing directly to the user. "
        'Given a job posting and their "looking for" profile, produce '
        "an analysis in the EXACT format below. Address the reader as "
        '"you" / "your" throughout — never refer to "the candidate" '
        "or use third person. No prose outside the sections. No markdown "
        "beyond what is shown.\n"
        "\n"
        "Match: N/10 — <verdict in 10 words or fewer>\n"
        "\n"
        "Summary\n"
        "<2-3 sentences capturing the role>\n"
        "\n"
        "Why it fits\n"
        '✓ <specific reason — e.g. "Remote, EU timezones — matches your profile">\n'
        "✓ <reason>\n"
        "\n"
        "Where it doesn't\n"
        '✗ <specific gap — e.g. "Heavy ML focus, but you prefer pure backend">\n'
        "✗ <gap>\n"
        '(if perfect fit, write "None — strong fit overall.")\n'
        "\n"
        "Red flags\n"
        "⚠ <concern about the posting itself, regardless of fit>\n"
        "⚠ <concern>\n"
        '(if none apparent, write "None apparent.")\n'
        "\n"
        "Open questions\n"
        "- <question YOU should ask in an interview, grounded in gaps above>\n"
        "- <question>\n"
        "\n"
        "Rules:\n"
        '- Address the user directly: "you", "your". Never "the '
        'candidate" or "they".\n'
        "- Cite specifics from the posting and profile, not generalities.\n"
        "- Distinguish mismatch (doesn't fit your wants) from red flag "
        "(concerning regardless).\n"
        "- Score anchors: 1-4 poor fit, 5-6 fair, 7-8 strong, "
        "9-10 exceptional.\n"
        "- Output only the sections above, in that order, with no extra "
        "headers or commentary."
    )

    fields = [
        f"PROFILE:\n{profile.strip()}",
        "",
        "JOB POSTING:",
        f"Title: {job.title}",
        f"Company: {job.company.name}",
    ]
    if job.location:
        fields.append(f"Location: {job.location}")
    fields.append(f"URL: {job.url}")
    fields.append("")
    fields.append("Description:")
    fields.append(job.description or "(no description available)")

    return [
        {"role": "system", "content": system},
        {"role": "user", "content": "\n".join(fields)},
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
