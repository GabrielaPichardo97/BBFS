# AuditorÃ­a independiente final de BBFS

Fecha de ejecuciÃ³n: 2 de agosto de 2026 (America/Mexico_City; las marcas de
evidencia estÃ¡n en UTC). Repositorio pÃºblico verificado mediante la API anÃ³nima
de GitHub: <https://github.com/GabrielaPichardo97/BBFS>.

## Alcance y commits auditados

La inspecciÃ³n comenzÃ³ desde un clon nuevo en un directorio temporal vacÃ­o. La
rama predeterminada `main` apuntaba al commit
`3418c2d7262ebe32d19514578c6db51003c429b1`; contenÃ­a Ãºnicamente
`README.md` con seis bytes. Para evaluar y corregir la implementaciÃ³n existente
sin inventarla de nuevo, se creÃ³ `codex/final-independent-audit` desde
`origin/codex/phase-0-source-discovery`, commit base
`eebbbd56a074348ab1daa4467fb5c1291c7ed5a0`.

Entorno observado:

- Microsoft Windows 11 Home Single Language 10.0.26200, AMD64;
- Git 2.54.0.windows.1;
- Docker cliente y servidor 29.6.2;
- Docker Compose 5.3.1;
- imagen `python:3.11-slim`, Python 3.11.15 y usuario no root UID 10001;
- Pydantic 2.10.6, DuckDB y FAISS CPU disponibles en el contenedor;
- ninguna credencial ni secreto obligatorio.

## Reporte inicial, emitido antes de modificar archivos

El reporte inicial se guardÃ³ fuera del clon como `initial-audit.md` antes de
aplicar correcciones. Estos fueron sus hallazgos reproducibles.

### BLOCKER

| ID | Archivo/lÃ­neas | Evidencia y reproducciÃ³n | Impacto | CorrecciÃ³n mÃ­nima |
| --- | --- | --- | --- | --- |
| B-01 | `README.md:1` en `main` | `git ls-tree -r --name-only 3418c2d7262ebe32d19514578c6db51003c429b1` devolviÃ³ sÃ³lo `README.md`; su contenido era `# BBFS`. | Un clon predeterminado no contiene el producto. | Auditar la rama implementada y publicar las correcciones en una rama revisable. |
| B-02 | `docker-compose.yml` ausente en `main` | Los seis comandos Docker exigidos devolvieron cÃ³digo 1 y `no configuration file provided: not found`. | No existe camino reproducible desde el README predeterminado. | Llevar la implementaciÃ³n corregida a `main` mediante revisiÃ³n/merge. |
| B-03 | `artifacts/evidence.json` y cÃ³digo ausentes en `main` | No habÃ­a CLI, capas ni evidencia que ejecutar. | Ninguno de los veinte criterios podÃ­a verificarse. | Ejecutar y documentar la rama implementada; no declarar PASS en `main`. |

### HIGH

| ID | Archivo/lÃ­neas | Evidencia y reproducciÃ³n | Impacto | CorrecciÃ³n mÃ­nima aplicada |
| --- | --- | --- | --- | --- |
| H-01 | `README.md:1` en `main` | El README tenÃ­a seis bytes y ningÃºn comando. | El quickstart de un clon limpio es inexistente. | Se conserva como bloqueo de `main`; la rama corregida incluye el README ejecutable. |
| H-02 | `.github/workflows/` ausente en `main` | La API de GitHub devolviÃ³ cero workflows en la rama predeterminada. | No hay CI alojada para el cÃ³digo predeterminado. | La rama corregida conserva CI y E2E live; su ejecuciÃ³n alojada sigue sin verificarse. |
| H-03 | `LICENSE` ausente en `main` | `git ls-tree` no mostrÃ³ una licencia. | ReutilizaciÃ³n ambigua del repositorio predeterminado. | La implementaciÃ³n auditada contiene MIT; el merge a `main` sigue pendiente. |
| H-04 | `README.md` y `cli.py` en el commit base implementado | `docker compose run --rm pipeline test` devolviÃ³ cÃ³digo 2: `No such command 'test'`. | El procedimiento literal de auditorÃ­a se detenÃ­a. | Se agregÃ³ un self-test offline que ejecuta almacenamiento inmutable, Pydantic v2, migraciones DuckDB, auditorÃ­a de duplicados/sintÃ©ticos y ausencia de secretos. |
| H-05 | `bronze/adapters.py` y evidencia previa | Europe PMC y OpenAlex respondÃ­an HTTP 200 pero extraÃ­an cero registros; la matriz anterior aun marcaba PASS. | No se demostraban tres fuentes, corpus bilingÃ¼e ni cuarentena real. | Europe PMC usa una expansiÃ³n recuperable; OpenAlex divide el cupo entre `language:es` y `language:en`. La demo ahora falla si una fuente no aporta registros, si falta bilingÃ¼ismo o si no existe una cuarentena real con motivo. |

