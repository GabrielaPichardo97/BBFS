# baby-first-steps-medallion

Implementación local y reproducible de una arquitectura medallón documental sobre
desarrollo temprano (0–36 meses). La recuperación final será exclusivamente en
español; el corpus puede incluir documentos en español e inglés.

Bronze descarga respuestas reales sin transformarlas. Silver las valida y
persiste de forma idempotente en DuckDB. Gold crea embeddings CPU y un índice
FAISS local a partir de recursos Silver reales; la búsqueda recibe consultas
exclusivamente en español.

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

## Gold y búsqueda semántica

Gold sólo lee `silver_resources` con `source_type='real'`. Usa
`intfloat/multilingual-e5-small` exclusivamente en CPU, conserva vectores
`float32` normalizados L2 y registra el nombre y la revisión efectiva del
modelo. El primer comando puede descargar el modelo público a la caché de
Hugging Face, que está fuera de Git.

```powershell
baby-first-steps gold
baby-first-steps search "actividades sensoriales con diferentes texturas para un bebé" --top-k 5
```

El texto de documento se forma sin traducción ni enriquecimiento como
`passage: <title>. <abstract>. Keywords: <keywords>. Subjects: <subject_terms>.`;
la consulta se codifica como `query: <consulta en español>`. El índice se escribe
de forma atómica en `data/gold/resources.faiss` y su estado, hash, IDs estables
y vectores se registran en DuckDB. Si el contenido y el modelo no cambian,
`gold` no vuelve a codificar ni reescribir el índice.

`gold` también genera
`artifacts/gold/acceptance-search.json` con seis consultas españolas, hasta cinco
resultados, score, título, idioma, fuentes, fragmento y una revisión manual de
coherencia pendiente. No contiene una métrica de relevancia inventada. El JSON
de `search` devuelve `rank`, identificador canónico, título, score, fragmento,
idioma, fecha, URL y fuentes observadas.

## Docker

Cuando Docker Compose esté disponible:

```powershell
docker compose config
docker compose build
docker compose run --rm pipeline doctor
```

El único servicio es `pipeline`, se ejecuta sin privilegios de root y persiste
`./data` en `/app/data`. La caché de Hugging Face usa un volumen independiente.
Para ejecutar Gold dentro del contenedor:

```powershell
docker compose run --rm pipeline gold
docker compose run --rm pipeline search "lectura compartida durante los primeros años de vida" --top-k 5
```

## Demostración y evidencia reproducible

El recorrido de aceptación no usa notebooks. El comando principal verifica el
entorno, elimina únicamente salidas generadas conocidas, adquiere dos batches
reales distintos de PubMed, Europe PMC y OpenAlex, procesa sólo el primero en
Silver/Gold y lo reprocesa sin volver a consultar las APIs. Después ejecuta
duplicados, seis consultas en español y las salvaguardas contra datos sintéticos.

```powershell
baby-first-steps demo --fresh
# Sin pregunta interactiva, por ejemplo para CI local:
baby-first-steps demo --fresh --yes
baby-first-steps evidence
```

`--fresh` sólo elimina `data/bronze`, `data/gold`, la DuckDB local, cachés/modelos
locales bajo `data/`, los artifacts de ejecución conocidos y
`docs/evidence.generated.md`. No elimina código, fixtures, `.gitkeep` ni otros
archivos del usuario. La confirmación es obligatoria salvo con `--yes`.

La ejecución genera los archivos ignorados por Git:

- `artifacts/evidence.json`, `artifacts/evidence.csv` y `artifacts/run.log`;
- `docs/evidence.generated.md`.

El JSON incluye tablas Bronze, contrato, idempotencia, SQL exacto de duplicados,
seis resultados de búsqueda y los cuatro conteos calculados de seguridad
sintética. `evidence` sólo vuelve a renderizar CSV, log y Markdown desde ese
JSON; no llama APIs. El script equivalente es
`python scripts/run_demo.py --fresh --yes`.

Los atajos disponibles son `make build`, `make test`, `make demo`,
`make evidence` y `make clean-generated`. En Docker se usan:

```powershell
docker compose run --rm pipeline demo --fresh --yes
docker compose run --rm pipeline evidence
```

## Datos y seguridad

- Bronze preserva bytes de respuesta sin transformarlos y calcula SHA-256 sobre
  esos bytes.
- Las transformaciones, cuarentena y deduplicación pertenecen a Silver.
- Datos reales, DuckDB, modelos, embeddings e índices se excluyen de Git.
- Los datos sintéticos sólo son válidos en `tests/fixtures/synthetic/` y las
  salvaguardas rechazan `source_type='synthetic'` en contextos productivos.
- Los resultados son recuperación documental: no son diagnóstico, tratamiento,
  prescripción médica ni recomendación de seguridad personalizada.

Consulte [docs/PRD.md](docs/PRD.md), [docs/architecture.md](docs/architecture.md)
y [docs/data-contract.md](docs/data-contract.md) para las decisiones completas.
