# Arquitectura definitiva propuesta

## Principios

- Local-first, sin infraestructura cloud ni secretos obligatorios.
- Capas medallón estrictas: Bronze preserva; Silver transforma; Gold recupera.
- La unidad de trazabilidad es la respuesta de una fuente y la unidad de búsqueda es el documento canónico.
- La demostración pública usa sólo consultas españolas; la adquisición puede usar español e inglés.

## Flujo futuro

```text
PubMed ─────┐
Europe PMC ─┼─> Bronze inmutable ─> Silver validado/canónico ─> Gold + FAISS
OpenAlex ───┘        │                       │                        │
                      └─ manifest/hash       └─ cuarentena auditable   └─ búsqueda en español
```

SciELO no está en el flujo crítico. Sólo puede añadirse como cuarto adaptador después de una prueba reproducible de interfaz pública estable y sin afectar los tres adaptadores iniciales.

## Bronze

- Entrada: páginas HTTP originales de los adaptadores.
- Persistencia futura: `data/bronze/<run_id>/<source>/<sequence>.<json|xml>` ignorada por Git.
- Inmutabilidad: escribir `response.content` sin decodificar, descomprimir, serializar ni normalizar; calcular el hash sobre esos bytes.
- Manifest separado: URL, consulta interna, cursor/offset, status, headers permitidos, tamaño, latencia, fecha UTC, SHA-256 y ruta del archivo.
- No contiene entidades canónicas, campos transformados, embeddings ni registros sintéticos.

## Silver

- Entrada: bytes Bronze y manifest de la misma respuesta.
- Procesos: parseo por fuente, Pydantic v2, normalización de DOI/PMID, selección de clave, deduplicación determinista y procedencia múltiple.
- Implementación actual: `silver-validate` lee un batch Bronze local, verifica hashes y genera registros y cuarentenas sólo en memoria. No hace llamadas HTTP ni persiste Silver.
- Salidas: documento canónico, una o más filas de procedencia y cuarentena auditable para datos reales inválidos.
- Almacén futuro: DuckDB local con staging transitorio y UPSERT transaccional.
- Idempotencia: reejecutar el mismo manifest no crea una nueva entidad ni una nueva procedencia idéntica.

## Gold

- Entrada exclusiva: documentos Silver válidos con `source_type != 'synthetic'`.
- Documento de recuperación: título + abstract/resumen, y keywords/términos temáticos como contexto separado.
- Índice: FAISS incremental, con manifiesto de versión/hash de los documentos Silver incluidos; índice y vectores se ignoran en Git.
- Consulta: texto español con modelo multilingüe de recuperación asimétrica. La primera opción de evaluación es `intfloat/multilingual-e5-base` con prefijos `query:` y `passage:`; no se descarga ni evalúa en esta fase.

## Operación futura

1. Comando de adquisición limitado y reproducible.
2. Comando de transformación Silver que incluye la prueba de exclusión sintética.
3. Comando de construcción Gold/FAISS que rechaza una entrada no Silver o sintética.
4. Docker Compose sólo envolverá ese flujo local probado; no añadirá servicios externos.
5. CI ejecutará pruebas, demostración española y evidencia agregada; los payloads reales serán artifacts efímeros, no commits.