No se observaron MEDIUM o LOW que justificaran ampliar el cambio. La bÃºsqueda
devuelve resultados, pero la calidad de ranking sobre una muestra de diez
entidades continÃºa siendo una limitaciÃ³n, no un criterio de eficacia clÃ­nica.

## InspecciÃ³n estÃ¡tica de la implementaciÃ³n

- Bronze escribe `response.content` directamente, calcula SHA-256 sobre esos
  bytes y rechaza sobrescrituras divergentes. JSON/XML sÃ³lo se interpreta en
  Silver; manifests y metadatos no sustituyen el payload.
- Los `batch_id` combinan microsegundos y sufijo aleatorio; una prueba ejercita
  dos IDs dentro del mismo microsegundo.
- Silver usa Pydantic v2 estricto, staging real `stg_resources`, clave natural
  DOI normalizado, PMID, OpenAlex y por Ãºltimo fuente+ID. No deduplica por
  tÃ­tulo. El hash de contenido excluye timestamps, batch y rutas.
- El UPSERT calcula inserciones, cambios y no-ops antes de persistir, actualiza
  contenido sÃ³lo cuando cambia el hash y conserva todas las procedencias.
- Cuarentena tiene ID determinista y `ON CONFLICT DO NOTHING`; el reproceso
  observado produjo no-ops, no duplicados.
- Gold usa `intfloat/multilingual-e5-small`, prefijos `query:`/`passage:`,
  vectores normalizados e `IndexIDMap2(IndexFlatIP)`. Reutiliza embeddings sin
  cambios y no hace una bÃºsqueda lÃ©xica disfrazada.
- Las seis consultas de aceptaciÃ³n son espaÃ±olas. Las expansiones inglesas sÃ³lo
  pertenecen a adquisiciÃ³n.
- La evidencia se calcula desde manifests, DuckDB, FAISS y resultados de
  bÃºsqueda; no se encontrÃ³ una tabla productiva ni acceso CLI a fixtures
  sintÃ©ticos.
- Ruff no encontrÃ³ imports/cÃ³digo muerto detectable. El escaneo publicable no
  encontrÃ³ secretos, bases, modelos, Ã­ndices ni datos generados versionables.

## Comandos y resultados reales

### Rama `main` del clon limpio

| Comando | CÃ³digo | Tiempo aproximado | Resultado |
| --- | ---: | ---: | --- |
| `docker compose config` | 1 | 0.38 s | FAIL: no existe configuraciÃ³n |
| `docker compose build` | 1 | 0.22 s | FAIL: no existe configuraciÃ³n |
| `docker compose run --rm pipeline doctor` | 1 | 0.22 s | FAIL: no existe configuraciÃ³n |
| `docker compose run --rm pipeline test` | 1 | 0.21 s | FAIL: no existe configuraciÃ³n |
| `docker compose run --rm pipeline demo --fresh --yes` | 1 | 0.23 s | FAIL: no existe configuraciÃ³n |
| `docker compose run --rm pipeline evidence` | 1 | 0.25 s | FAIL: no existe configuraciÃ³n |

