# Seguridad y privacidad

## Modelo de datos

BBFS procesa metadatos bibliográficos y resúmenes públicos. No solicita nombres,
cuentas, historiales de salud ni datos de bebés, cuidadores o usuarios. Las
consultas se ejecutan localmente y no se incorporan a la evidencia por defecto,
excepto las seis consultas de aceptación públicas y predeterminadas.

## Secretos y acceso externo

- No hay secretos obligatorios, API keys ni servicios pagados.
- `.env`, credenciales, claves privadas y formatos comunes de secretos están
  ignorados por Git.
- `scripts/check_repository_hygiene.py` inspecciona los archivos versionados y
  falla ante firmas comunes de tokens, archivos de credenciales, bases, modelos,
  índices o datos runtime.
- Los workflows declaran `permissions: contents: read` y no referencian
  `secrets.*`.
- Pull requests no llaman APIs live; sólo el workflow manual/semanal tiene red.

El escaneo por patrones reduce errores accidentales, pero no sustituye una
herramienta especializada de detección de secretos ni una revisión de historial.

## Separación de capas

- Bronze escribe bytes reales sin transformación y conserva un SHA-256.
- Silver verifica el checksum antes de leer, valida con Pydantic y escribe
  DuckDB dentro de transacciones.
- Gold sólo consulta filas con `source_type='real'` y valida que su índice y
  metadata coincidan.
- Las restricciones SQL y las pruebas negativas impiden insertar
  `source_type='synthetic'` en tablas productivas.

Los fixtures artificiales viven exclusivamente en
`tests/fixtures/synthetic/`. La integración usa `tmp_path`, un batch vacío
válido y bloqueo de red; no carga registros artificiales ni produce evidencia.

## Archivos públicos y artifacts

Git sólo debe contener código, SQL, documentación, tests, fixtures claramente
artificiales y marcadores `.gitkeep`. Se excluyen:

- respuestas Bronze y fallos reales;
- DuckDB y archivos WAL;
- modelos y cachés;
- embeddings e índices FAISS;
- evidencia generada localmente;
- `.env`, credenciales y notebooks ejecutados.

El E2E live usa una allowlist de artifacts. Retiene durante 14 días evidencia,
manifests y checksums; no publica payloads completos. Los manifests pueden
contener URLs, consultas internas, códigos HTTP y timestamps, pero no datos
personales aportados por usuarios.

## Contenedor y dependencias

- La imagen usa `python:3.11-slim` y un usuario no root con UID 10001.
- No instala CUDA ni expone puertos.
- Las dependencias Python están fijadas en `requirements.lock`.
- La integración CI usa `--network none`, filesystem de sólo lectura y un
  `tmpfs` acotado.
- La caché del modelo se mantiene separada de `data/` y no se publica.

Fijar versiones mejora reproducibilidad, pero no garantiza ausencia de
vulnerabilidades. Las versiones deben revisarse periódicamente y actualizarse
con pruebas completas.

## Respuesta a incidentes

Si se detecta un secreto o dato indebido:

1. detener workflows y revocar la credencial en el proveedor;
2. retirar el archivo del árbol y, si procede, del historial Git;
3. borrar artifacts afectados;
4. ejecutar el escaneo de higiene y todas las pruebas;
5. documentar el alcance sin copiar el secreto en issues, logs o commits.

Si aparece un sintético en una ruta productiva, la ejecución es inválida: se
deben eliminar las salidas regenerables, corregir el límite y repetir desde
Bronze real.
