# Plan de ejecución

## Estado de trabajo

| Paso | Resultado | Estado |
| --- | --- | --- |
| 0. Descubrimiento de fuente | Muestra real y decisión inicial documentadas | Completado en el commit anterior |
| 1. Diseño definitivo | PRD, contratos, arquitectura, fuentes y ADRs de esta entrega | Completado |
| 2. Esqueleto local | Paquete, configuración, dependencias, contenedor y pruebas mínimas | Completado |
| 3. Bronze | Adaptadores PubMed, Europe PMC y OpenAlex; bytes crudos, manifiestos e idempotencia de descarga | Pendiente |
| 4. Silver | Pydantic v2, cuarentena, canonicalización, staging y UPSERT DuckDB | Pendiente |
| 5. Gold | Corpus, embeddings multilingües, FAISS incremental y consulta española | Pendiente |
| 6. Operación | Docker Compose, evidencia generada por código y GitHub Actions | Pendiente |

## Paso activo cerrado: esqueleto local

Esta fase crea el mínimo reproducible para los pasos posteriores: paquete Python 3.11, CLI Typer, configuración sin secretos, rutas locales, Docker Compose de un único servicio no root, dependencia bloqueada y pruebas. No implementa llamadas a APIs, tablas, payloads Bronze, DuckDB, FAISS, modelos ni pipeline.

Validación ejecutada en esta fase: `doctor`, los seis comandos placeholder (salida 2), Ruff, mypy y 19 pruebas de pytest. Las pruebas incluyen configuración, rutas, CLI, contrato estático de contenedor, reglas de ignorado y la salvaguarda que rechaza `source_type='synthetic'` en límites productivos. Las comprobaciones `docker compose config`, `docker compose build` y `docker compose run --rm pipeline doctor` quedan pendientes porque Docker no está instalado en este equipo.

## Secuencia crítica posterior

1. Crear el esqueleto Python y el entorno de pruebas sin datos reales versionados.
2. Implementar Bronze primero: una página/respuesta por archivo inmutable y un manifiesto separado.
3. Añadir los modelos Pydantic v2 y la prueba de exclusión de `source_type='synthetic'` antes de habilitar Silver.
4. Implementar staging y UPSERT idempotente en DuckDB antes de embeddings.
5. Construir Gold/FAISS sólo desde Silver válido y ejecutar las consultas de aceptación en español.
6. Añadir contenedores y CI cuando el recorrido local cumpla la matriz de aceptación.

## Decisiones que no bloquean este plan

- Rango propuesto: 0–36 meses.
- Ranking propuesto: evidencia científica primero, recursos prácticos después.
- SciELO es opcional y no puede retrasar los pasos 2–6.
