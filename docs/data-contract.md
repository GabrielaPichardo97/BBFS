# Contrato de datos y canonicalización

## Convenciones comunes

- `source_name`: `pubmed`, `europe_pmc` u `openalex`.
- `source_type`: sólo `real` en ejecución productiva. `synthetic` sólo es válido bajo `tests/fixtures/synthetic/` y dentro de un test.
- Fechas: ISO-8601 UTC para ejecución; fechas de publicación conservan la precisión entregada por la fuente.
- DOI normalizado: minúsculas, sin URL/prefijo `doi:`, sin espacios extremos.
- PMID: cadena decimal sin prefijo URL.

## BronzeResponseManifest

El manifest es metadata de la descarga, no una transformación del payload.

| Campo | Regla |
| --- | --- |
| `run_id`, `source_name`, `sequence` | obligatorios; identifican una respuesta de la ejecución |
| `query_profile`, `source_query`, `request_url` | obligatorios; reproducen la adquisición |
| `status_code`, `received_at_utc`, `latency_ms`, `content_type` | obligatorios |
| `payload_path`, `payload_sha256`, `payload_bytes` | obligatorios y calculados sobre bytes sin modificar |
| `cursor_in`, `cursor_out`, `retry_count` | opcionales según fuente |
| `source_type` | debe ser exactamente `real` |

El archivo de payload contiene sólo `response.content`. No se permite cargarlo, reserializarlo ni usar un objeto JSON/XML como sustituto de esos bytes.

## ResourceRecord Silver (Pydantic v2)

| Campo | Regla |
| --- | --- |
| `source_name`, `source_record_id` | obligatorios; identifican el registro fuente |
| `title` | obligatorio, no vacío después de normalización Silver |
| `abstract` | opcional; ausencia no se inventa |
| `language`, `publication_date`, `authors`, `keywords`, `controlled_terms` | opcionales y trazables a la fuente |
| `doi_normalized`, `pmid`, `openalex_id` | opcionales; se validan por formato |
| `landing_url`, `license`, `rights_note` | opcionales; no infieren derechos de la obra |
| `bronze_payload_sha256`, `bronze_record_locator` | obligatorios para procedencia |
| `source_type` | debe ser `real`; cualquier otro valor se rechaza |

Las transformaciones permitidas aquí incluyen extraer campos, decodificar, limpiar espacios, normalizar identificadores y estructurar autores/términos. No se modifica Bronze. La validación produce `ResourceRecord` en memoria y la carga Silver posterior la persiste dentro de una única transacción DuckDB.

## SilverCanonicalDocument y procedencia

`SilverCanonicalDocument` tiene `canonical_key`, título/abstract elegidos, idioma, fechas, identificadores normalizados y timestamps de carga. `SilverDocumentProvenance` tiene una fila por `(canonical_key, source_name, source_record_id, bronze_payload_sha256)` y conserva todos los valores fuente relevantes.

### Clave natural y fusión

1. Si existe DOI normalizado, `canonical_key = "doi:<doi>"`.
2. Si no existe DOI y existe PMID, `canonical_key = "pmid:<pmid>"`.
3. Si no existen los anteriores y el origen es OpenAlex, `canonical_key = "openalex:<W-id>"`.
4. En último caso, `canonical_key = "source:<source_name>:<source_record_id>"`.

Dos registros se unen sólo por DOI igual normalizado o PMID igual. Nunca por título, similitud textual, URL temporal o hash del payload. El registro principal se selecciona de forma determinista: abstract no vacío, abstract más completo, PubMed, Europe PMC, OpenAlex y `source_record_id` como desempate. La tabla de procedencia conserva cada representación fuente y los agregados `observed_sources` y `source_count` se acumulan en reprocesos de la misma clave canónica.

## Cuarentena

`QuarantineRecord` incluye un `quarantine_id` determinista, identificador canónico candidato, fuente, locator Bronze, hash del registro crudo, fecha y una lista completa de errores. Hay una sola cuarentena por registro fuente aunque tenga varios errores. `silver_rejects` usa ese identificador como clave primaria, por lo que un reproceso no duplica la cuarentena. Sólo admite payloads reales; no existe ruta productiva para datos sintéticos.

## Persistencia Silver DuckDB

La base local ignorada por Git es `data/baby_first_steps.duckdb`. La migración
versionada `sql/001_silver_schema.sql` crea `meta_schema_version`,
`bronze_batches`, `stg_resources`, `silver_resources`,
`silver_resource_sources`, `silver_rejects`, `pipeline_runs` y `dq_metrics`.

- Cada `silver --batch-id` inicia una transacción, vacía `stg_resources`, carga
  sólo los registros ya validados de ese batch y conserva una fila principal por
  `canonical_id` con prioridad determinista.
- DuckDB 1.2 no implementa `MERGE`; la implementación realiza el UPSERT
  equivalente mediante inserción o actualización de las filas deduplicadas de
  staging dentro de la misma transacción.
- `content_hash` igual incrementa `rows_noop` y no cambia `updated_at`.
  Un hash diferente incrementa `rows_updated` y actualiza sólo los campos
  funcionales. Una clave inexistente incrementa `rows_inserted`.
- Un fallo revierte staging, lotes, recursos, procedencias, cuarentenas y
  métricas de esa transacción; `pipeline_runs` conserva un run separado con
  estado `failed` y el mensaje de error.
- `audit-duplicates` ejecuta las consultas de aceptación de recursos y
  cuarentenas, y además exige cero filas con `source_type='synthetic'` en las
  cuatro tablas de datos Silver.

## GoldSearchDocument

Gold recibe sólo documentos Silver canónicos válidos. Contiene `canonical_key`, `language`, `embedding_text`, hash de texto, versión de modelo y procedencia. `embedding_text` se construye como `title + abstract` y añade keywords/MeSH en una sección identificada si existen. Gold debe rechazar explícitamente `source_type='synthetic'`, referencias Bronze directas y registros sin procedencia Silver.

## Salvaguarda obligatoria contra sintéticos

Antes de cerrar el paso Silver, una prueba automatizada debe:

1. Cargar un fixture artificial exclusivamente desde `tests/fixtures/synthetic/`.
2. Verificar que el intento de persistirlo en una ejecución productiva falla con un error inequívoco.
3. Consultar las tablas/evidencia productivas y exigir cero filas con `source_type='synthetic'`.
4. Verificar que Gold/FAISS no recibe ese fixture.

La matriz de aceptación no podrá marcar estos criterios como PASS sin ejecutar dicha prueba.
