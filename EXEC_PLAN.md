# Plan de ejecución

## Estado de trabajo

| Paso | Resultado | Estado |
| --- | --- | --- |
| 0. Descubrimiento de fuente | Muestra real y decisión inicial documentadas | Completado en el commit anterior |
| 1. Diseño definitivo | PRD, contratos, arquitectura, fuentes y ADRs de esta entrega | Completado |
| 2. Esqueleto local | Paquete, configuración, dependencias, contenedor y pruebas mínimas | Completado |
| 3. Bronze | Adaptadores PubMed, Europe PMC y OpenAlex; bytes crudos, manifiestos e idempotencia de descarga | Completado |
| 4. Silver | Pydantic v2, cuarentena, canonicalización, staging y UPSERT DuckDB | Completado |
| 5. Gold | Embeddings multilingües CPU, FAISS incremental, búsqueda española y evidencia por consulta | Completado |
| 6. Operación | Demostración reproducible y evidencia generada por código completadas; GitHub Actions queda pendiente | Completado parcialmente |

## Paso activo: Operación — demostración y evidencia (completado; no avanzar a CI sin una nueva instrucción)

Silver lee exclusivamente bytes existentes en `data/bronze/<batch_id>/`, verifica su SHA-256 y extrae registros mediante parsers de PubMed, Europe PMC y OpenAlex. `ResourceRecord` usa Pydantic v2 estricto; normaliza solamente Unicode, espacios e identificadores permitidos. La carga `silver --batch-id` ejecuta migraciones SQL, vacía staging, deduplica por DOI o PMID, selecciona un principal determinista, conserva procedencias, hace UPSERT transaccional, persiste cuarentenas idempotentes, registra runs/métricas y ejecuta la auditoría de duplicados. No realiza llamadas HTTP ni modifica payloads Bronze.

Gold recibe exclusivamente `silver_resources` reales. Forma textos E5 sin traducción como `passage: <title>. <abstract>. Keywords: <keywords>. Subjects: <subject_terms>.`, usa `intfloat/multilingual-e5-small` en CPU con vectores `float32` normalizados L2, y registra la revisión efectiva. `gold_embeddings` conserva ID entero estable, contenido, vector y metadata; `gold_index_state` conserva el SHA-256 de `data/gold/resources.faiss`. La actualización elimina y reemplaza sólo los vectores de contenido/modelo modificados; un no-op no reescribe el índice. `search` sólo admite la consulta explícita de CLI y devuelve campos de presentación seguros.

`demo --fresh` es ahora el recorrido reproducible de esta fase. Tras verificar el entorno y limpiar sólo rutas generadas conocidas con confirmación (u `--yes`), obtiene dos batches Bronze reales de PubMed, Europe PMC y OpenAlex. Selecciona explícitamente el primero para Silver/Gold y lo reprocesa localmente sin consultas HTTP adicionales. El comando exige idempotencia, cero duplicados, seis búsquedas en español y los cuatro conteos calculados de seguridad sintética en cero antes de escribir la evidencia.

La ejecución final desde Docker usó los batches `20260803T020206199544Z-36d001` y `20260803T020211371104Z-364f0e`. Generó `artifacts/evidence.json`, `artifacts/evidence.csv`, `artifacts/run.log` y `docs/evidence.generated.md`; los cuatro son salidas ignoradas por Git. La matriz calculada dejó en PASS entorno, dos batches reales, idempotencia, duplicados, seis búsquedas y seguridad sintética. La segunda corrida tuvo cero inserciones/actualizaciones Silver y Gold, y tres no-ops de recursos y embeddings. No se versionan los payloads Bronze, la base DuckDB, la caché del modelo, el índice FAISS ni la evidencia generada.

## Estado del entorno Docker

Docker Desktop 4.84.0 y su motor 29.6.2 se verificaron tras habilitar WSL 2 y
la Plataforma de máquina virtual. Se ejecutaron correctamente `docker compose
config`, `docker compose build` y `docker compose run --rm pipeline doctor`.
El contenedor informó Python 3.11.15, rutas escribibles y UID 10001 (no root).
Se ejecutaron fuera de Docker y desde Docker `demo --fresh --yes`; se conserva
sólo la evidencia de Docker. También se ejecutaron dentro de la imagen, con el
repositorio montado como solo lectura, `ruff check --no-cache src tests`,
`mypy --cache-dir=/tmp/mypy-cache src` y la suite completa de pytest: 70 pruebas
pasaron. Pytest mostró una advertencia de deprecación procedente de
`faiss-cpu`/NumPy, sin fallo. `docker compose run --rm pipeline evidence`
regeneró las tres vistas derivadas sin llamadas a APIs. El `ENTRYPOINT` de la
imagen invoca la CLI, por lo que el argumento `doctor` del comando Compose se
interpreta correctamente.

## Secuencia crítica posterior

1. Añadir GitHub Actions sólo tras una nueva instrucción; no forma parte de este paso.

## Decisiones que no bloquean este plan

- Rango propuesto: 0–36 meses.
- Ranking propuesto: evidencia científica primero, recursos prácticos después.
- SciELO es opcional y no puede retrasar los pasos 2–6.
