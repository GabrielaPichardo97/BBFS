# Fase 0: viabilidad de fuentes

## Objetivo

Elegir la mínima fuente pública y reproducible para un corpus documental de `baby-first-steps-medallion` sobre desarrollo temprano (0–36 meses), con búsqueda de usuario exclusivamente en español. El resultado debe facilitar después dos lotes Bronze, validación, cuarentena, UPSERT, búsqueda semántica y automatización, sin implementar aún ninguna de esas capas.

## Identidad y restricciones verificadas

- Repositorio local: `BBFS`.
- `origin`: `https://github.com/GabrielaPichardo97/BBFS.git`; coincide con BBFS.
- Nombre visible que se documenta: `baby-first-steps-medallion`.
- Rama de esta fase: `codex/phase-0-source-discovery`.
- No se renombró el repositorio ni se modificó el remoto.
- Sin API keys obligatorias, pagos, scraping HTML, navegador headless ni PDFs/texto completo.
- Los resultados de la prueba son reales y pequeños. No se crearon ni se usaron registros sintéticos.

## Metodología

Se aplicaron primero los criterios obligatorios: acceso sin autenticación, interfaz pública documentada, identificador estable, título con abstract/descripción aprovechable y respuesta cruda almacenable. Sólo las fuentes que los superaron se puntuaron sobre 100.

El script [source_probe.py](../scripts/source_probe.py) ejecutó como máximo cinco resultados por intención y tres intenciones por fuente: desarrollo temprano, lectura compartida e interacción cuidador-bebé. Cada llamada usó timeout de 15 s, hasta tres intentos, backoff, `Retry-After`, `User-Agent` y un máximo de dos solicitudes por segundo. Las respuestas reales quedaron únicamente bajo `tmp/source_probe/`, ignorado por Git.

Las consultas mostradas al usuario no se cambiaron: el catálogo está en [query-catalog.yml](query-catalog.yml). Para perfilar fuentes inglesas se emplearon expansiones internas como `early childhood development AND infant`, `shared reading AND infant` y `parent infant interaction AND social emotional`.

## Fuentes evaluadas

| Fuente | Interfaz | Resultado de criterio obligatorio | Resultado |
| --- | --- | --- | --- |
| Europe PMC | REST, JSON/XML/DC | Pasa | Seleccionada. |
| PubMed | E-utilities: JSON + XML | Pasa | Válida, pero redundante con Europe PMC. |
| DOAJ | REST JSON | Pasa | Válida, pero no aporta respaldo demostrado. |
| BVS/LILACS | Sólo web pública confirmada | Falla | No se confirmó API/RSS/Atom/OAI-PMH de descubrimiento documentado. |
| SciELO | OAI-PMH de Books confirmado | Falla | No es un descubrimiento general de artículos temáticos para este alcance. |
| WHO IRIS | Búsqueda web de repositorio | Falla | No se confirmó endpoint soportado que evite HTML/API interna. |

