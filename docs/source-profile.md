# Perfil de fuente: Europe PMC REST API

## Decisión y propósito

Fuente recomendada para `baby-first-steps-medallion`: **Europe PMC REST API**. Se usará sólo para metadatos y abstracts/descripciones disponibles, nunca para descargar PDFs ni texto completo durante la ingesta ordinaria.

Documentación oficial: <https://europepmc.org/RestfulWebService>. La documentación describe la búsqueda REST, los formatos JSON/XML/DC y `resultType=core`, que expone abstract y términos MeSH cuando existen.

## Endpoint y contrato de consulta

```text
GET https://www.ebi.ac.uk/europepmc/webservices/rest/search
  ?query=<consulta-interna-codificada>
  &format=json
  &resultType=core
  &pageSize=<tamano-lote>
  &cursorMark=<cursor>
```

- Autenticación: no requerida.
- Formato Bronze futuro: el cuerpo **JSON** exacto de cada página, sin transformación.
- Formato de lectura: `resultList.result`; la respuesta incluye `hitCount` y, cuando aplica, `nextCursorMark`.
- Paginación: iniciar con `cursorMark=*` y persistir el `nextCursorMark` de la respuesta; si no hay cursor, tratar la página como terminal. Mantener un `pageSize` moderado y nunca inferir que `hitCount` cabe en memoria.
- Límite de frecuencia: la página oficial consultada no publica una cifra numérica. La implementación inicial debe ser conservadora: máximo dos solicitudes por segundo, timeout de 15 segundos, hasta tres intentos, backoff exponencial y respeto de `Retry-After`.
- Identificación: enviar un `User-Agent` con nombre y versión de la herramienta. Añadir un contacto de mantenimiento antes de producción.

## Consultas

La interfaz del producto acepta sólo las cadenas españolas de [query-catalog.yml](query-catalog.yml). La ingesta construirá internamente expresiones bilingües a partir de `internal_expansion_es` e `internal_expansion_en`; por ejemplo:

```text
Consulta visible: lectura compartida para estimular el lenguaje
Expansión interna: shared reading OR shared book reading OR lectura compartida OR desarrollo del lenguaje
```

Las expresiones exactas deben quedar en el manifest de cada ejecución. La muestra de Fase 0 usó tres expansiones inglesas de alta señal para perfilar la fuente; no son cambios a la interfaz en español.

## Campos que interesan

| Propósito | Campos Europe PMC | Disponibilidad en muestra de 15 |
| --- | --- | --- |
| Identidad | `source`, `id`, `pmid`, `doi` | `source`/`id`: 100%; PMID: 80.0%; DOI: 93.3% |
| Búsqueda semántica futura | `title`, `abstractText`, `keywordList`, `meshHeadingList` | título: 100%; abstract: 93.3%; keywords: 66.7%; MeSH: 53.3% |
| Filtros y trazabilidad | `language`, `firstPublicationDate`, `authorString`, `journalTitle` | idioma: 86.7%; fecha/enlace/autores: no deben asumirse sólo por la muestra |
| Reutilización | `license`, enlaces de texto completo si existen | licencia: 46.7%; el enlace no concede derecho sobre texto completo |

URL permanente recomendada: `https://europepmc.org/article/{source}/{id}`. No usar un enlace temporal de resultados como identidad.

## Clave natural

Clave garantizada para esta fuente: **`(source_name, external_id)`**, donde `source_name = "europe_pmc"` y `external_id = "{source}:{id}"`.

Ejemplo: `("europe_pmc", "MED:36404647")`. `pmid` se conserva como identificador alternativo y puede ser la clave de coincidencia cuando exista, pero no sustituye la clave primaria porque 20.0% de la muestra no lo traía. Normalizar DOI a minúsculas, sin prefijo `https://doi.org/`, sólo como índice de deduplicación futuro.

Si alguna fase posterior añade otra fuente, detectar la misma obra por PMID idéntico y después por DOI normalizado. No implementar todavía reconciliación, precedencia ni fusión de registros.

## Muestra de Fase 0

Tres consultas internas, cinco resultados como máximo cada una, respondieron HTTP 200. La latencia observada de una consulta de control fue 1,048.3 ms. Los porcentajes siguientes son de esa muestra mínima, no estimaciones del catálogo completo:

| Consulta visible en español | Términos de ingesta probados | Título recuperado | Idioma | Abstract | Relevancia |
| --- | --- | --- | --- | --- | --- |
| actividades de estimulación temprana para bebés | `early childhood development AND infant` | *From theory to practice: Piloting a measure of fidelity for Infant and Early Childhood Mental Health Consultation.* | eng | Sí | Evidencia de contexto para desarrollo temprano; requiere un filtro posterior para no presentarlo como una actividad concreta. |
| lectura compartida para estimular el lenguaje | `shared reading AND infant` | *Shared book reading promotes experience-dependent autonomic synchrony in parent–preterm infant dyads* | eng | Sí | Coincide directamente con lectura compartida; la población prematura debe conservarse como matiz. |
| interacción entre cuidadores y bebés para el desarrollo socioemocional | `parent infant interaction AND social emotional` | *The power of the group - Group-based parenting programmes for disadvantaged parents and their infants: a realist review.* | eng | Sí | Aporta evidencia sobre programas de crianza e interacción; no debe mostrarse como recomendación individual. |

En las 15 respuestas: 13 tenían idioma marcado, y fueron 13/13 inglés y 0/13 español; dos no tenían campo de idioma. Esto demuestra recuperación inglesa y no demuestra cobertura española suficiente. Por ello el corpus previsto es bilingüe por diseño de consulta, pero debe registrar y monitorear `language` antes de prometer resultados en español.

## Problemas conocidos y límites

- La consulta de texto libre es amplia: puede recuperar desarrollo, salud mental o poblaciones fuera de 0–36 meses. Las reglas de alcance y edad pertenecen a fases posteriores.
- `abstractText`, `language`, DOI, PMID, términos y licencia no son obligatorios. Validar presencia antes de indexar y permitir cuarentena para errores reales.
- Europe PMC incluye registros de PubMed. La verificación de Fase 0 recuperó el PMID `36404647` de PubMed como `MED:36404647` en Europe PMC; no integrar ambos en paralelo.
- El acceso libre no equivale a licencia de texto completo. Conservar metadatos necesarios y aplicar la licencia por registro; no descargar ni versionar PDFs.
- La documentación no fijó un rate limit numérico en la página revisada. Mantener la política conservadora indicada arriba y registrar HTTP/latencia.

## Recomendación para fases posteriores

Para embeddings, evaluar sin descargar durante Fase 0 `intfloat/multilingual-e5-base`: modelo multilingüe de recuperación con prefijos asimétricos `query:` y `passage:`. El campo de pasaje debería ser `title + abstractText`, con `keywordList` y `meshHeadingList` como contexto opcional claramente separado. Se necesita benchmark posterior con las consultas canónicas en español antes de adoptarlo.
