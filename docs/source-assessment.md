# Evaluación definitiva de fuentes

## Decisión

El diseño prevé tres adaptadores iniciales: **PubMed**, **Europe PMC** y **OpenAlex**. SciELO queda opcional y fuera del camino crítico.

La prioridad de recuperación no implica fusionar fuentes sin trazabilidad: toda coincidencia conserva sus filas de procedencia. La prioridad para un registro principal duplicado será PubMed, Europe PMC y OpenAlex, en ese orden; los campos de acceso abierto/licencia pueden complementarse desde otra procedencia sin reemplazar su origen.

## Consultas de adquisición

| Perfil | Consultas internas iniciales |
| --- | --- |
| `motor_sensory` | `estimulación sensorial bebés`; `desarrollo motor lactantes`; `sensory play infant development`; `fine motor activities infants toddlers` |
| `language_interaction` | `estimulación del lenguaje bebés`; `lectura compartida desarrollo infantil`; `shared reading infant language development`; `caregiver child interaction language` |
| `music_play_materials` | `música movimiento primera infancia`; `materiales de juego desarrollo infantil`; `music movement early childhood development`; `play materials infant development` |

Estas no son consultas de usuario. Los adaptadores pueden traducir o combinar términos para la sintaxis de cada catálogo, pero deben registrar en el manifest tanto el perfil como la expresión enviada. La búsqueda final permanece en español.

## Pruebas pequeñas reales

Se ejecutaron tres consultas de los perfiles con hasta tres resultados por consulta. Las métricas son sólo de la muestra indicada y no se extrapolan a los catálogos. Los cuerpos recibidos por `source_probe.py` para PubMed/Europe PMC se dejaron bajo `tmp/source_probe/`, ignorado por Git; OpenAlex y SciELO se inspeccionaron sólo en memoria.

| Fuente | HTTP y latencia observada | Muestra útil | Campos observados | Limitación relevante |
| --- | --- | --- | --- | --- |
| PubMed E-utilities | 200; búsqueda 420.9 ms y EFetch 806.3 ms en la consulta inglesa | 3 registros para `shared reading infant language development`; las dos expansiones españolas sin acentos enviadas por la sonda devolvieron 0 | Título, abstract, idioma, DOI, PMID y fecha: 100%; autores: 66.7%; MeSH: 100% | Las consultas españolas textuales no fueron efectivas en esta muestra; usar expansión inglesa/MeSH sin cambiar la interfaz española. |
| Europe PMC REST | 200; 975.4–1,267.7 ms | 9 registros | Título, DOI, PMID y fecha: 100%; abstract: 88.9%; autores: 88.9%; licencia: 77.8%; 1/9 español y 8/9 inglés | Consulta libre amplia: puede recuperar contenido clínico o fuera de edad objetivo; Silver debe conservar población y aplicar reglas de alcance. |
| OpenAlex REST | 200 sin clave; 689.2–2,015.1 ms | 9 registros | Título, autores, fecha, URL y keywords: 100%; abstract invertido: 88.9%; sin abstract: 11.1%; DOI: 77.8%; PMID: 11.1%; idioma: 3/9 es, 4/9 en, 2/9 vacío | La documentación actual declara API key gratuita; el acceso anónimo funcionó en esta prueba, pero debe verificarse antes de cada ejecución. |
| SciELO | OAI histórico Brasil: 404 HTML; OAI Books: error SSL por certificado expirado | 0 registros válidos | No evaluable | No se confirmó una interfaz programática de descubrimiento estable que no sea HTML. |

Ejemplos reales de la muestra OpenAlex incluyen *Desarrollo integral pedagógico en bebés de cero a doce meses por medio de la estimulación sensorial* y *Shared reading with preverbal infants and later language development*. Esto aporta la cobertura española complementaria que no apareció en la muestra de PubMed/Europe PMC.

## Interfaces y límites

| Fuente | Endpoint base y formato | Paginación | Límite conocido o política inicial | Identidad y derechos |
| --- | --- | --- | --- | --- |
| PubMed | `esearch.fcgi` JSON + `efetch.fcgi` XML | `retstart`/`retmax` o History Server | NCBI documenta hasta 3 solicitudes/s sin API key; usar 2/s | PMID nativo, DOI frecuente; abstracts pueden estar protegidos. |
| Europe PMC | `https://www.ebi.ac.uk/europepmc/webservices/rest/search`, JSON `resultType=core` | `cursorMark` / `nextCursorMark` | No se halló cifra oficial en la documentación revisada; usar 2/s | `source:id`, PMID/DOI frecuentes; licencia variable por registro. |
| OpenAlex | `https://api.openalex.org/works`, JSON | cursor en la API de listas | Acceso anónimo observado, sin tasa anónima publicada en la documentación actual; usar 1/s y preflight HTTP 200 | ID `https://openalex.org/W…`, DOI/PMID opcionales; metadatos OpenAlex CC0, obra subyacente no necesariamente. |
| SciELO | No seleccionado | N/A | N/A | Opcional; no iniciar integración hasta validar endpoint. |

Fuentes de documentación: [NCBI E-utilities](https://www.ncbi.nlm.nih.gov/books/NBK25497/), [Europe PMC REST](https://europepmc.org/RestfulWebService), [OpenAlex Developers](https://developers.openalex.org/), [SciELO Search](https://search.scielo.org/) y [SciELO Books OAI-PMH](https://books.scielo.org/en/availability-and-interoperability/).

## Regla de disponibilidad de OpenAlex

El adaptador se implementará sin parámetro ni secreto de API. Antes de escribir Bronze realizará una solicitud mínima anónima. Si la fuente devuelve autenticación requerida, cuota agotada o un estado no exitoso, el lote OpenAlex queda marcado como no ejecutado y el proceso continúa con PubMed/Europe PMC; no se añadirá una API key para evitarlo. Esta regla protege simultáneamente la decisión de tres adaptadores y la prohibición de credenciales.

## SciELO

La ayuda oficial de búsqueda expone campos como título, abstract, palabras clave, idioma y DOI, pero no confirmó un API de resultados soportado. Se probó el endpoint OAI brasileño histórico y falló con 404; el endpoint OAI de Books presentó un certificado expirado. No se usará HTML ni se intentará corregir esa infraestructura. Su posible cobertura en español se reevalúa después de que los tres adaptadores críticos funcionen.