### Rama corregida

| Comando | CÃ³digo | Tiempo aproximado | Resultado |
| --- | ---: | ---: | --- |
| `docker compose config` | 0 | 0.5 s | PASS |
| `docker compose build` | 0 | 12.0 s con cachÃ© | PASS; la construcciÃ³n frÃ­a previa tardÃ³ 375.2 s |
| `docker compose run --rm pipeline doctor` | 0 | 2.8 s | PASS |
| `docker compose run --rm pipeline test` | 0 | 2.8 s | PASS, cinco checks offline |
| `docker compose run --rm pipeline demo --fresh --yes` (ejecuciÃ³n A) | 0 | 29.8 s | PASS |
| `docker compose run --rm pipeline evidence` (A) | 0 | 3.2 s | PASS |
| `docker compose run --rm pipeline demo --fresh --yes` (ejecuciÃ³n B) | 0 | 28.3 s | PASS |
| `docker compose run --rm pipeline evidence` (B) | 0 | 3.4 s | PASS |
| `pytest -q` dentro de la imagen y sin red | 0 | 44.8 s | 77 passed, una advertencia externa FAISS/NumPy |
| `ruff check ...` dentro de la imagen y sin red | 0 | 1.3 s | All checks passed |
| `mypy src` dentro de la imagen y sin red | 0 | n/d | Success, 26 archivos |
| `check_repository_hygiene.py --mode publishable` | 0 | 1.5 s | PASS, 99 archivos al momento del escaneo |

## Dos demostraciones completas sobre el mismo repositorio

Cada ejecuciÃ³n externa de `demo --fresh --yes` obtuvo dos lotes reales y,
dentro de la misma ejecuciÃ³n, procesÃ³ dos veces exactamente el primer lote sin
volver a las APIs. Los JSON completos permanecieron fuera de Git; sus hashes
permiten identificar la evidencia que produjo este informe.

| EjecuciÃ³n | Generada UTC | Batch seleccionado | Segundo batch | SHA-256 de evidence.json | Criterios |
| --- | --- | --- | --- | --- | --- |
| A | 2026-08-03 03:10:34 | `20260803T031009597720Z-f39d0a` | `20260803T031013497553Z-b6cc43` | `0a425b45418475be5918e821cded517c762e245918b9658572fd78b62273ded8` | 10/10 PASS |
| B (conservada) | 2026-08-03 03:11:20 | `20260803T031057657608Z-0ed839` | `20260803T031101598840Z-db7130` | `f97d3b7e0d5d8424fe6dec1423c0504c4b2017b69816ed58dc682252917b96fb` | 10/10 PASS |

Ambas ejecuciones observaron el mismo perfil: Europe PMC 5 extraÃ­dos (4
vÃ¡lidos, 1 `abstract_missing`), OpenAlex 5 (3 vÃ¡lidos, 2
`pmid_invalid`) y PubMed 3 (3 vÃ¡lidos). Silver quedÃ³ con 3 registros espaÃ±oles,
7 ingleses y ninguno desconocido.

## Idempotencia y ausencia de duplicados

Los valores siguientes son iguales en las ejecuciones A y B.

| MÃ©trica | Corrida interna 1 | Reproceso del mismo batch | Esperado | Estado |
| --- | ---: | ---: | ---: | --- |
| rows_inserted | 10 | 0 | 0 | PASS |
| rows_updated | 0 | 0 | 0 | PASS |
| rows_noop | 0 | 10 | 10 | PASS |
| quarantine_inserted | 3 | 0 | 0 | PASS |
| quarantine_noop | 0 | 3 | 3 | PASS |
| embeddings_inserted | 10 | 0 | 0 | PASS |
| embeddings_updated | 0 | 0 | 0 | PASS |
| embeddings_noop | 0 | 10 | 10 | PASS |

