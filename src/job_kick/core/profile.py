from pathlib import Path

STARTER_TEMPLATE = """\
# What I'm looking for
- (e.g. remote senior Python roles, EU timezones)
- Comp range, must-haves, deal-breakers, stack preferences
- Anything else: company size, industry, on-call tolerance, …

# About me (optional)
- Brief: years of experience, current role, location
- Anything that changes how a posting should be read against your wants
"""


def ensure_profile(path: Path) -> bool:
    if path.exists():
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(STARTER_TEMPLATE, encoding="utf-8")
    return True


def load_profile(path: Path) -> str | None:
    if not path.exists():
        return None
    return path.read_text(encoding="utf-8")
