import typer
from rich.console import Console

from job_kick.core.config import (
    load_config,
    load_credentials,
    save_config,
    save_credentials,
)
from job_kick.core.configure.step import ConfigureStep


class WizardRunner:
    def __init__(self, steps: list[ConfigureStep], *, console: Console) -> None:
        self._steps = steps
        self._console = console

    def run(self) -> None:
        cfg = load_config()
        creds = load_credentials()
        total = len(self._steps)

        for i, step in enumerate(self._steps, 1):
            self._console.print()
            self._console.rule(f"[bold]{i}/{total}  {step.title}[/bold]", align="left")
            status = step.status(cfg, creds)

            if status.configured:
                self._console.print(f"  [green]✔ Configured:[/green] {status.summary}")
                action = self._prompt("  [E]dit · [S]kip · [Q]uit", {"e", "s", "q"})
            else:
                self._console.print("  [yellow]✗ Not configured[/yellow]")
                action = self._prompt(
                    "  [C]onfigure · [S]kip · [Q]uit", {"c", "s", "q"}
                )

            if action == "q":
                self._console.print("[dim]Quit. Earlier steps preserved.[/dim]")
                return
            if action == "s":
                continue

            cfg, creds = step.run(cfg, creds)
            save_config(cfg)
            save_credentials(creds)
            self._console.print("  [green]✔ Saved.[/green]")

        self._console.print()
        self._console.print("[bold green]Done.[/bold green]")

    def _prompt(self, label: str, valid: set[str]) -> str:
        while True:
            raw = typer.prompt(label).strip().lower()
            if raw in valid:
                return raw
            self._console.print("  [red]Invalid choice.[/red]")
