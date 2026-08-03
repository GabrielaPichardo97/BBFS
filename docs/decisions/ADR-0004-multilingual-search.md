# ADR-0004: Recuperación bilingüe y consulta española

- Estado: aceptada e implementada para Gold.
- Fecha: 2026-08-02.

## Decisión

Adquirir documentos en español e inglés mediante expansiones internas, pero aceptar y demostrar consultas de usuario sólo en español. Gold usa
`intfloat/multilingual-e5-small` en CPU, con `query:` para la consulta y
`passage:` para el documento. La versión efectiva del modelo queda registrada
en DuckDB junto con cada embedding y el estado del índice.

El ranking por defecto propuesto favorece evidencia científica antes de recursos prácticos. Las señales futuras incluirán tipo de publicación, presencia de abstract, correspondencia de edad, idioma, procedencia y trazabilidad; no harán afirmaciones médicas ni de seguridad.

## Consecuencias

- La recuperación semántica se verifica con seis consultas españolas y una
  revisión manual estructurada por consulta. No se declara relevancia a partir
  de un umbral automático ni se inventa una métrica de calidad.
- Una evolución posterior puede hacer benchmark o ajustar ranking, pero no
  cambia los prefijos E5 ni permite consultas de usuario en inglés.
- El idioma de la interfaz no depende del idioma del documento recuperado.
