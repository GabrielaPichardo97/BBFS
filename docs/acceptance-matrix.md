# Matriz de aceptación

Los estados reflejan las verificaciones ejecutadas para cada paso. `Pendiente`
no significa que se haya intentado ni que el criterio haya fallado.

| Área | Criterio verificable futuro | Comando o prueba esperada | Estado actual |
| --- | --- | --- | --- |
| Fuentes | PubMed responde sin key, con título y PMID en una muestra real | prueba de adaptador PubMed contra muestra limitada | Especificado; evidencia de diseño ejecutada |
| Fuentes | Europe PMC responde JSON `core` sin key y conserva `source:id` | prueba de adaptador Europe PMC | Especificado; evidencia de diseño ejecutada |
| Fuentes | OpenAlex funciona sin key o marca su lote como no ejecutado sin detener otros | prueba de preflight anónimo + prueba de degradación | Especificado; HTTP 200 observado, no adaptador implementado |
| Fuentes | SciELO no bloquea tres adaptadores críticos | prueba que omite el adaptador opcional | Especificado |
| Bronze | Payload escrito es byte a byte igual a la respuesta HTTP | comparación de SHA-256 de `response.content` y archivo Bronze | Pendiente |
| Bronze | Payload real y manifest no están versionados | `git check-ignore` y prueba de ruta | Pendiente |
| Silver | Modelos son Pydantic v2 y campos mínimos se validan | pruebas unitarias de modelos | Pendiente |
| Silver | Datos inválidos reales van a cuarentena auditable | prueba con respuesta real malformada controlada o fixture de error aislado | Pendiente |
| Sintéticos | Ninguna tabla/evidencia productiva contiene `source_type='synthetic'` | prueba automática de exclusión y consulta DuckDB | Pendiente |
| Canonicalización | DOI > PMID > OpenAlex > fuente/ID, sin deduplicar por título | pruebas unitarias de claves y procedencia múltiple | Pendiente |
| Idempotencia | Reprocesar el mismo manifest no duplica entidad/procedencia | prueba de dos ejecuciones contra DuckDB temporal | Pendiente |
| Gold | Sólo Silver válido y real llega a embedding/FAISS | `tests/unit/test_gold_service.py` incluye la barrera `source_type` y metadata/índice | Ejecutado en pruebas unitarias deterministas |
| Gold | Inserciones, actualizaciones y no-op conservan IDs y no reescriben índice | pruebas Gold de incrementalidad, persistencia y escritura atómica | Ejecutado en pruebas unitarias deterministas |
| Búsqueda | Las seis consultas de aceptación se ejecutan en español | `gold` genera `artifacts/gold/acceptance-search.json` | Ejecutado; revisión de coherencia pendiente de una persona |
| Evidencia | El reporte Gold se genera por código, sin métrica inventada | `write_acceptance_evidence` y prueba unitaria | Ejecutado sólo para evidencia Gold; evidencia integral queda pendiente |
| Operación | Docker Compose reproduce el recorrido local sin nube | `docker compose up` y smoke test | Pendiente |

## Consultas de aceptación Gold, todas en español

1. actividades sensoriales con diferentes texturas para un bebé
2. materiales cotidianos para desarrollar la motricidad fina
3. juegos entre cuidadores y bebés para estimular el lenguaje
4. lectura compartida durante los primeros años de vida
5. música y movimiento para mejorar la coordinación infantil
6. actividades para fortalecer la interacción entre padres e hijos

La revisión de coherencia es manual y estructurada por consulta; no existe un
umbral automático que declare relevancia.
