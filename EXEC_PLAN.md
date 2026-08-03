# Plan de ejecución

## Estado de trabajo

| Paso | Resultado | Estado |
| --- | --- | --- |
| 0. Descubrimiento de fuente | Muestra real y decisión inicial documentadas | Completado en el commit anterior |
| 1. Diseño definitivo | PRD, contratos, arquitectura, fuentes y ADRs de esta entrega | Completado |
| 2. Esqueleto local | Paquete, configuración, dependencias, contenedor y pruebas mínimas | Completado |
| 3. Bronze | Adaptadores PubMed, Europe PMC y OpenAlex; bytes crudos, manifiestos e idempotencia de descarga | Completado |
| 4. Silver | Pydantic v2, cuarentena, canonicalización, staging y UPSERT DuckDB | Completado |
| 5. Gold | Embeddings multilingües CPU, FAISS incremental, búsqueda española y evidencia por consulta | Completado |
| 6. Operación | Demostración, evidencia, documentación pública y workflows CI/live reproducibles | Completado |

## Paso activo: Operación — publicación reproducible (completado)

Silver lee exclusivamente bytes existentes en `data/bronze/<batch_id>/`, verifica su SHA-256 y extrae registros mediante parsers de PubMed, Europe PMC y OpenAlex. `ResourceRecord` usa Pydantic v2 estricto; normaliza solamente Unicode, espacios e identificadores permitidos. La carga `silver --batch-id` ejecuta migraciones SQL, vacía staging, deduplica por DOI o PMID, selecciona un principal determinista, conserva procedencias, hace UPSERT transaccional, persiste cuarentenas idempotentes, registra runs/métricas y ejecuta la auditoría de duplicados. No realiza llamadas HTTP ni modifica payloads Bronze.

Gold recibe exclusivamente `silver_resources` reales. Forma textos E5 sin traducción como `passage: <title>. <abstract>. Keywords: <keywords>. Subjects: <subject_terms>.`, usa `intfloat/multilingual-e5-small` en CPU con vectores `float32` normalizados L2, y registra la revisión efectiva. `gold_embeddings` conserva ID entero estable, contenido, vector y metadata; `gold_index_state` conserva el SHA-256 de `data/gold/resources.faiss`. La actualización elimina y reemplaza sólo los vectores de contenido/modelo modificados; un no-op no reescribe el índice. `search` sólo admite la consulta explícita de CLI y devuelve campos de presentación seguros.

`demo --fresh` es ahora el recorrido reproducible de esta fase. Tras verificar el entorno y limpiar sólo rutas generadas conocidas con confirmación (u `--yes`), obtiene dos batches Bronze reales de PubMed, Europe PMC y OpenAlex. Selecciona explícitamente el primero para Silver/Gold y lo reprocesa localmente sin consultas HTTP adicionales. El comando exige idempotencia, cero duplicados, seis búsquedas en español y los cuatro conteos calculados de seguridad sintética en cero antes de escribir la evidencia.

La ejecución final desde Docker usó los batches `20260803T020206199544Z-36d001` y `20260803T020211371104Z-364f0e`. Generó `artifacts/evidence.json`, `artifacts/evidence.csv`, `artifacts/run.log` y `docs/evidence.generated.md`; los cuatro son salidas ignoradas por Git. La matriz calculada dejó en PASS entorno, dos batches reales, idempotencia, duplicados, seis búsquedas y seguridad sintética. La segunda corrida tuvo cero inserciones/actualizaciones Silver y Gold, y tres no-ops de recursos y embeddings. No se versionan los payloads Bronze, la base DuckDB, la caché del modelo, el índice FAISS ni la evidencia generada.

## Estado del entorno Docker

Docker Desktop 4.84.0 y su motor 29.6.2 se verificaron tras habilitar WSL 2 y
la Plataforma de máquina virtual. Se ejecutaron correctamente `docker compose
config`, `docker compose build` y `docker compose run --rm pipeline doctor`.
El contenedor informó Python 3.11.15, rutas escribibles y UID 10001 (no root).
Se ejecutaron fuera de Docker y desde Docker `demo --fresh --yes`; se conserva
sólo la evidencia de Docker. También se ejecutaron dentro de la imagen, con el
repositorio montado como solo lectura, `ruff check --no-cache src tests`,
`mypy --cache-dir=/tmp/mypy-cache src` y la suite completa de pytest: 70 pruebas
pasaron. Pytest mostró una advertencia de deprecación procedente de
`faiss-cpu`/NumPy, sin fallo. `docker compose run --rm pipeline evidence`
regeneró las tres vistas derivadas sin llamadas a APIs. El `ENTRYPOINT` de la
imagen invoca la CLI, por lo que el argumento `doctor` del comando Compose se
interpreta correctamente.

