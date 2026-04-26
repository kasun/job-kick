import functools
from typing import Callable

import typer
from rich.console import Console

from job_kick.core.config import (
    Credentials,
    JobqConfig,
    get_api_key,
    load_config,
    load_credentials,
)


class GuardError(Exception):
    def __init__(self, message: str, *, hint: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.hint = hint


Guard = Callable[[JobqConfig, Credentials], None]


def llm_configured(cfg: JobqConfig, creds: Credentials) -> None:
    if cfg.llm is None:
        raise GuardError(
            "No LLM configured.",
            hint="Run `jobq configure` to set up an LLM provider.",
        )
    if get_api_key(cfg.llm.provider, creds) is None:
        raise GuardError(
            f"No API key found for {cfg.llm.provider}.",
            hint=(
                f"Run `jobq configure` or set the "
                f"{cfg.llm.provider.upper()}_API_KEY env var."
            ),
        )


def _run_guards(
    cfg: JobqConfig, creds: Credentials, guards: tuple[Guard, ...]
) -> None:
    for guard in guards:
        try:
            guard(cfg, creds)
        except GuardError as exc:
            console = Console()
            console.print(f"[red]{exc.message}[/red]")
            if exc.hint:
                console.print(f"[dim]{exc.hint}[/dim]")
            raise typer.Exit(code=1) from None


def requires(*guards: Guard) -> Callable:
    def decorator(fn: Callable) -> Callable:
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            cfg = load_config()
            creds = load_credentials()
            _run_guards(cfg, creds, guards)
            return fn(*args, **kwargs)

        return wrapper

    return decorator


def uses_llm(fn: Callable) -> Callable:
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        cfg = load_config()
        creds = load_credentials()
        _run_guards(cfg, creds, (llm_configured,))
        assert cfg.llm is not None
        Console().print(
            f"[dim]› Using LLM: {cfg.llm.provider}/{cfg.llm.model}[/dim]"
        )
        return fn(*args, **kwargs)

    return wrapper
