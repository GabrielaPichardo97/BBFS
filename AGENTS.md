# Instrucciones del repositorio

## Proyecto y alcance

- Proyecto visible: `baby-first-steps-medallion`; paquete futuro: `baby_first_steps_medallion`.
- La rama principal es `main`. Antes de actuar, ejecutar `git status --short --branch` e inspeccionar el remoto.
- Antes de cambiar código, leer este archivo, `docs/PRD.md` y `EXEC_PLAN.md`.
- Ejecutar únicamente el paso activo del plan. Un paso posterior permanece pendiente aunque su diseño esté documentado.

## Límites técnicos

- Priorizar una implementación local, gratuita, reproducible y dockerizada.
- No añadir nube, Terraform, Spark, Airflow, MinIO, PostgreSQL, Streamlit, FastAPI ni interfaz web sin autorización expresa.
- No usar API keys ni servicios de pago. Un adaptador cuya fuente deje de aceptar acceso anónimo debe fallar de forma clara y no debe introducir una clave como alternativa.
- No versionar respuestas descargadas, PDFs, texto completo, modelos, DuckDB ni índices FAISS.

## Datos y capas

- Bronze conserva los bytes originales de cada respuesta. No reformatear JSON/XML ni aplicar normalizaciones en Bronze.
- Silver contiene toda transformación, validación, normalización, deduplicación y cuarentena.
- Gold contiene sólo entidades Silver válidas y no sintéticas; los embeddings e índices son derivados locales no versionados.
- Los datos sintéticos sólo pueden existir en `tests/fixtures/synthetic/` y sólo los puede cargar código de pruebas.
- Está prohibido que `source_type='synthetic'` aparezca en rutas Bronze reales, DuckDB productivo, Silver, Gold, evidencia o métricas. Cada implementación debe añadir una prueba automatizada que lo compruebe.

## Calidad y entrega

- No inventar resultados, métricas, pruebas, archivos ni ejecuciones. Una verificación sólo es PASS si se ejecutó.
- Cada cambio funcional requiere pruebas proporcionales; usar respuestas reales pequeñas para evidencia y sintéticas sólo para pruebas negativas aisladas.
- Actualizar `EXEC_PLAN.md` al terminar el paso activo, ejecutar verificaciones aplicables, revisar el diff y crear un solo commit claro.
- Intentar `git push`; reportar resultados reales y únicamente bloqueos pendientes.
