# ADR-0001: Fuentes iniciales y prioridad de procedencia

- Estado: aceptada para diseño; implementación pendiente.
- Fecha: 2026-08-02.

## Contexto

El producto necesita evidencia científica multilingüe y recursos documentales sin claves, pagos ni scraping HTML. El mandato de velocidad establece tres adaptadores iniciales: PubMed, Europe PMC y OpenAlex. PubMed y Europe PMC se solapan; OpenAlex mejora cobertura multilingüe pero su documentación actual indica que la API requiere una clave gratuita, mientras que la sonda anónima de esta fase obtuvo HTTP 200.

## Decisión

Implementar los tres adaptadores en fases posteriores, sin API keys:

1. PubMed para metadato biomédico curado y PMIDs.
2. Europe PMC para JSON `core`, abstracts y enriquecimiento de procedencia.
3. OpenAlex para descubrimiento multilingüe y metadatos académicos CC0, sujeto a preflight anónimo.

SciELO no se integra inicialmente. La prioridad determinista de registro principal es PubMed, Europe PMC y OpenAlex. Esto no elimina ninguna procedencia.

## Consecuencias

- El solapamiento PubMed/Europe PMC se resuelve en Silver por DOI/PMID, no evitando un adaptador útil.
- OpenAlex puede ser temporalmente no ejecutable si deja de aceptar anónimo; el lote debe degradarse sin frenar PubMed/Europe PMC y sin solicitar una clave.
- La licencia de OpenAlex cubre sus metadatos, no la obra subyacente; el texto/abstract sigue sujeto a su fuente.
- SciELO se reconsiderará sólo con endpoint público comprobado y sin retrasar el camino crítico.
