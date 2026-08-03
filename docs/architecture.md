# Arquitectura definitiva propuesta

## Principios

- Local-first, sin infraestructura cloud ni secretos obligatorios.
- Capas medallón estrictas: Bronze preserva; Silver transforma; Gold recupera.
- La unidad de trazabilidad es la respuesta de una fuente y la unidad de búsqueda es el documento canónico.
- La demostración pública usa sólo consultas españolas; la adquisición puede usar español e inglés.

## Flujo local

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
- Implementación actual: `silver` lee un batch Bronze local, verifica hashes,
  valida con Pydantic v2 y persiste el resultado con staging, UPSERT
  transaccional DuckDB, procedencia, cuarentena, métricas y auditoría. No hace
  llamadas HTTP ni modifica los bytes Bronze.
- Salidas: documento canónico, una o más filas de procedencia y cuarentena auditable para datos reales inválidos.
- Almacén: DuckDB local en `data/baby_first_steps.duckdb`, con migraciones SQL
  versionadas, staging transitorio y UPSERT transaccional.
- Idempotencia: reejecutar el mismo manifest no crea una nueva entidad ni una nueva procedencia idéntica.

## Gold

- Entrada exclusiva: documentos Silver válidos con `source_type='real'`. La
  implementación falla antes de codificar si Silver o Gold contiene otro tipo.
- Documento de recuperación: `passage: <title>. <abstract>. Keywords:
  <keywords>. Subjects: <subject_terms>.`, sin traducción ni enriquecimiento.
- Modelo: `intfloat/multilingual-e5-small`, sólo CPU. Los documentos usan el
  prefijo `passage:` y las consultas en español usan `query:`. Se almacenan la
  revisión efectiva, dimensión y `content_hash` junto con el vector `float32`
  normalizado L2.
- Índice: `IndexFlatIP` dentro de `IndexIDMap2`, con ID entero estable derivado
  del identificador canónico. El archivo atómico
  `data/gold/resources.faiss` y los vectores/estado DuckDB se ignoran en Git.
  El estado registra el SHA-256 del archivo y permite detectar desalineación.
- Incrementalidad: entradas sin cambio de contenido y modelo son no-op; los
  documentos cambiados sustituyen su vector conservando el ID; un índice ausente
  puede reconstruirse desde los blobs Gold sin recodificar entradas sin cambio.
- Consulta: `semantic_search(query, top_k)` valida checksum y compatibilidad de
  modelo antes de devolver rank, score, fragmento, idioma, fecha, URL y fuentes
  observadas. No aplica un umbral artificial de relevancia.

## Operación posterior (fuera del paso actual)

1. Comando de adquisición limitado y reproducible.
2. Comando de transformación Silver que incluye la prueba de exclusión sintética.
3. Comando de construcción Gold/FAISS que rechaza una entrada no Silver o sintética.
4. Docker Compose sólo envolverá ese flujo local probado; no añadirá servicios externos.
5. CI ejecutará pruebas, demostración española y evidencia agregada; los payloads reales serán artifacts efímeros, no commits.

## Demostración reproducible

`baby-first-steps demo --fresh` es el recorrido ejecutable de la rúbrica, no un
notebook. Verifica prerrequisitos locales, solicita confirmación de la limpieza
o acepta `--yes`, y elimina sólo rutas generadas conocidas dentro del proyecto.
Adquiere dos batches Bronze reales con IDs distintos usando los tres adaptadores;
selecciona explícitamente el primero para Silver y Gold. La segunda corrida
revalida y reprocesa exactamente ese batch local, por lo que no llama las APIs.

La evidencia se crea mediante código bajo `artifacts/` y
`docs/evidence.generated.md`, ambos ignorados por Git. Incluye tablas de Bronze
y contrato, métricas de idempotencia, SQL exacto de duplicados, seis consultas
en español y los conteos calculados de `source_type='synthetic'` en Bronze,
Silver, Gold y la propia evidencia. Cualquier criterio no satisfecho termina el
comando con código no cero.
