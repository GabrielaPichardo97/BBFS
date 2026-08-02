"""Command-line entry point for the scaffold."""

from __future__ import annotations

import importlib.util
import sys
from dataclasses import dataclass
from typing import NoReturn

import typer

from baby_first_steps_medallion.config import Settings
from baby_first_steps_medallion.logging import configure_logging
from baby_first_steps_medallion.paths import build_runtime_paths, ensure_writable

app = typer.Typer(
    add_completion=False,
    help="Scaffold local de baby-first-steps-medallion; sin ingesta aún.",
    no_args_is_help=True,
)


@dataclass(frozen=True)
class DoctorCheck:
    name: str
    status: str
    detail: str


def _optional_library_check(module_name: str, label: str) -> DoctorCheck:
    if importlib.util.find_spec(module_name) is None:
        return DoctorCheck(label, "SKIP", "no instalado en este scaffold")
    try:
        __import__(module_name)
    except Exception as error:  # pragma: no cover - depends on optional local libraries
        return DoctorCheck(label, "FAIL", f"no se pudo importar: {error}")
    return DoctorCheck(label, "OK", "disponible")


def run_doctor(settings: Settings) -> list[DoctorCheck]:
    """Run only scaffold diagnostics; never contacts a remote source."""
    checks: list[DoctorCheck] = []
    python_ok = sys.version_info >= (3, 11)
    checks.append(
        DoctorCheck(
            "python",
            "OK" if python_ok else "FAIL",
            f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
        )
    )
    try:
        ensure_writable(build_runtime_paths(settings))
    except OSError as error:
        checks.append(DoctorCheck("rutas", "FAIL", str(error)))
    else:
        checks.append(DoctorCheck("rutas", "OK", str(settings.data_dir)))
    checks.append(DoctorCheck("configuracion", "OK", f"log_level={settings.log_level}"))
    checks.append(
        DoctorCheck(
            "secretos_obligatorios",
            "OK" if not settings.required_secret_names else "FAIL",
            (
                "ninguno requerido"
                if not settings.required_secret_names
                else ", ".join(settings.required_secret_names)
            ),
        )
    )
    checks.append(_optional_library_check("duckdb", "duckdb"))
    checks.append(_optional_library_check("faiss", "faiss"))
    return checks


def _unavailable(command: str) -> NoReturn:
    typer.echo(f"{command}: no implementado en este scaffold; no se realizó ninguna acción.")
    raise typer.Exit(code=2)


@app.command()
def doctor() -> None:
    """Verify local prerequisites without downloading data or models."""
    settings = Settings.from_env()
    configure_logging(settings.log_level)
    checks = run_doctor(settings)
    for check in checks:
        typer.echo(f"[{check.status}] {check.name}: {check.detail}")
    if any(check.status == "FAIL" for check in checks):
        raise typer.Exit(code=1)


@app.command()
def ingest() -> None:
    """Reserved for the future Bronze step."""
    _unavailable("ingest")


@app.command()
def silver() -> None:
    """Reserved for the future Silver step."""
    _unavailable("silver")


@app.command()
def gold() -> None:
    """Reserved for the future Gold step."""
    _unavailable("gold")


@app.command()
def search() -> None:
    """Reserved for the future Spanish semantic-search step."""
    _unavailable("search")


@app.command()
def evidence() -> None:
    """Reserved for future generated execution evidence."""
    _unavailable("evidence")


@app.command()
def demo() -> None:
    """Reserved for the future Spanish-only demonstration."""
    _unavailable("demo")


def main() -> None:
    """Run the Typer application."""
    app()


if __name__ == "__main__":
    main()
