# ADR-0001: Selección de fuente documental inicial

- Estado: aceptada para Fase 0; pendiente de aprobación humana para iniciar el pipeline.
- Fecha: 2026-08-02.

## Contexto

El proyecto visible `baby-first-steps-medallion`, en el repositorio `BBFS`, necesita una fuente pública, gratuita y rápida de implementar para metadatos y abstracts sobre desarrollo y juego de 0 a 36 meses. Las consultas visibles son sólo en español; la expansión interna puede ser bilingüe. Esta decisión no autoriza almacenar PDFs, texto completo protegido ni datos sintéticos en rutas productivas.

## Fuentes consideradas

- Europe PMC REST API: JSON, una llamada de búsqueda con `resultType=core`, metadatos y abstracts frecuentes.
- PubMed E-utilities: interfaz estable, PMIDs nativos y metadatos ricos; requiere ESearch seguido de EFetch XML para el abstract.
- DOAJ article search API: JSON, metadatos CC0 de DOAJ y abstracts en la muestra; sin PMIDs y sin idioma/licencia por registro en la muestra.
- BVS/LILACS: descartada por no confirmar en el timebox una interfaz pública de búsqueda documentada y soportada, distinta de la web.
- SciELO: descartada; la interoperabilidad confirmada fue OAI-PMH de SciELO Books, no un endpoint general de descubrimiento temático de artículos adecuado para este caso.
- WHO IRIS: descartada para ingesta inicial; se confirmó búsqueda web/documentación de repositorio, no un endpoint público de descubrimiento documentado que evite HTML o una API interna de DSpace.

No se evaluó Crossref porque las seis candidatas de prioridad alta agotaron el cupo y ya existe una opción principal válida.

## Decisión

**Fuente principal: Europe PMC REST API.**

**Fuente de respaldo: ninguna.** PubMed está incluido de forma sustancial en Europe PMC; DOAJ no demostró valor adicional en español ni un campo de idioma utilizable en la muestra. Una segunda integración añadiría cliente, contratos, reconciliación y reglas de rate limit sin mejorar de forma comprobada esta fase.

## Razones

1. Una sola respuesta JSON `core` produce título, abstract y varios identificadores con menos código que el patrón XML de dos solicitudes de PubMed.
2. La muestra de 15 registros tuvo 100% título, 93.3% abstract, 93.3% DOI y 80.0% PMID.
3. La documentación es pública y el acceso no requiere API key.
4. La verificación puntual mostró que un resultado PubMed (`PMID 36404647`) se resuelve en Europe PMC como `MED:36404647`; no es una fuente complementaria suficiente.

## Consecuencias

- La clave natural será `(source_name, external_id)` con `("europe_pmc", "{source}:{id}")`; PMID y DOI normalizado serán índices de coincidencia futuros.
- Bronze futuro guardará cuerpos JSON sin modificar por página y un manifest con URL, consulta interna, cursor, HTTP, latencia y hash. No se versionarán esos cuerpos reales.
- Silver futuro validará los campos mínimos, normalizará DOI y preservará idioma/licencia/procedencia. Esta ADR no crea aún ningún modelo ni tabla.
- Gold futuro puede generar embeddings únicamente a partir de `title + abstractText` permitidos por la política de derechos; no se asume acceso a texto completo.
- Si posteriormente se considera un segundo origen, se debe demostrar con una nueva muestra cobertura española adicional, mapeo al mismo contrato y coste de integración de dos horas o menos.

## Alternativas descartadas

- **PubMed como principal:** excelente PMIDs y la mejor puntuación de evidencia biomédica, pero 78/100 frente a 79/100 y exige dos llamadas/XML. Se mantiene como referencia conceptual, no como fallback productivo.
- **DOAJ como respaldo:** 66/100. Sus metadatos tienen una política CC0 clara, pero los 15 registros de muestra no incluyeron idioma ni licencia por registro y se observó menor precisión temática.
- **BVS/LILACS, SciELO y WHO IRIS:** no pasan los criterios obligatorios de interfaz pública, estable y documentada para el descubrimiento que se necesita; no se usarán endpoints internos ni scraping.

## Estimación

Implementar el adaptador inicial de Europe PMC para Bronze (consulta paginada, raw JSON, manifest, límites y reintentos) se estima en **2 horas**. Esa estimación excluye Bronze/Silver/Gold completos, modelos, cuarentena, embeddings, FAISS, Docker y CI, que pertenecen a fases posteriores.