| Consulta de duplicados ejecutada | Filas devueltas A | Filas devueltas B | Estado |
| --- | ---: | ---: | --- |
| `silver_resources` por `canonical_id` con `COUNT(*) > 1` | 0 | 0 | PASS |
| `silver_rejects` por `quarantine_id` con `COUNT(*) > 1` | 0 | 0 | PASS |
| `gold_embeddings` por `vector_id` con `COUNT(*) > 1` | 0 | 0 | PASS |
| auditorÃ­a de `source_type='synthetic'` | 0 | 0 | PASS |

## Evidencia de bÃºsqueda semÃ¡ntica

Se usÃ³ FAISS con el modelo E5 multilingÃ¼e. Las seis consultas fueron en espaÃ±ol
y cada una devolviÃ³ cinco resultados en ambas ejecuciones. Ejemplos conservados
de la ejecuciÃ³n B:

| Consulta espaÃ±ola | Rank | Resultado | Idioma | Fuente | Score |
| --- | ---: | --- | --- | --- | ---: |
| actividades sensoriales con diferentes texturas para un bebÃ© | 1 | Programa de estimulaciÃ³n sensorial pre-natal | es | OpenAlex | 0.854306 |
| materiales cotidianos para desarrollar la motricidad fina | 1 | Mecedora Inteligente para bebÃ©s de 0 - 10 meses | es | OpenAlex | 0.818938 |
| mÃºsica y movimiento para mejorar la coordinaciÃ³n infantil | 1 | Programa de estimulaciÃ³n sensorial pre-natal | es | OpenAlex | 0.818911 |

Esto verifica ejecuciÃ³n semÃ¡ntica y resultados, no pertinencia clÃ­nica ni una
calidad de ranking suficiente para producciÃ³n. La muestra pequeÃ±a repite dos
tÃ­tulos como primeros resultados en varias intenciones.

## Matriz literal de aceptaciÃ³n

| # | Requisito | Resultado | Evidencia ejecutada |
| ---: | --- | --- | --- |
| 1 | tres fuentes pÃºblicas sin autenticaciÃ³n | PASS | PubMed, Europe PMC y OpenAlex aportaron 3, 5 y 5 registros; doctor reportÃ³ cero secretos requeridos |
| 2 | contenido espaÃ±ol e inglÃ©s | PASS | 3 espaÃ±oles y 7 ingleses en Silver |
| 3 | dos lotes Bronze distintos | PASS | dos IDs distintos en cada ejecuciÃ³n A/B |
| 4 | payload intacto | PASS | 10/10 archivos re-leÃ­dos con bytes y SHA-256 coincidentes en cada ejecuciÃ³n |
| 5 | Pydantic | PASS | self-test Pydantic 2.10.6 y pruebas de contrato |
| 6 | cuarentena real con motivo | PASS | 3 rechazos; incluye `abstract_missing` real de Europe PMC |
| 7 | cero datos sintÃ©ticos | PASS | Bronze=0, Silver=0, Gold=0, evidencia=0 calculados |
| 8 | staging | PASS | migraciÃ³n y pruebas ejercitaron `stg_resources` |
| 9 | UPSERT por clave natural | PASS | DOI/PMID/OpenAlex/fuente+ID y pruebas de persistencia |
| 10 | reproceso del mismo batch | PASS | cada demo reusÃ³ explÃ­citamente el primer batch |
| 11 | rows_inserted = 0 | PASS | reproceso A=0 y B=0 |
| 12 | rows_updated = 0 | PASS | reproceso A=0 y B=0 |
| 13 | cero duplicados | PASS | cuatro consultas/auditorÃ­as devolvieron cero |
| 14 | FAISS funcional | PASS | Ã­ndice con 10 vectores y seis consultas con resultados |
| 15 | Gold incremental | PASS | reproceso: insertados=0, actualizados=0, no-op=10 |
| 16 | consultas solamente en espaÃ±ol | PASS | seis entradas de aceptaciÃ³n espaÃ±olas |
| 17 | bÃºsqueda con resultados | PASS | cinco resultados por consulta en A y B |
| 18 | Docker Compose | PASS | config, build, doctor, test, demo y evidence con cÃ³digo 0 |
| 19 | evidencia generada | PASS | JSON, CSV, log y Markdown derivados por cÃ³digo |
| 20 | GitHub Actions vÃ¡lidas | PASS local / NOT VERIFIED alojado | pruebas de contrato y YAML locales pasan; no se observÃ³ una corrida alojada de esta rama |

