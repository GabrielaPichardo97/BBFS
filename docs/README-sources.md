# Ejemplos de fuentes Bronze

Esta guía muestra cómo el paso Bronze adquiere respuestas reales de PubMed,
Europe PMC y OpenAlex. Los ejemplos usan el perfil `motor_sensory`, con consultas
internas en español e inglés. La interfaz final del producto seguirá siendo sólo
en español.

Los cuerpos devueltos por las APIs no se incluyen aquí ni se versionan. Una
ejecución real los guarda, sin transformarlos, en `data/bronze/<batch_id>/`, que
está ignorado por Git.

## Ejecutar las tres fuentes

```powershell
baby-first-steps ingest `
  --sources pubmed,europe_pmc,openalex `
  --profiles motor_sensory `
  --max-records-per-source 20
```

El límite se distribuye entre los perfiles seleccionados. Con un único perfil,
cada fuente recibe el límite completo. El resultado contiene `manifest.json`,
`checksums.sha256` y `failures.jsonl`; cada payload exitoso tiene también un
`request_XXXX.meta.json` asociado.

## PubMed E-utilities

PubMed requiere dos respuestas Bronze: una búsqueda ESearch JSON que crea el
historial del servidor, seguida de EFetch XML. Bronze sólo lee los identificadores
de historial de ESearch para construir la segunda URL; no extrae ni normaliza
documentos.

```text
GET https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi
  ?db=pubmed
  &term=("estimulación sensorial bebés" OR "desarrollo motor lactantes" OR
        "sensory play infant development" OR "fine motor activities infants toddlers")
  &retmax=20
  &retmode=json
  &usehistory=y
  &sort=relevance
```

Con `WebEnv` y `query_key` recibidos en ESearch, el adaptador solicita:

```text
GET https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi
  ?db=pubmed
  &WebEnv=<historial-recibido>
  &query_key=<clave-recibida>
  &retstart=0
  &retmax=20
  &retmode=xml
```

El lote conserva `response_0001.json` y `response_0002.xml`. La pista de
identidad futura es `PMID`; la extracción de PMIDs pertenece a Silver.

## Europe PMC REST

Europe PMC se adquiere en una única respuesta JSON por perfil y página:

```text
GET https://www.ebi.ac.uk/europepmc/webservices/rest/search
  ?query="estimulación sensorial bebés" OR "desarrollo motor lactantes" OR
         "sensory play infant development" OR "fine motor activities infants toddlers"
  &format=json
  &resultType=core
  &pageSize=20
  &cursorMark=*
```

El lote conserva `europe_pmc/response_0001.json`. La pista de identidad futura
es `source:id`; los posibles PMID, DOI, abstract, idioma y términos se manejan
recién en Silver.

## OpenAlex REST

OpenAlex recibe una consulta de texto libre con los términos internos del perfil:

```text
GET https://api.openalex.org/works
  ?search=estimulación sensorial bebés desarrollo motor lactantes sensory play
          infant development fine motor activities infants toddlers
  &per-page=20
```

El lote conserva `openalex/response_0001.json`. La pista de identidad futura es
el identificador de obra OpenAlex; la posible reconstrucción de abstracts y la
normalización de DOI no se hacen en Bronze.

## Límites y seguridad de transporte

- No se usan API keys, PDFs, scraping HTML ni texto completo.
- Cada fuente tiene un limitador independiente; la configuración inicial usa
  hasta 3 solicitudes por segundo para PubMed y hasta 2 para Europe PMC y
  OpenAlex.
- Las respuestas `429`, `500`, `502`, `503` y `504`, además de timeouts, se
  reintentan hasta tres veces con backoff exponencial, jitter y `Retry-After`.
- El `User-Agent` identifica a `baby-first-steps-medallion`.
- Los payloads se escriben primero en un temporal y se renombran atómicamente.
  Si ya existe el mismo nombre, sólo se acepta cuando el SHA-256 coincide.

## Reanudar

Si un lote conserva fallos parciales, la misma configuración puede reintentarse
sin volver a descargar payloads ya válidos:

```powershell
baby-first-steps ingest --resume <batch_id>
```

La reanudación verifica el hash de cada archivo existente antes de reutilizarlo.
Los datos sintéticos no son una opción de la CLI y no pueden entrar a Bronze.
