# ADR-0004: Recuperación bilingüe y consulta española

- Estado: aceptada para diseño; modelo pendiente de benchmark.
- Fecha: 2026-08-02.

## Decisión

Adquirir documentos en español e inglés mediante expansiones internas, pero aceptar y demostrar consultas de usuario sólo en español. Construir Gold con un modelo multilingüe de recuperación asimétrica; candidato inicial: `intfloat/multilingual-e5-base`, usando `query:` para la consulta y `passage:` para el documento.

El ranking por defecto propuesto favorece evidencia científica antes de recursos prácticos. Las señales futuras incluirán tipo de publicación, presencia de abstract, correspondencia de edad, idioma, procedencia y trazabilidad; no harán afirmaciones médicas ni de seguridad.

## Consecuencias

- Se requiere benchmark posterior con las ocho consultas españolas antes de fijar el modelo o pesos.
- No se descargan modelos, no se generan embeddings y no se crea FAISS durante esta fase.
- El idioma de la interfaz no depende del idioma del documento recuperado.
