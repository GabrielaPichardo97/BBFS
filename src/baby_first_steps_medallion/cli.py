"""Command-line entry point for the scaffold."""

from __future__ import annotations

import importlib.util
import json
import sys
from dataclasses import dataclass
from typing import NoReturn

import typer

from baby_first_steps_medallion.bronze.service import (
    BronzeIngestor,
    BronzeUsageError,
    build_default_adapters,
)
from baby_first_steps_medallion.config import Settings
from baby_first_steps_medallion.gold.service import GoldError, GoldRepository
from baby_first_steps_medallion.logging import configure_logging
from baby_first_steps_medallion.paths import build_runtime_paths, ensure_writable
from baby_first_steps_medallion.silver.persistence import SilverPersistenceError, SilverRepository
from baby_first_steps_medallion.silver.service import SilverValidationError, SilverValidator

app = typer.Typer(
    add_completion=False,
    help="Pipeline local de baby-first-steps-medallion.",
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
def ingest(
    sources: str | None = typer.Option(
        None, help="Fuentes separadas por coma: pubmed,europe_pmc,openalex."
    ),
    profiles: str | None = typer.Option(
        None, help="Perfiles separados por coma; por defecto se usan los tres perfiles Bronze."
    ),
    max_records_per_source: int | None = typer.Option(
        None, min=1, help="Máximo total de registros por fuente; por defecto 20."
    ),
    resume: str | None = typer.Option(
        None, help="Batch ID Bronze incompleto que se debe reanudar."
    ),
) -> None:
    """Download real source responses into an immutable, resumable Bronze batch."""
    settings = Settings.from_env()
    adapters, client = build_default_adapters()
    try:
        manifest = BronzeIngestor(settings, adapters).ingest(
            sources=sources,
            profiles=profiles,
            max_records_per_source=max_records_per_source,
            resume=resume,
        )
    except BronzeUsageError as error:
        raise typer.BadParameter(str(error)) from error
    finally:
        client.close()
    typer.echo(
        "Bronze batch "
        f"{manifest['batch_id']}: {manifest['success_count']} respuestas, "
        f"{manifest['failure_count']} fallos, {manifest['total_bytes']} bytes."
    )
    if manifest["failure_count"]:
        raise typer.Exit(code=1)


@app.command("silver-validate")
def silver_validate(
    batch_id: str = typer.Option(..., help="Batch Bronze local para validar sin persistir Silver."),
) -> None:
    """Extract and validate one local Bronze batch without a Silver UPSERT."""
    settings = Settings.from_env()
    try:
        result = SilverValidator(settings).validate_batch(batch_id)
    except SilverValidationError as error:
        typer.echo(f"silver-validate: {error}", err=True)
        raise typer.Exit(code=2) from error
    typer.echo(json.dumps(result.metrics(), ensure_ascii=False, indent=2, sort_keys=True))


@app.command()
def silver(
    batch_id: str = typer.Option(
        ..., help="Batch Bronze local que se cargará de forma idempotente."
    ),
) -> None:
    """Validate and persist one local Bronze batch into transactional DuckDB Silver."""
    settings = Settings.from_env()
    try:
        validation = SilverValidator(settings).validate_batch(batch_id)
        persistence = SilverRepository(settings).persist(validation)
    except (SilverValidationError, SilverPersistenceError) as error:
        typer.echo(f"silver: {error}", err=True)
        raise typer.Exit(code=1) from error
    typer.echo(
        json.dumps(
            {"validation": validation.metrics(), "persistence": persistence.as_dict()},
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
    )


@app.command("audit-duplicates")
def audit_duplicates() -> None:
    """Fail if the persisted Silver tables contain duplicate or synthetic rows."""
    try:
        audit = SilverRepository(Settings.from_env()).audit_duplicates()
    except SilverPersistenceError as error:
        typer.echo(f"audit-duplicates: {error}", err=True)
        raise typer.Exit(code=1) from error
    typer.echo(json.dumps(audit.as_dict(), ensure_ascii=False, indent=2, sort_keys=True))


@app.command("show-runs")
def show_runs(limit: int = typer.Option(20, min=1, max=100)) -> None:
    """Show recent Silver pipeline runs without exposing raw source payloads."""
    try:
        runs = SilverRepository(Settings.from_env()).show_runs(limit=limit)
    except SilverPersistenceError as error:
        typer.echo(f"show-runs: {error}", err=True)
        raise typer.Exit(code=1) from error
    typer.echo(json.dumps(runs, ensure_ascii=False, indent=2, sort_keys=True, default=str))


@app.command()
def gold() -> None:
    """Build the incremental CPU FAISS index from real Silver resources."""
    repository = GoldRepository(Settings.from_env())
    try:
        build = repository.build()
        artifact_path = repository.write_acceptance_evidence()
    except GoldError as error:
        typer.echo(f"gold: {error}", err=True)
        raise typer.Exit(code=1) from error
    typer.echo(
        json.dumps(
            {"build": build.as_dict(), "acceptance_artifact_path": str(artifact_path)},
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
    )


@app.command()
def search(
    query: str = typer.Argument(..., help="Consulta de búsqueda semántica en español."),
    top_k: int = typer.Option(5, min=1, max=100, help="Máximo de resultados a devolver."),
) -> None:
    """Search the local multilingual Gold index with a Spanish user query."""
    try:
        results = GoldRepository(Settings.from_env()).semantic_search(query, top_k)
    except GoldError as error:
        typer.echo(f"search: {error}", err=True)
        raise typer.Exit(code=1) from error
    typer.echo(
        json.dumps(
            [result.as_dict() for result in results],
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
    )


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
