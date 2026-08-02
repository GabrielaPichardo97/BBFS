# Matriz de aceptación

Los estados siguientes reflejan únicamente esta fase de diseño. `Especificado` no significa PASS de implementación.

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
| Gold | Sólo Silver válido y real llega a embedding/FAISS | prueba de frontera Silver→Gold | Pendiente |
| Búsqueda | Las ocho consultas de aceptación se ejecutan en español | prueba de demostración con catálogo real pequeño | Pendiente |
| Evidencia | Métricas y reportes se generan por código | comando de evidencia en CI/local | Pendiente |
| Operación | Docker Compose reproduce el recorrido local sin nube | `docker compose up` y smoke test | Pendiente |

## Consultas de aceptación futuras, todas en español

1. actividades de estimulación temprana para bebés
2. juegos sensoriales para bebés de cero a doce meses
3. actividades de motricidad fina con objetos cotidianos
4. juegos para desarrollar la coordinación y el movimiento
5. lectura compartida para estimular el lenguaje
6. música y movimiento para el desarrollo infantil temprano
7. interacción entre cuidadores y bebés para el desarrollo socioemocional
8. materiales de juego seguros para bebés y niños pequeños
