# Plan de ejecución

## Estado de trabajo

| Paso | Resultado | Estado |
| --- | --- | --- |
| 0. Descubrimiento de fuente | Muestra real y decisión inicial documentadas | Completado en el commit anterior |
| 1. Diseño definitivo | PRD, contratos, arquitectura, fuentes y ADRs de esta entrega | Completado |
| 2. Esqueleto local | Paquete, configuración, dependencias, contenedor y pruebas mínimas | Completado |
| 3. Bronze | Adaptadores PubMed, Europe PMC y OpenAlex; bytes crudos, manifiestos e idempotencia de descarga | Completado |
| 4. Silver | Pydantic v2, cuarentena, canonicalización, staging y UPSERT DuckDB | Completado |
| 5. Gold | Corpus, embeddings multilingües, FAISS incremental y consulta española | Pendiente |
| 6. Operación | Docker Compose, evidencia generada por código y GitHub Actions | Pendiente |

## Paso activo: Silver (completado; no avanzar a Gold sin una nueva instrucción)

Silver lee exclusivamente bytes existentes en `data/bronze/<batch_id>/`, verifica su SHA-256 y extrae registros mediante parsers de PubMed, Europe PMC y OpenAlex. `ResourceRecord` usa Pydantic v2 estricto; normaliza solamente Unicode, espacios e identificadores permitidos. La carga `silver --batch-id` ejecuta migraciones SQL, vacía staging, deduplica por DOI o PMID, selecciona un principal determinista, conserva procedencias, hace UPSERT transaccional, persiste cuarentenas idempotentes, registra runs/métricas y ejecuta la auditoría de duplicados. No realiza llamadas HTTP ni modifica payloads Bronze.

Validación ejecutada en esta fase: `docker compose config`, `docker compose build`, `docker compose run --rm pipeline doctor`, Ruff, mypy y 61 pruebas de pytest. Las pruebas cubren inmutabilidad byte a byte, XML/JSON, reintentos, escritura atómica, Pydantic v2, parsers Silver, cuarentena determinista, clave natural, staging, UPSERT, cuatro reprocesos exactos, contenido modificado, DOI/PMID entre fuentes, prioridad determinista, estabilidad de `updated_at`, rollback, métricas y bloqueo de `source_type='synthetic'`. También se cargó dos veces el batch real `20260802T235347835334Z-218bcf`: la primera carga insertó 1 recurso; la segunda informó `rows_inserted=0`, `rows_updated=0`, `rows_noop=1` y `quarantine_inserted=0`. Las dos consultas de aceptación devolvieron cero filas y el chequeo de filas sintéticas devolvió 0.

## Estado del entorno Docker

Docker Desktop 4.84.0 y su motor 29.6.2 se verificaron tras habilitar WSL 2 y
la Plataforma de máquina virtual. Se ejecutaron correctamente `docker compose
config`, `docker compose build` y `docker compose run --rm pipeline doctor`.
El contenedor informó Python 3.11.15, rutas escribibles y UID 10001 (no root).
También se ejecutaron dentro de la imagen, con el repositorio montado como
solo lectura, Ruff, mypy y las 31 pruebas de pytest: todos pasaron. El
`ENTRYPOINT` de la imagen invoca la CLI, por lo que el argumento `doctor` del
comando Compose se interpreta correctamente.

## Secuencia crítica posterior

1. Construir Gold/FAISS sólo desde Silver válido y ejecutar las consultas de aceptación en español.
2. Añadir CI cuando el recorrido local cumpla la matriz de aceptación.

## Decisiones que no bloquean este plan

- Rango propuesto: 0–36 meses.
- Ranking propuesto: evidencia científica primero, recursos prácticos después.
- SciELO es opcional y no puede retrasar los pasos 2–6.
