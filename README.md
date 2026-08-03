# baby-first-steps-medallion

Implementación local y reproducible de una arquitectura medallón documental sobre
desarrollo temprano (0–36 meses). La recuperación final será exclusivamente en
español; el corpus puede incluir documentos en español e inglés.

Bronze descarga respuestas reales sin transformarlas y Silver las valida y
persiste de forma idempotente en DuckDB. Gold, búsqueda, evidencia y demo aún
no se implementan y no simulan éxito.

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

## Ingesta Bronze

El alias instalable es `baby-first-steps`. El siguiente comando conserva los
bytes originales de las respuestas de PubMed, Europe PMC y OpenAlex en un batch
ignorado por Git; no parsea documentos, no crea DuckDB y no descarga PDFs.

```powershell
baby-first-steps ingest --sources pubmed,europe_pmc,openalex --profiles motor_sensory --max-records-per-source 20
```

Cada batch incluye `manifest.json`, `checksums.sha256`, `failures.jsonl` y, por
fuente, pares de metadata de solicitud y payload original `.json` o `.xml`.
Puede reanudarse una ejecución incompleta sin sustituir un payload existente:

```powershell
baby-first-steps ingest --resume <batch_id>
```

Los comandos `gold`, `search`, `evidence` y `demo` siguen sin implementarse y
salen con código 2.

## Validación Silver temporal

La validación Silver lee exclusivamente un batch Bronze local, verifica los
SHA-256 y aplica el contrato Pydantic v2 en memoria. No descarga datos, no crea
DuckDB, no escribe una tabla Silver ni realiza UPSERT. El umbral inicial de
abstract es 80 caracteres.

```powershell
baby-first-steps silver-validate --batch-id <batch_id>
```

El comando informa conteos por fuente, registros válidos, cuarentenas reales,
errores de parseo y proporción de abstracts ausentes. Los fixtures sintéticos
no se aceptan en rutas Bronze productivas.

## Carga Silver en DuckDB

La carga Silver vuelve a validar el batch y persiste sólo registros reales en
`data/baby_first_steps.duckdb`. Ejecuta migraciones SQL versionadas, vacía
staging, deduplica por DOI o PMID, conserva procedencias y hace UPSERT
idempotente. Un error revierte Silver y deja el run con estado fallido.

```powershell
baby-first-steps silver --batch-id <batch_id>
baby-first-steps audit-duplicates
baby-first-steps show-runs
```

`audit-duplicates` falla si existen claves canónicas, cuarentenas o filas
`source_type='synthetic'` duplicadas/no permitidas. DuckDB se ignora en Git.

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

- Bronze preserva bytes de respuesta sin transformarlos y calcula SHA-256 sobre
  esos bytes.
- Las transformaciones, cuarentena y deduplicación pertenecen a Silver.
- Datos reales, DuckDB, modelos, embeddings e índices se excluyen de Git.
- Los datos sintéticos sólo son válidos en `tests/fixtures/synthetic/` y las
  salvaguardas rechazan `source_type='synthetic'` en contextos productivos.

Consulte [docs/PRD.md](docs/PRD.md), [docs/architecture.md](docs/architecture.md)
y [docs/data-contract.md](docs/data-contract.md) para las decisiones completas.
