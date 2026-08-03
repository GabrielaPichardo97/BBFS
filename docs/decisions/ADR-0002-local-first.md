# ADR-0002: Ejecución local-first y almacenamiento derivado

- Estado: aceptada para diseño.
- Fecha: 2026-08-02.

## Decisión

Ejecutar la arquitectura de forma local. Los payloads reales Bronze, DuckDB, embeddings y FAISS se mantienen fuera de Git; Docker Compose y CI se añadirán sólo tras comprobar el recorrido local. No se incorporan servicios cloud, bases remotas, colas ni orquestadores.

## Consecuencias

- La reproducibilidad proviene de manifests, hashes, configuración y evidencia generada por código.
- Los payloads reales podrán viajar como artifacts efímeros de CI, nunca como commits.
- El sistema debe operar sin API keys ni servicios de pago.
