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
| 6. Operación | Docker Compose, evidencia generada por código y GitHub Actions | Pendiente |

## Paso activo: Gold (completado; no avanzar a Operación sin una nueva instrucción)

Silver lee exclusivamente bytes existentes en `data/bronze/<batch_id>/`, verifica su SHA-256 y extrae registros mediante parsers de PubMed, Europe PMC y OpenAlex. `ResourceRecord` usa Pydantic v2 estricto; normaliza solamente Unicode, espacios e identificadores permitidos. La carga `silver --batch-id` ejecuta migraciones SQL, vacía staging, deduplica por DOI o PMID, selecciona un principal determinista, conserva procedencias, hace UPSERT transaccional, persiste cuarentenas idempotentes, registra runs/métricas y ejecuta la auditoría de duplicados. No realiza llamadas HTTP ni modifica payloads Bronze.

Gold recibe exclusivamente `silver_resources` reales. Forma textos E5 sin traducción como `passage: <title>. <abstract>. Keywords: <keywords>. Subjects: <subject_terms>.`, usa `intfloat/multilingual-e5-small` en CPU con vectores `float32` normalizados L2, y registra la revisión efectiva. `gold_embeddings` conserva ID entero estable, contenido, vector y metadata; `gold_index_state` conserva el SHA-256 de `data/gold/resources.faiss`. La actualización elimina y reemplaza sólo los vectores de contenido/modelo modificados; un no-op no reescribe el índice. `search` sólo admite la consulta explícita de CLI y devuelve campos de presentación seguros.

En la ejecución local real, `baby-first-steps gold` procesó el lote Silver disponible: insertó 1 embedding de 384 dimensiones con la revisión `614241f622f53c4eeff9890bdc4f31cfecc418b3` y generó `artifacts/gold/acceptance-search.json` con las seis consultas en español. El artifact usa revisión manual de coherencia pendiente y no declara relevancia automática. No se versionan el índice, la base DuckDB, la caché del modelo ni ese artifact.

## Estado del entorno Docker

Docker Desktop 4.84.0 y su motor 29.6.2 se verificaron tras habilitar WSL 2 y
la Plataforma de máquina virtual. Se ejecutaron correctamente `docker compose
config`, `docker compose build` y `docker compose run --rm pipeline doctor`.
El contenedor informó Python 3.11.15, rutas escribibles y UID 10001 (no root).
Después de Gold se ejecutaron dentro de la imagen, con el repositorio montado
como solo lectura, `ruff check --no-cache src tests`, `mypy --cache-dir=/tmp/mypy-cache src`
y la suite completa de pytest: 68 pruebas pasaron; pytest mostró una advertencia
de deprecación procedente de `faiss-cpu`/NumPy, sin fallo. `gold` se ejecutó una
segunda vez contra los datos reales y reportó `embeddings_noop=1` con el mismo
SHA-256, sin reescritura del índice. El `ENTRYPOINT` de la imagen invoca la CLI,
por lo que el argumento `doctor` del comando Compose se interpreta correctamente.

## Secuencia crítica posterior

1. Añadir operación/CI sólo tras una nueva instrucción; no forma parte de este paso.

## Decisiones que no bloquean este plan

- Rango propuesto: 0–36 meses.
- Ranking propuesto: evidencia científica primero, recursos prácticos después.
- SciELO es opcional y no puede retrasar los pasos 2–6.
