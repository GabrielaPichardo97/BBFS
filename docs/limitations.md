# Limitaciones

## Cobertura documental

- Las fuentes iniciales son catálogos académicos. Pueden ofrecer evidencia
  científica pero no necesariamente instrucciones prácticas listas para usar.
- PubMed y Europe PMC tienen solapamiento importante. La deduplicación por DOI o
  PMID reduce duplicados, pero no resuelve todas las versiones de una obra.
- OpenAlex amplía idiomas y disciplinas; la calidad y completitud de abstracts,
  idioma, autores y licencias varía por registro.
- SciELO no está integrado. La cobertura regional en español puede ser menor de
  la deseada hasta validar una interfaz oficial estable.

## Recuperación y ranking

- `multilingual-e5-small` limita sus entradas a 512 tokens y produce similitud
  semántica, no una evaluación clínica ni de seguridad.
- Las consultas finales son sólo en español. El corpus inglés puede recuperarse
  mediante el espacio multilingüe, con pérdida variable según tema y redacción.
- No existe un umbral universal de relevancia. La posición relativa requiere
  revisión humana y no demuestra eficacia de una actividad.
- El ranking todavía no implementa una ponderación editorial separada entre
  evidencia científica y recursos prácticos.

## Calidad y edad

- El rango de producto es 0–36 meses, pero no todos los registros incluyen una
  edad explícita o suficientemente precisa.
- La presencia de términos como “infant” o “toddler” no valida por sí sola que
  una actividad sea adecuada para una niña o niño concreto.
- Materiales cotidianos pueden implicar riesgos de asfixia, toxicidad, alergia
  o lesión. El sistema no certifica productos ni reemplaza instrucciones de
  fabricantes, normas locales o supervisión adulta.

## Derechos y contenido

- Acceso gratuito no equivale a permiso de redistribución. Los abstracts de
  PubMed o Europe PMC pueden estar protegidos por autores o editoriales.
- El repositorio no versiona respuestas Bronze, PDFs ni texto completo. El
  workflow live publica únicamente manifests, checksums y evidencia agregada.
- La licencia MIT cubre el código BBFS, no concede derechos sobre documentos de
  terceros, metadatos incorporados ni modelos externos.

## Operación

- Las APIs y sus límites pueden cambiar sin aviso. El E2E live es semanal y no
  garantiza disponibilidad continua.
- FAISS y el modelo requieren CPU, memoria, disco y una descarga inicial. No se
  ofrece GPU ni servicio remoto.
- DuckDB y FAISS son locales: no hay alta disponibilidad, acceso multiusuario ni
  recuperación administrada.
- GitHub Actions hosted no se puede reproducir exactamente en todos los equipos;
  los comandos locales validan contratos, pero el estado hosted debe revisarse
  después de cada push.

## Uso informativo

Los resultados son referencias documentales. No constituyen diagnóstico,
tratamiento, prescripción, consejo médico personalizado ni recomendación de
seguridad. Ante dudas de desarrollo o seguridad se debe acudir a profesionales
cualificados y a las normas aplicables.
