# PRD — baby-first-steps-medallion

## Producto

`baby-first-steps-medallion` es un sistema local que recopilará, validará, preservará e indexará metadatos y resúmenes de publicaciones sobre desarrollo temprano, juego, interacción y materiales para niñas y niños de **0 a 36 meses**.

Su salida será recuperación documental. No es diagnóstico, tratamiento, prescripción, consejo médico personalizado ni recomendación de seguridad de juguetes o actividades.

## Usuarios y experiencia objetivo

- Personas que buscan documentación sobre estimulación temprana, juego y desarrollo.
- Todas las consultas funcionales, ejemplos y demostraciones se expresarán **únicamente en español**.
- El corpus será **bilingüe**: se podrán adquirir registros en español e inglés y expandir internamente conceptos españoles a términos ingleses.
- El ranking propuesto por defecto favorece evidencia científica y, después, recursos prácticos claramente etiquetados. Este orden queda pendiente del checkpoint humano final.

## Alcance temático

- Estimulación temprana y juego sensorial.
- Motricidad gruesa y fina.
- Lenguaje y lectura compartida.
- Música y movimiento.
- Interacción cuidador-bebé y desarrollo socioemocional.
- Materiales de juego apropiados y evidencia sobre seguridad, sin sustituir normas locales ni fabricantes.

## Requisitos funcionales futuros

1. Ingerir respuestas reales de PubMed, Europe PMC y OpenAlex con consultas de adquisición españolas e inglesas.
2. Conservar cada respuesta Bronze byte a byte y asociarla a fuente, consulta, URL, HTTP, fecha y hash sin transformar su contenido.
3. Validar y normalizar sólo en Silver con Pydantic v2; enviar fallos reales a una cuarentena auditable.
4. Conservar procedencia completa y una entidad canónica por DOI/PMID/ID estable según `docs/data-contract.md`.
5. Cargar Silver mediante staging y UPSERT en DuckDB, con idempotencia estricta.
6. Crear Gold y un índice FAISS incremental únicamente con registros Silver válidos.
7. Responder las consultas de aceptación en español y exponer evidencia generada por código.

## Requisitos no funcionales

- Ejecución local y gratuita; Docker Compose llegará después del flujo local probado.
- Sin API keys ni servicios de pago. OpenAlex tendrá una preprueba anónima obligatoria y no se ejecutará si deja de aceptar acceso sin clave.
- Sin scraping de HTML, navegador headless, PDFs ni texto completo protegido.
- No versionar respuestas descargadas, bases DuckDB, modelos, embeddings ni FAISS.
- Mantener payloads reales ignorados por Git y usar artifacts de CI con retención acotada cuando sea necesario.
- Producir métricas y evidencia mediante código ejecutado, no por inspección manual.

## Integridad de datos

- Bronze es inmutable: el archivo es el cuerpo de respuesta original en bytes; el manifiesto es un archivo distinto.
- Toda transformación pertenece a Silver, nunca a Bronze.
- Los datos sintéticos sólo pueden existir bajo `tests/fixtures/synthetic/`, ser inequívocamente artificiales y cargarse exclusivamente desde pruebas.
- Debe existir una salvaguarda automatizada que falle si una tabla, evidencia o ejecución productiva contiene `source_type='synthetic'`.

## Fuera de alcance de esta fase

No se implementan aún pipeline, `src/`, modelos Pydantic, DuckDB, FAISS, Docker, Docker Compose, CI, API, interfaz o datos persistentes.
