# job-kick

[![PyPI](https://img.shields.io/pypi/v/job-kick.svg)](https://pypi.org/project/job-kick/)
[![Python](https://img.shields.io/pypi/pyversions/job-kick.svg)](https://pypi.org/project/job-kick/)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

> Terminal-first job-search assistant. Filter, save queries, and (optionally) rank with an LLM.

`job-kick` is a CLI for skimming 25 job postings without 25 browser tabs. Search, filter, and save queries from the terminal — bring an LLM key for ranking and per-job analysis.

<!-- TODO: replace with asciinema cast -->
```
$ jobq search --source linkedin -k python -l Germany --remote-only
                       LinkedIn — 12 jobs
┏━━━┳━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━┳━━━━━━━━━━┳━━━━━━━━━━━━┓
┃ # ┃ Job ID   ┃ Title            ┃ Company    ┃ Location ┃ Posted     ┃
┡━━━╇━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━╇━━━━━━━━━━╇━━━━━━━━━━━━┩
│ 1 │ 12345678 │ Senior Python    │ Acme       │ Remote   │ 2026-04-29 │
│ 2 │ 12345679 │ Backend Engineer │ Globex     │ Berlin   │ 2026-04-28 │
│ 3 │ 12345680 │ ML Engineer      │ Initech    │ Remote   │ 2026-04-27 │
└───┴──────────┴──────────────────┴────────────┴──────────┴────────────┘
```

## Why

Job search can be exhausting — too many sources, too many irrelevant postings. `job-kick` is a terminal-first job-search assistant: search a source, filter by keyword, location, recency, remote, and job type, and save queries for re-use. No login, no algorithm picking what you see.

Bring an LLM key (Anthropic or OpenAI) if you want the extras: natural-language queries, profile-based ranking, and per-job analysis. None of these are required to use the core.

## Install

```bash
pip install job-kick
# or: uv tool install job-kick

jobq configure
```

`jobq configure` walks through three steps: default source, LLM provider (Anthropic or OpenAI — bring your own API key), and search profile. The LLM features (`--prompt`, `--match`, `match`, `summarize`) need a key; everything else works without one.

## Quickstart

```bash
# search by keyword and filters
jobq search -k python -l Germany --remote-only --source linkedin

# save a query for re-use
jobq search -k python -l Germany --remote-only --save-template eu-python
jobq search --template eu-python

# bookmark interesting jobs (job ids come from the table)
jobq bookmarks add 12345678 --source linkedin
```

### With an LLM key (optional)

```bash
# natural-language search → structured filters
jobq search -p "remote python jobs in EU posted this week"

# rank every result against your profile
jobq search --template eu-python --match

# deep-read one job — summary, fit, red flags, interview questions
jobq match 12345678
```

## Commands

| Command | What it does |
| --- | --- |
| `jobq search` | Search a source. Filter by location, remote, job-type, posted-within. `-p/--prompt` for natural-language → structured filters. `--match` to rank results. `--bookmark` to persist. `--save-template` / `--template` to reuse queries. |
| `jobq match <id>` | Full LLM analysis: summary, why it fits, where it doesn't, red flags, interview questions. |
| `jobq summarize <id>` | Tight summary of a job description (skips the marketing fluff). |
| `jobq describe <id>` | Full job description, plain text. |
| `jobq url <id>` | Public URL for a job id. |
| `jobq bookmarks {add,list,remove,clear}` | Local job bookmarks. |
| `jobq templates {list,remove}` | Manage saved searches. |
| `jobq profile {edit,show,path}` | Free-form markdown profile used by `jobq search --match` and `jobq match`. |
| `jobq configure` | First-run / reconfigure wizard. |

Run `jobq <command> --help` for full options. `-v / --verbose` (before the subcommand) enables debug logging to stderr.

## Profile

Run `jobq profile edit` to open a markdown file in `$EDITOR`. Write what you're looking for in your own words — when you opt in to ranking with an LLM key, this file is the rubric:

```markdown
# What I'm looking for
- Remote senior Python roles, EU timezones
- Comp band €80-110k
- Small teams, no on-call

# About me
- 8 years backend, currently in Berlin
- Strong in Python/Postgres, light on AWS/k8s
```

Treat it as a journal, not a CV. The richer the intent, the better the scores.

## Privacy & data

- **Local-first.** No telemetry. The only network calls are to the source you configure (e.g. LinkedIn) and the LLM provider you configure.
- Everything lives under `~/.config/jobq/`:
  - `config.toml` — settings
  - `credentials.toml` — API keys (file mode `0600`)
  - `profile.md` — search profile
  - `data.json` — bookmarks and templates
- Delete the directory to start over.

## Architecture

- **Sources are pluggable.** LinkedIn (public job pages, no auth) is the only one in 0.1. Adding a source means implementing the `JobSource` protocol in [`src/job_kick/sources/base.py`](src/job_kick/sources/base.py).
- **LLM providers are pluggable via [LiteLLM](https://github.com/BerriAI/litellm).** Anthropic and OpenAI are first-class. Switching to a local Ollama, Bedrock, or anything else LiteLLM supports is a config change.
- **Storage is a single human-readable JSON file** (TinyDB). Inspect it, edit it, version-control it if you want.

## Status

`jobq` is **v0.1** — early. What works today:

- LinkedIn public-jobs search and job fetch (no login required).
- LLM-backed prompt parsing, single-job match analysis, batch match scoring, summarization.
- Local bookmarks, saved search templates, search profile.

What's coming:

- Authenticated LinkedIn (richer filters, fewer rate limits).
- Mark seen jobs.
- Scheduling, notifications.
- Additional sources, open an issue if you would like a specific source.

## Contributing

Issues and PRs welcome — small, scoped changes land faster.

## License

MIT — see [LICENSE](LICENSE).
