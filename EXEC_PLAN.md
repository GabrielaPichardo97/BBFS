# Plan de ejecución

## Estado de trabajo

| Paso | Resultado | Estado |
| --- | --- | --- |
| 0. Descubrimiento de fuente | Muestra real y decisión inicial documentadas | Completado en el commit anterior |
| 1. Diseño definitivo | PRD, contratos, arquitectura, fuentes y ADRs de esta entrega | Completado |
| 2. Esqueleto local | Paquete, configuración, dependencias y pruebas unitarias mínimas | Pendiente |
| 3. Bronze | Adaptadores PubMed, Europe PMC y OpenAlex; bytes crudos, manifiestos e idempotencia de descarga | Pendiente |
| 4. Silver | Pydantic v2, cuarentena, canonicalización, staging y UPSERT DuckDB | Pendiente |
| 5. Gold | Corpus, embeddings multilingües, FAISS incremental y consulta española | Pendiente |
| 6. Operación | Docker Compose, evidencia generada por código y GitHub Actions | Pendiente |

## Paso activo cerrado: diseño definitivo

Esta fase fija los contratos y decisiones que usarán los pasos 2–6. No crea `src/`, tests, base DuckDB, índices FAISS, modelos, Docker ni pipeline. El diseño incorpora los tres adaptadores solicitados, con OpenAlex condicionado a que su acceso anónimo siga disponible; nunca se resolverá con una API key.

Validación ejecutada en esta fase: lectura UTF-8 y presencia de los 11 documentos requeridos, comprobación de los invariantes de edad y exclusión sintética en los contratos, ausencia de `src/` y `git diff --check`. No hay criterio de pipeline marcado como PASS.

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
