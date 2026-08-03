# ADR-0003: Clave canónica y procedencia múltiple

- Estado: aceptada para diseño.
- Fecha: 2026-08-02.

## Decisión

Usar DOI normalizado, después PMID, ID OpenAlex y finalmente `(source_name, source_record_id)` como clave natural. No se deduplica por título, abstract, URL temporal, posición de búsqueda ni hash de payload.

Cuando DOI o PMID coinciden, crear una sola entidad canónica y conservar una procedencia por fuente/registro/payload. El registro principal se elige PubMed > Europe PMC > OpenAlex y las ausencias se complementan con procedencia explícita.

## Consecuencias

- El UPSERT es determinista e idempotente.
- Se conserva auditabilidad de cada fuente y se evita eliminar información útil.
- Una coincidencia de identificador posterior puede promover la clave sin perder alias ni procedencia anteriores.