Referencias oficiales revisadas: [NCBI E-utilities](https://www.ncbi.nlm.nih.gov/books/NBK25497/), [Europe PMC REST](https://europepmc.org/RestfulWebService), [DOAJ metadata](https://doaj.org/docs/faq/), [DOAJ OAI-PMH](https://doaj.org/docs/oai-pmh/), [LILACS](https://lilacs.bvsalud.org/), [SciELO Books OAI-PMH](https://books.scielo.org/en/availability-and-interoperability/) y [guía de IRIS](https://iris.who.int/static/pdf/IRIS_advanced_search.pdf).

## Pruebas y resultados observados

Los datos son porcentajes de una muestra mínima, no porcentajes de cada catálogo.

| Fuente | Muestra | Título | Abstract/descripción | Idioma | DOI | PMID | HTTP/latencia de control |
| --- | ---: | ---: | ---: | --- | ---: | ---: | --- |
| Europe PMC | 15 | 100.0% | 93.3% | 13/15 etiquetados; 0/13 es, 13/13 en | 93.3% | 80.0% | 200 / 1,048.3 ms |
| PubMed | 15 | 100.0% | 100.0% | 15/15 etiquetados; 0/15 es, 15/15 en | 100.0% | 100.0% | 200, 200 / 424.8 ms + 506.0 ms |
| DOAJ | 15 | 100.0% | 100.0% | 0/15 con campo idioma | 93.3% | 0.0% | 200 / 325.1 ms |

Los totales encontrados por intención fueron, respectivamente, Europe PMC: 126,662, 15,237 y 16,331; PubMed: 40,182, 264 y 1,166; DOAJ: 624, 8 y 27. Son conteos de búsqueda para las expresiones internas de prueba, no estimaciones de relevancia ni de cobertura del producto.

La matriz reproducible completa está en [source-scorecard.csv](source-scorecard.csv). Las puntuaciones fueron Europe PMC **79/100**, PubMed **78/100** y DOAJ **66/100**. Los demás fallaron criterios obligatorios y no son elegibles, por lo que no reciben puntuación competitiva.

## Solapamiento

Europe PMC incorpora múltiples catálogos, incluido PubMed. La comprobación de identidad con `EXT_ID:36404647 AND SRC:MED` devolvió exactamente un registro, con PMID `36404647` y título *Shared reading: Parental attitudes, practices and barriers in Turkey.*, previamente recuperado por PubMed. Los primeros cinco resultados por relevancia no coincidieron posición a posición, algo esperable por índices/ranking distintos, pero no es evidencia de cobertura complementaria. Integrar ambos obligaría a dos clientes, dos contratos y reconciliación sin valor proporcional.

## Evaluación semántica

Europe PMC puede recuperar evidencia inglesa para consultas visibles españolas usando expansiones internas bilingües. La muestra no mostró ningún registro español etiquetado: por tanto, la decisión de corpus es **bilingüe**, pero la cobertura española debe tratarse como objetivo verificable de fases posteriores, no como hecho probado. El modelo candidato futuro es `intfloat/multilingual-e5-base`, por su patrón asimétrico `query:`/`passage:`; no se descargó ni se comparó durante esta fase.

Los tres ejemplos concretos de recuperación y sus matices están documentados en [source-profile.md](source-profile.md). La futura presentación debe conservar población, edad, diseño del estudio y límites para no convertir evidencia documental en consejo médico individual.

## Copyright, datos y repositorio público

- Conservar sólo el metadato necesario, identificadores, URLs permanentes, idioma y licencias observadas.
- Los abstracts pueden tener restricciones de copyright aunque el registro sea accesible; Europe PMC exige respetar los términos de cada obra. No guardar ni publicar texto completo ni PDF.
- No versionar respuestas completas, bases de datos, payloads Bronze reales, embeddings, índices FAISS ni artifacts pesados. Guardarlos bajo rutas ignoradas como `data/`, `artifacts/` o `tmp/`, o como artifacts con retención acotada de GitHub Actions.
- Versionar únicamente código, manifiestos de ejemplo mínimos sin contenido protegido, hashes, configuración y evidencia agregada como esta. La documentación pública puede mostrar identificadores, estadísticas agregadas y títulos de muestra; debe evitar reproducir abstracts completos.
- DOAJ declara su metadato bajo CC0, pero eso no transfiere derechos sobre la obra descrita. Para Europe PMC, aplicar siempre la licencia/copyright de cada registro.

## Riesgos

1. La muestra inglesa no demuestra cobertura española. Mitigación futura: ejecutar y medir consultas internas españolas y bilingües, registrando idioma.
2. La recuperación libre puede traer población fuera de 0–36 meses, condiciones clínicas o intervenciones. Mitigación futura: reglas explícitas de inclusión/exclusión y presentación documental.
3. La licencia y el abstract no están siempre presentes. Mitigación futura: campos opcionales, validación y cuarentena de fallos reales, sin inventar datos.
4. Europe PMC no publicó un número de rate limit en la página de documentación revisada. Mitigación: empezar a 2 solicitudes/s, respetar reintentos y monitorizar HTTP/latencia.

## Recomendación final

```text
Fuente principal:
Europe PMC REST API

Fuente de respaldo:
ninguna

Clave natural:
(source_name, external_id), con external_id = "{source}:{id}"

Formato Bronze:
JSON

Campo futuro para embeddings:
title + abstractText; keywordList y meshHeadingList como contexto opcional

Motivo principal:
Entrega título y abstract frecuente en un único JSON documentado, sin autenticación, y evita duplicar PubMed.

Tiempo estimado de implementación:
2 horas

Riesgo principal:
La muestra recuperada fue predominantemente inglesa y no prueba aún cobertura española suficiente.

Decisión sobre corpus:
bilingüe.
```
