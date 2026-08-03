# Guía de ejecución

## Requisitos

- Git y un checkout de `BBFS`.
- Python 3.11 para ejecución local.
- Docker Desktop o Docker Engine con Compose v2 para la ruta recomendada.
- Espacio local para la imagen CPU, la caché de Hugging Face y los datos
  generados. Ninguno de esos elementos se versiona.

No se requiere API key, tarjeta, cuenta de nube ni GPU.

## Instalación local reproducible

En PowerShell:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --requirement requirements.lock
python -m pip install --no-deps --no-build-isolation --editable .
baby-first-steps doctor
```

La primera instalación descarga dependencias CPU fijadas. La primera ejecución
Gold descarga `intfloat/multilingual-e5-small` en `data/cache/` salvo que
`HF_HOME` apunte a otra ruta ignorada.

## Ejecución por capas

```powershell
baby-first-steps ingest --sources pubmed,europe_pmc,openalex --profiles motor_sensory --max-records-per-source 5
baby-first-steps silver-validate --batch-id <batch_id>
baby-first-steps silver --batch-id <batch_id>
baby-first-steps audit-duplicates
baby-first-steps gold
baby-first-steps search "lectura compartida para estimular el lenguaje" --top-k 5
```

`silver-validate`, `silver`, `gold` y `search` trabajan con estado local. Sólo
`ingest` y la primera mitad de `demo` llaman fuentes públicas.

## Demostración completa

La ruta principal solicita confirmación antes de retirar salidas generadas:

```powershell
baby-first-steps demo --fresh
```

Para CI local o Docker:

```powershell
baby-first-steps demo --fresh --yes
docker compose run --rm pipeline demo --fresh --yes
docker compose run --rm pipeline evidence
```

`--fresh` sólo afecta las rutas generadas enumeradas en el código: Bronze,
Gold, DuckDB, caché/modelos bajo `data/`, artifacts conocidos y
`docs/evidence.generated.md`. No elimina fixtures, código, `.gitkeep` ni otros
archivos del usuario.

## Docker

```powershell
docker compose config
docker compose build
docker compose run --rm pipeline doctor
docker compose run --rm pipeline search "música y movimiento para el desarrollo infantil" --top-k 5
```

El servicio `pipeline` se ejecuta como UID 10001. `./data`, `./artifacts` y
`./docs` se montan para conservar salidas; `hf-cache` es un volumen separado.
En Linux, esos directorios deben permitir escritura al usuario del contenedor o
se debe ejecutar con el UID/GID del usuario anfitrión, como hace el workflow
live.

## CI rápida local

Los siguientes comandos reproducen los pasos principales de `.github/workflows/ci.yml`:

```powershell
python scripts/check_repository_hygiene.py --root . --mode publishable
python -m ruff check src tests scripts/check_repository_hygiene.py
python -m mypy src
python -m coverage run --source=baby_first_steps_medallion -m pytest tests/unit
python -m coverage report --show-missing
pytest tests/integration -m integration
docker compose config
docker compose build
docker compose run --rm pipeline doctor
```

Las pruebas de integración parchean `socket.connect` para fallar ante cualquier
intento de red. En GitHub también se ejecutan dentro de un contenedor con
`--network none`.

## GitHub Actions

### CI

`ci.yml` se activa en pull requests y pushes a `main`. Ejecuta calidad, tipos,
unit tests, cobertura, Compose, build, doctor, integración offline y el escaneo
de higiene. No contiene `ingest`, `demo` ni endpoints de las fuentes.

### E2E live

`e2e-live.yml` se activa sólo mediante `workflow_dispatch` o el cron semanal.
Tiene permisos `contents: read`, timeout de 45 minutos, concurrencia única y no
declara secretos. Usa una caché persistente del modelo y ejecuta
`demo --fresh --yes`.

El artifact tiene retención de 14 días y una allowlist explícita:

- evidencia JSON/CSV/Markdown y `run.log`;
- `manifest.json` y `checksums.sha256` de cada batch.

No se incluyen `response_*.json`, `response_*.xml`, PDFs, DuckDB, modelos ni
FAISS. La matriz calculada se copia al GitHub Job Summary.

## Inspección y limpieza

```powershell
baby-first-steps evidence
baby-first-steps show-runs
baby-first-steps audit-duplicates
baby-first-steps clean-generated
```

La limpieza es destructiva únicamente para salidas regenerables y solicita
confirmación salvo con `--yes`. Los archivos retirados no se envían a una
papelera; se pueden recuperar volviendo a ejecutar el pipeline.

## Fallos esperables

- Una fuente puede limitar, cambiar o interrumpir su API; el workflow live debe
  fallar y conservar el diagnóstico disponible, no inventar resultados.
- Si OpenAlex deja de aceptar la búsqueda básica anónima, el adaptador falla de
  forma explícita; no se añade una API key como alternativa.
- Un checksum Bronze distinto detiene Silver.
- Un `source_type` distinto de `real` detiene los límites productivos.
- El primer Gold puede tardar más por la descarga del modelo CPU.