La preparación pública añade dos workflows con permisos de sólo lectura. `CI`
se ejecuta en pull requests y pushes a `main`: instala desde el lock, ejecuta
Ruff, mypy, pruebas unitarias con cobertura, valida y construye Docker, ejecuta
`doctor`, prueba la integración con `--network none` y escanea rutas
productivas. `E2E live` queda separado, sólo manual o semanal, con timeout,
concurrency, caché de Hugging Face y retención de evidencia durante 14 días;
no publica payloads Bronze completos.

Las verificaciones de esta entrega pasaron localmente: Ruff, mypy sobre 25
archivos, 74 pruebas unitarias con 83% de cobertura, YAML de ambos workflows,
escaneo publicable de 98 archivos, `docker compose config`, build de la imagen
CPU, `doctor`, una integración medallón sin red y escaneo Docker de 105 archivos
con `data/` y `artifacts/` vacíos. La API pública anónima de GitHub confirmó
`GabrielaPichardo97/BBFS`, `private=false` y rama predeterminada `main`. Las
ejecuciones alojadas de ambos workflows permanecen `NOT VERIFIED` hasta que
GitHub las ejecute; este estado no se declara `PASS` por inspección.

## Cierre del paso

No queda una fase posterior autorizada en este plan. La matriz reproducible de
esta entrega está en `docs/rubric-traceability.md`; cualquier trabajo futuro
requiere una nueva instrucción.

## AuditorÃ­a independiente final (completada)

Un clon nuevo de la rama predeterminada `main` revelÃ³ que el commit
`3418c2d7262ebe32d19514578c6db51003c429b1` sÃ³lo contiene un README de seis
bytes; los seis comandos Docker fallaron allÃ­. La implementaciÃ³n se auditÃ³ desde
el commit `eebbbd56a074348ab1daa4467fb5c1291c7ed5a0` en la rama
`codex/final-independent-audit`. Se corrigieron exclusivamente los bloqueos de
ejecuciÃ³n: comando offline `pipeline test`, consultas que realmente aportan
registros de las tres fuentes y criterios calculados para integridad de bytes,
cuarentena real y corpus bilingÃ¼e.

Se ejecutÃ³ dos veces desde cero `docker compose run --rm pipeline demo --fresh
--yes` sobre el mismo clon. Ambas ejecuciones pasaron diez criterios calculados,
procesaron dos veces el mismo batch seleccionado, dejaron la segunda corrida
con cero inserciones/actualizaciones Silver y Gold, devolvieron cero duplicados,
generaron seis bÃºsquedas espaÃ±olas con resultados y calcularon cero registros
sintÃ©ticos en Bronze, Silver, Gold y evidencia. La ejecuciÃ³n final se conserva
localmente; payloads, DuckDB, modelo e Ã­ndice permanecen ignorados. Resultados,
limitaciones y estado `NOT VERIFIED` de GitHub Actions alojadas se documentan en
`docs/final-audit.md` y `output/pdf/bbfs-final-audit.pdf`. El merge a `main`
queda fuera de este paso y es el Ãºnico bloqueo para que un clon predeterminado
sea reproducible.

## Actualización del informe técnico (completada)

Se regeneró `output/pdf/bbfs-final-audit.pdf` como informe A4 de 12 páginas con
resumen ejecutivo, diagrama de arquitectura, detalle Bronze/Silver/Gold,
contratos Pydantic, cuarentena, staging/UPSERT, idempotencia, auditorías de
duplicados, búsqueda E5/FAISS, matriz de 20 requisitos y anexos de terminal.
La actualización usa una tercera ejecución Docker real con batches
`20260803T043422262180Z-90bc82` y `20260803T043426533522Z-b102e3`; no versiona
payloads, DuckDB, modelos, índice FAISS ni evidencia cruda.

La evidencia calculada de esa ejecución obtuvo 10/10 criterios PASS, segunda
corrida con cero inserciones y actualizaciones Silver/Gold, cero duplicados y
seis búsquedas en español con resultados. El run alojado de GitHub Actions
`30784482168` terminó con los dos jobs en `SUCCESS`. Las 12 páginas del PDF se
renderizaron con Poppler y se inspeccionaron visualmente sin cortes ni
solapamientos.

## Decisiones que no bloquean este plan

- Rango propuesto: 0–36 meses.
- Ranking propuesto: evidencia científica primero, recursos prácticos después.
- SciELO es opcional y no puede retrasar los pasos 2–6.
