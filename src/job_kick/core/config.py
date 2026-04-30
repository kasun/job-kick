import os
import stat
import tomllib
from pathlib import Path

import tomli_w
from pydantic import BaseModel

from job_kick.core.models import SourceName


class LLMConfig(BaseModel):
    provider: str
    model: str


class JobqConfig(BaseModel):
    llm: LLMConfig | None = None
    default_source: SourceName | None = None
    profile_path: Path | None = None


class ProviderCredentials(BaseModel):
    api_key: str


class Credentials(BaseModel):
    providers: dict[str, ProviderCredentials] = {}


PROVIDER_ENV_VARS: dict[str, str] = {
    "anthropic": "ANTHROPIC_API_KEY",
    "openai": "OPENAI_API_KEY",
}


def config_dir() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base) / "jobq"


def config_path() -> Path:
    return config_dir() / "config.toml"


def credentials_path() -> Path:
    return config_dir() / "credentials.toml"


def profile_file_path(cfg: "JobqConfig | None" = None) -> Path:
    if cfg is None:
        cfg = load_config()
    return cfg.profile_path or (config_dir() / "profile.md")


def load_config() -> JobqConfig:
    path = config_path()
    if not path.exists():
        return JobqConfig()
    with open(path, "rb") as f:
        return JobqConfig.model_validate(tomllib.load(f))


def save_config(cfg: JobqConfig) -> None:
    _atomic_write_toml(config_path(), cfg.model_dump(mode="json", exclude_none=True))


def load_credentials() -> Credentials:
    path = credentials_path()
    if not path.exists():
        return Credentials()
    with open(path, "rb") as f:
        return Credentials.model_validate(tomllib.load(f))


def save_credentials(creds: Credentials) -> None:
    path = credentials_path()
    _atomic_write_toml(path, creds.model_dump(exclude_none=True))
    try:
        os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)
    except OSError:
        pass


def get_api_key(
    provider: str, creds: Credentials | None = None
) -> tuple[str, str] | None:
    env_name = PROVIDER_ENV_VARS.get(provider)
    if env_name and (val := os.environ.get(env_name)):
        return val, "env"
    creds = creds if creds is not None else load_credentials()
    pc = creds.providers.get(provider)
    if pc and pc.api_key:
        return pc.api_key, "file"
    return None


def _atomic_write_toml(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "wb") as f:
        tomli_w.dump(data, f)
    os.replace(tmp, path)
