# Fuentes, licencias y reutilización

Revisión documental: 2026-08-02. Este documento es una guía técnica y no
asesoría legal. Las condiciones de cada fuente y de cada publicación pueden
cambiar; deben revisarse antes de redistribuir contenido.

## Política del repositorio

BBFS conserva respuestas reales sólo localmente y publica código, contratos,
manifests, checksums y evidencia agregada. No versiona PDFs, texto completo,
respuestas Bronze ni bases de datos. La licencia MIT del repositorio cubre el
código BBFS y no relicencia contenido de terceros.

## PubMed / NCBI

- Interfaz: [NCBI E-utilities](https://www.ncbi.nlm.nih.gov/books/NBK25497/).
- Política: [NCBI Website and Data Usage Policies](https://www.ncbi.nlm.nih.gov/home/about/policies/).
- NCBI indica un máximo anónimo general de tres solicitudes por segundo y pide
  no sobrecargar sus sistemas. BBFS usa límites inferiores y un User-Agent.
- NLM no reclama copyright sobre los abstracts de PubMed, pero los autores o
  editores sí pueden hacerlo. Por tanto, BBFS no trata un abstract como dominio
  público ni lo publica automáticamente.
- PubMed ofrece citas y abstracts, no el texto completo de los artículos.

Campos admitidos en documentación pública: PMID, DOI, título, autores, fecha,
revista, idioma, URL permanente y métricas agregadas. Los payloads y abstracts
completos permanecen fuera de Git y de los artifacts allowlisted.

## Europe PMC

- Interfaz: [Europe PMC RESTful Web Service](https://europepmc.org/RestfulWebService).
- La API documenta JSON/XML y metadatos como identificadores, títulos,
  abstracts, fechas, MeSH y enlaces de acceso.
- La documentación/implementación del servicio se presenta bajo Apache 2.0,
  pero eso no concede una licencia uniforme sobre cada publicación o abstract.
- Los campos de acceso abierto y licencia se conservan cuando existen; en su
  ausencia no se presume permiso de redistribución.

BBFS consume sólo `search` y metadatos/resúmenes necesarios. No descarga full
text, material suplementario, PDFs ni imágenes.

## OpenAlex

- Interfaz: [OpenAlex Developers](https://developers.openalex.org/).
- Política abierta: [OpenAlex pricing and data license](https://help.openalex.org/hc/en-us/articles/24397762024087-Pricing).
- OpenAlex declara su dataset como CC0 y permite usar y distribuir sus
  metadatos. Los límites y características del servicio API pueden variar.
- Los PDFs o contenidos enlazados conservan el copyright y la licencia de su
  publicación original; BBFS no los descarga.

El proyecto conserva OpenAlex ID, DOI, título, autores, fecha, idioma, URL,
conceptos y abstract reconstruido cuando la respuesta lo ofrece.

## Modelo de embeddings

- Modelo: [intfloat/multilingual-e5-small](https://huggingface.co/intfloat/multilingual-e5-small).
- La ficha del modelo declara licencia MIT, 94 idiomas, dimensión 384 y límite
  de 512 tokens.
- Los pesos se descargan a una caché local/CI y no se versionan ni se publican
  como artifact.

## Código BBFS y dependencias

El código propio se distribuye bajo [MIT](../LICENSE). Las dependencias fijadas
en `requirements.lock` conservan sus licencias individuales. La presencia de
una dependencia en el lock no significa que sus autores respalden este
proyecto. Un inventario legal completo de dependencias transitivas permanece
fuera del alcance técnico de esta fase.

## Decisión de publicación

| Contenido | Git público | Artifact live | Almacenamiento local |
| --- | --- | --- | --- |
| Código, SQL, documentación | Sí | No necesario | Sí |
| Fixtures inequívocamente sintéticos | Sólo bajo `tests/fixtures/synthetic/` | No | Sí |
| Manifests y checksums reales | No como ejecución local | Sí, 14 días | Sí |
| Evidencia agregada | No, es generada | Sí, 14 días | Sí |
| Respuestas Bronze | No | No | Sí, ignoradas |
| Abstracts completos/PDFs/texto completo | No | No | Sólo lo mínimo permitido; PDFs y full text no se descargan |
| DuckDB, modelos y FAISS | No | No | Sí, ignorados |
