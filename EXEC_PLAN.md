# Plan de ejecución

## Estado de trabajo

| Paso | Resultado | Estado |
| --- | --- | --- |
| 0. Descubrimiento de fuente | Muestra real y decisión inicial documentadas | Completado en el commit anterior |
| 1. Diseño definitivo | PRD, contratos, arquitectura, fuentes y ADRs de esta entrega | Completado |
| 2. Esqueleto local | Paquete, configuración, dependencias, contenedor y pruebas mínimas | Completado |
| 3. Bronze | Adaptadores PubMed, Europe PMC y OpenAlex; bytes crudos, manifiestos e idempotencia de descarga | Completado |
| 4. Silver | Pydantic v2, cuarentena, canonicalización, staging y UPSERT DuckDB | En curso: extracción y validación temporal completadas; staging y UPSERT pendientes |
| 5. Gold | Corpus, embeddings multilingües, FAISS incremental y consulta española | Pendiente |
| 6. Operación | Docker Compose, evidencia generada por código y GitHub Actions | Pendiente |

## Paso activo: Silver (extracción y validación temporal)

Silver lee exclusivamente bytes existentes en `data/bronze/<batch_id>/`, verifica su SHA-256 y extrae registros en memoria con parsers de PubMed, Europe PMC y OpenAlex. `ResourceRecord` usa Pydantic v2 estricto; normaliza solamente Unicode, espacios e identificadores permitidos. Los registros inválidos generan una sola cuarentena auditable en memoria con todos sus errores. No realiza llamadas HTTP, no escribe payloads Bronze, no crea una tabla Silver, DuckDB, staging ni UPSERT.

Validación ejecutada en esta fase: Ruff, mypy y 51 pruebas de pytest, incluidas pruebas sin red de inmutabilidad byte a byte, XML/JSON, reintentos, errores definitivos, escritura atómica, colisiones, manifest, reanudación, Pydantic v2, parsers Silver, cuarentena determinista, clave natural, estabilidad de `content_hash` y rechazo de `source_type='synthetic'`. También se ejecutaron `silver-validate` sobre dos batches reales ya locales: 18 y 1 registros PubMed válidos respectivamente; Europe PMC y OpenAlex devolvieron cero registros en esas muestras. Hubo cero rechazos reales, cero fallos de parseo y cero abstracts ausentes entre los 19 registros extraídos. El umbral inicial de 80 caracteres no rechazó contenido observado.

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

1. Implementar staging y UPSERT idempotente en DuckDB antes de embeddings.
3. Construir Gold/FAISS sólo desde Silver válido y ejecutar las consultas de aceptación en español.
4. Añadir contenedores y CI cuando el recorrido local cumpla la matriz de aceptación.

## Decisiones que no bloquean este plan

- Rango propuesto: 0–36 meses.
- Ranking propuesto: evidencia científica primero, recursos prácticos después.
- SciELO es opcional y no puede retrasar los pasos 2–6.