## Seguridad, datos versionados y licencia

`check_repository_hygiene.py --mode publishable` no detectÃ³ secretos, nombres
de credenciales, claves privadas, payloads reales, DuckDB, modelos ni Ã­ndices.
`git ls-files data artifacts` devolviÃ³ solamente `data/.gitkeep` y
`artifacts/.gitkeep`; ningÃºn archivo rastreado superaba 1 MiB. Las Ãºnicas
apariciones productivas de `source_type='synthetic'` son consultas y guardas que
lo rechazan o cuentan. MIT es compatible con la publicaciÃ³n del cÃ³digo de la
rama implementada; no concede derechos adicionales sobre abstracts externos.

## Estado de GitHub y limitaciones

- La API anÃ³nima confirmÃ³ `private=false`, `visibility=public` y rama
  predeterminada `main` para el enlace citado.
- `main` continÃºa siendo el commit mÃ­nimo de seis bytes hasta que la rama
  corregida sea revisada y fusionada. Por tanto, el README de un clon
  predeterminado sigue FAIL aunque esta rama pase la auditorÃ­a.
- Las ejecuciones alojadas de GitHub Actions de la rama corregida son
  `NOT VERIFIED`; la validaciÃ³n local no sustituye una corrida de GitHub.
- Los resultados dependen de APIs externas y de una muestra deliberadamente
  pequeÃ±a. Dos registros OpenAlex se rechazaron por formato de PMID y uno Europe
  PMC por abstract ausente.
- La bÃºsqueda funciona tÃ©cnicamente, pero la pertinencia de algunas primeras
  posiciones es dÃ©bil. Se requiere mÃ¡s corpus y evaluaciÃ³n antes de usarla para
  decisiones documentales serias.
- El producto recupera documentos; no diagnostica, prescribe ni sustituye
  indicaciones mÃ©dicas o de seguridad infantil.

El informe PDF derivado de esta auditorÃ­a se encuentra en
`output/pdf/bbfs-final-audit.pdf`.

## Actualización reproducible del informe PDF

El informe se regeneró con una tercera ejecución Docker fresca sobre el mismo
repositorio y commit auditado. Los lotes reales fueron
`20260803T043422262180Z-90bc82` y `20260803T043426533522Z-b102e3`; la evidencia
calculada volvió a obtener 10/10 criterios PASS, 10/10 payloads Bronze íntegros,
3 registros en español, 7 en inglés, 3 rechazos reales en cuarentena y cero
datos sintéticos en Bronze, Silver, Gold y evidencia.

El reproceso exacto del primer lote produjo `rows_inserted=0`,
`rows_updated=0`, `quarantine_inserted=0`, `embeddings_inserted=0` y
`embeddings_updated=0`. Las auditorías de `canonical_id`, `quarantine_id` y
`vector_id` devolvieron cero duplicados. Las seis consultas de aceptación se
ejecutaron en español y devolvieron cinco resultados cada una mediante E5
multilingüe y FAISS.

El run alojado de GitHub Actions `30784482168` verificó el commit del PR con
los jobs `Quality and unit tests` y `Docker and offline integration`, ambos en
estado `SUCCESS`. El PDF actualizado contiene el diagrama de arquitectura, el
desglose Bronze/Silver/Gold, tablas de contrato, idempotencia y duplicados, la
matriz de 20 requisitos y anexos visuales de las salidas Docker reales.
