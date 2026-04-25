import typer

from job_kick.core.config import (
    Credentials,
    JobqConfig,
    LLMConfig,
    ProviderCredentials,
    get_api_key,
)
from job_kick.core.configure.step import StepStatus

PROVIDERS: list[str] = ["anthropic", "openai"]

MODELS_BY_PROVIDER: dict[str, list[str]] = {
    "anthropic": [
        "claude-opus-4-7",
        "claude-sonnet-4-6",
        "claude-haiku-4-5",
    ],
    "openai": [
        "gpt-4o",
        "gpt-4o-mini",
        "gpt-4-turbo",
    ],
}

CUSTOM_MODEL = "(custom…)"


class LLMProviderStep:
    name: str = "llm_provider"
    title: str = "LLM provider"

    def status(self, cfg: JobqConfig, creds: Credentials) -> StepStatus:
        if cfg.llm is None:
            return StepStatus(configured=False)
        resolved = get_api_key(cfg.llm.provider, creds)
        if resolved is None:
            return StepStatus(configured=False)
        api_key, source = resolved
        suffix = " [dim](from env)[/dim]" if source == "env" else ""
        return StepStatus(
            configured=True,
            summary=f"{cfg.llm.provider} / {cfg.llm.model} / {_mask(api_key)}{suffix}",
        )

    def run(
        self, cfg: JobqConfig, creds: Credentials
    ) -> tuple[JobqConfig, Credentials]:
        current = cfg.llm

        provider = _select(
            "Provider",
            PROVIDERS,
            default=current.provider if current else None,
        )

        known_models = MODELS_BY_PROVIDER[provider]
        models = known_models + [CUSTOM_MODEL]
        default_model = (
            current.model if current and current.model in known_models else None
        )
        choice = _select("Model", models, default=default_model)
        model = (
            typer.prompt("  Model name").strip() if choice == CUSTOM_MODEL else choice
        )

        existing = creds.providers.get(provider)
        if existing and existing.api_key:
            raw = typer.prompt(
                "  API key (Enter to keep current)",
                hide_input=True,
                default="",
                show_default=False,
            ).strip()
            api_key = raw or existing.api_key
        else:
            api_key = typer.prompt("  API key", hide_input=True).strip()

        new_cfg = cfg.model_copy(
            update={"llm": LLMConfig(provider=provider, model=model)}
        )
        new_providers = dict(creds.providers)
        new_providers[provider] = ProviderCredentials(api_key=api_key)
        new_creds = Credentials(providers=new_providers)
        return new_cfg, new_creds


def _mask(key: str) -> str:
    if len(key) <= 8:
        return "***"
    return f"{key[:6]}…{key[-4:]}"


def _select(prompt: str, choices: list[str], default: str | None = None) -> str:
    typer.echo(f"  {prompt}:")
    default_idx: int | None = None
    for i, c in enumerate(choices, 1):
        marker = ""
        if default == c:
            marker = " (current)"
            default_idx = i
        typer.echo(f"    {i}. {c}{marker}")
    while True:
        raw = typer.prompt(
            "  Select",
            default=str(default_idx) if default_idx else None,
            show_default=bool(default_idx),
        )
        try:
            idx = int(raw)
            if 1 <= idx <= len(choices):
                return choices[idx - 1]
        except ValueError:
            pass
        typer.echo(f"  Invalid. Enter 1-{len(choices)}.")
