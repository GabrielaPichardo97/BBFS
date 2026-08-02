# baby-first-steps-medallion

Implementación local y reproducible de una arquitectura medallón documental sobre
desarrollo temprano (0–36 meses). La recuperación final será exclusivamente en
español; el corpus puede incluir documentos en español e inglés.

Bronze ya descarga respuestas reales sin transformarlas. Silver, Gold, búsqueda,
evidencia y demo aún no se implementan y no simulan éxito.

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

Los comandos `silver`, `gold`, `search`, `evidence` y `demo` siguen sin
implementarse y salen con código 2.

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
