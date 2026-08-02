# Plan de ejecución

## Estado de trabajo

| Paso | Resultado | Estado |
| --- | --- | --- |
| 0. Descubrimiento de fuente | Muestra real y decisión inicial documentadas | Completado en el commit anterior |
| 1. Diseño definitivo | PRD, contratos, arquitectura, fuentes y ADRs de esta entrega | Completado |
| 2. Esqueleto local | Paquete, configuración, dependencias, contenedor y pruebas mínimas | Completado |
| 3. Bronze | Adaptadores PubMed, Europe PMC y OpenAlex; bytes crudos, manifiestos e idempotencia de descarga | Completado |
| 4. Silver | Pydantic v2, cuarentena, canonicalización, staging y UPSERT DuckDB | Pendiente |
| 5. Gold | Corpus, embeddings multilingües, FAISS incremental y consulta española | Pendiente |
| 6. Operación | Docker Compose, evidencia generada por código y GitHub Actions | Pendiente |

## Paso activo cerrado: Bronze

Esta fase implementa exclusivamente Bronze: adaptadores nativos de PubMed, Europe PMC y OpenAlex; reintentos limitados, `Retry-After`, límites por fuente, batches reanudables, manifiestos y checksums. Cada respuesta exitosa se persiste desde `response.content` como bytes opacos; no se parsean documentos ni se implementan tablas, DuckDB, Silver, Gold, FAISS ni modelos.

Validación ejecutada en esta fase: Ruff, mypy y 31 pruebas de pytest, incluidas pruebas sin red de inmutabilidad byte a byte, XML/JSON, reintentos, errores definitivos, escritura atómica, colisiones, manifest y reanudación. También se ejecutó una ingesta real limitada a 20 registros por fuente, que produjo cuatro respuestas HTTP y cero fallos; se validaron sus SHA-256 y que los payloads están ignorados por Git. La reanudación del mismo batch no solicitó ni sustituyó payloads.

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

1. Añadir los modelos Pydantic v2 y la prueba de exclusión de `source_type='synthetic'` antes de habilitar Silver.
2. Implementar staging y UPSERT idempotente en DuckDB antes de embeddings.
3. Construir Gold/FAISS sólo desde Silver válido y ejecutar las consultas de aceptación en español.
4. Añadir contenedores y CI cuando el recorrido local cumpla la matriz de aceptación.

## Decisiones que no bloquean este plan

- Rango propuesto: 0–36 meses.
- Ranking propuesto: evidencia científica primero, recursos prácticos después.
- SciELO es opcional y no puede retrasar los pasos 2–6.
