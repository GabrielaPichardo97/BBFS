# baby-first-steps-medallion

Scaffold local y reproducible para una arquitectura medallón documental sobre
desarrollo temprano (0–36 meses). La recuperación final será exclusivamente en
español; el corpus puede incluir documentos en español e inglés.

Este commit sólo contiene el scaffold: no descarga fuentes, no crea tablas ni
índices, y no simula éxito para los comandos de pipeline aún pendientes.

## Inicio local

Se requiere Python 3.11.

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.lock
python -m pip install --no-deps -e .
python -m baby_first_steps_medallion.cli doctor
pytest
```

Los comandos `ingest`, `silver`, `gold`, `search`, `evidence` y `demo` están
registrados deliberadamente como no implementados y salen con código 2.

## Docker

Cuando Docker Compose esté disponible:

```powershell
docker compose config
docker compose build
docker compose run --rm pipeline doctor
```

El único servicio es `pipeline`, se ejecuta sin privilegios de root y persiste
`./data` en `/app/data`. La caché de Hugging Face usa un volumen independiente.

## Datos y seguridad

- Bronze preservará bytes de respuesta sin transformarlos.
- Las transformaciones, cuarentena y deduplicación pertenecen a Silver.
- Datos reales, DuckDB, modelos, embeddings e índices se excluyen de Git.
- Los datos sintéticos sólo son válidos en `tests/fixtures/synthetic/` y las
  salvaguardas rechazan `source_type='synthetic'` en contextos productivos.

Consulte [docs/PRD.md](docs/PRD.md), [docs/architecture.md](docs/architecture.md)
y [docs/data-contract.md](docs/data-contract.md) para las decisiones completas.
