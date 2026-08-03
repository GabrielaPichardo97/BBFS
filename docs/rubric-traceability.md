# Trazabilidad de la rúbrica

Fecha de verificación local: 2026-08-02. `PASS` significa que el criterio se
ejecutó; `NOT VERIFIED` evita convertir una revisión visual o una expectativa
de GitHub en evidencia. Los payloads, bases, modelos, índices y reportes
generados permanecen fuera de Git.

| Requisito | Implementación | Prueba | Comando | Evidencia | Resultado | Estado |
| --- | --- | --- | --- | --- | --- | --- |
| remoto corresponde a BBFS | `origin` conservado | inspección Git | `git remote -v` | URL de fetch/push | `GabrielaPichardo97/BBFS.git` | PASS |
| repositorio visible públicamente | repositorio GitHub existente | API pública anónima | `Invoke-RestMethod https://api.github.com/repos/GabrielaPichardo97/BBFS` | `private=false`, rama `main` | respuesta HTTP válida sin autenticación | PASS |
| licencia compatible con repositorio público | `LICENSE` MIT y metadato de paquete MIT | lectura y prueba de contrato | `pytest tests/unit/test_container_contract.py` | archivo y `pyproject.toml` | licencia permisiva; GitHub aún no la detecta en `main` | PASS |
| instalación reproducible en Python 3.11 | `requirements.lock` y paquete editable sin dependencias implícitas | instalación local y build Docker | `pip install -r requirements.lock` | lock versionado | dependencias fijadas | PASS |
| formato y lint | Ruff | ejecución local | `python -m ruff check src tests scripts/check_repository_hygiene.py` | salida de Ruff | sin incidencias | PASS |
| type checking | mypy | ejecución local | `python -m mypy src` | salida de mypy | 25 archivos sin incidencias | PASS |
| pruebas unitarias y cobertura | pytest + Coverage.py | ejecución local | `coverage run --source=baby_first_steps_medallion -m pytest tests/unit && coverage report` | `coverage.xml` local ignorado | 74 pruebas; 83% total | PASS |
| CI rápida en PR y push a `main` | `.github/workflows/ci.yml` | contrato YAML automatizado | `pytest tests/unit/test_workflow_contract.py` | workflow versionado | eventos, caché y jobs requeridos presentes | PASS |
| PR CI sin APIs live | job Docker con `--network none`; no ejecuta `ingest` ni `demo` | contrato automatizado | `pytest tests/unit/test_workflow_contract.py` | aserciones sobre el workflow | ninguna llamada live configurada | PASS |
| Compose válido | servicio `pipeline` | validación de Docker Compose | `docker compose config --quiet` | código de salida | configuración válida | PASS |
| imagen CPU y usuario no root | `Dockerfile`, UID 10001, imagen `bbfs-pipeline:local` | build y contrato | `docker compose build` | salida del build e inspección | build correcto; imagen Linux amd64 con usuario `app` | PASS |
| doctor dentro del contenedor | comando CLI real | smoke test Docker | `docker compose run --rm --no-deps pipeline doctor` | salida del doctor | Python 3.11.15; rutas, configuración, DuckDB y FAISS correctos | PASS |
| integración sin red | Silver vacío idempotente y fallo Gold explícito en `tmp_path` | Docker con red deshabilitada | `docker run --network none ... pytest tests/integration -m integration` | salida pytest | 1 prueba aprobada; cero conexiones permitidas | PASS |
| no datos sintéticos en producción | barreras Bronze/Silver/Gold/evidencia y escáner | pruebas negativas + escaneo publicable | `pytest tests/unit/test_synthetic_guard.py tests/unit/test_repository_hygiene.py` | consultas y rutas verificadas | cero rutas publicables infractoras | PASS |
| no secretos ni datos/modelos generados publicables | `scripts/check_repository_hygiene.py` y `.gitignore` | escaneo Git y rutas productivas vacías dentro de Docker | `python scripts/check_repository_hygiene.py --mode publishable` | salida del escáner | 98 archivos Git y 105 archivos Docker, sin incidencias | PASS |
| workflow live acotado | `.github/workflows/e2e-live.yml` | contrato YAML automatizado | `pytest tests/unit/test_workflow_contract.py` | timeout, concurrency, permisos, caché, agenda | contrato válido | PASS |
| artifacts live mínimos durante 14 días | allowlist de evidencia, manifests y checksums | contrato automatizado | `pytest tests/unit/test_workflow_contract.py` | configuración `upload-artifact` | payloads `response_*` excluidos | PASS |
| resumen de aceptación en GitHub | lector de `evidence.json` escribe `$GITHUB_STEP_SUMMARY` | contrato automatizado | `pytest tests/unit/test_workflow_contract.py` | paso del workflow | implementación presente | PASS |
| ejecución alojada de CI | GitHub Actions | run en GitHub | abrir PR o hacer push a `main` | checks alojados | no ejecutado en esta rama durante la entrega | NOT VERIFIED |
| ejecución alojada live | GitHub Actions manual/semanal | run `workflow_dispatch` o schedule | ejecutar `E2E live` en GitHub | artifact y Job Summary | no ejecutado durante esta entrega | NOT VERIFIED |
| dos batches Bronze reales | demo productiva | evidencia generada por código | `docker compose run --rm pipeline demo --fresh --yes` | `artifacts/evidence.json` ignorado | evidencia local previa: `two_real_bronze_batches=PASS` | PASS |
| idempotencia Silver/Gold | staging, UPSERT e índice incremental | dos corridas sobre el mismo batch | comando `demo` | tabla de idempotencia en evidencia | evidencia local previa: `idempotency=PASS` | PASS |
| seis búsquedas en español | E5 multilingüe + FAISS | demo y evidencia | comando `demo` | seis resultados por consulta en evidencia | evidencia local previa: `six_spanish_searches=PASS` | PASS |
| licencias y restricciones de fuentes | política conservadora por fuente | revisión de documentación oficial | revisar `docs/source-licenses.md` | enlaces y reglas por campo | metadatos documentados; no se publican payloads/texto completo | PASS |
| auditoría jurídica exhaustiva de cada registro | fuera del alcance técnico | revisión jurídica humana | no aplica | dictamen por registro/editor | no realizada | NOT VERIFIED |

## Interpretación

- Los `PASS` funcionales del demo provienen del último reporte Docker local y
  no sustituyen una nueva ejecución del workflow alojado.
- La integración usa un batch vacío válido en un directorio temporal de pytest;
  bloquea la red y no carga registros artificiales en Silver, Gold o evidencia.
- El workflow live no publica respuestas Bronze completas. Su allowlist sólo
  incluye evidencia agregada, manifests y checksums durante 14 días.
