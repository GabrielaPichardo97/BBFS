# Matriz de aceptación funcional

La demostración produce esta matriz desde código; no se completa manualmente.
La ejecución Docker conservada localmente en `artifacts/evidence.json` calculó
`PASS` para todos los criterios funcionales:

| Criterio calculado | Evidencia producida |
| --- | --- |
| entorno válido | `environment` |
| dos lotes Bronze reales | `two_real_bronze_batches` |
| reproceso idempotente | `idempotency` |
| ausencia de duplicados canónicos | `duplicates` |
| seis búsquedas en español | `six_spanish_searches` |
| ausencia de datos sintéticos en producción | `synthetic_safety` |

Los archivos de evidencia son derivados locales e ignorados por Git. Para
regenerarlos:

```bash
docker compose run --rm pipeline demo --fresh --yes
docker compose run --rm pipeline evidence
```

La trazabilidad de publicación, CI, pruebas y controles operativos está en
[`rubric-traceability.md`](rubric-traceability.md). Un estado `NOT VERIFIED`
allí significa que el criterio no fue ejecutado en el entorno alojado, no que
se haya declarado correcto por inspección.

## Consultas de aceptación, todas en español

1. actividades sensoriales con diferentes texturas para un bebé
2. materiales cotidianos para desarrollar la motricidad fina
3. juegos entre cuidadores y bebés para estimular el lenguaje
4. lectura compartida durante los primeros años de vida
5. música y movimiento para mejorar la coordinación infantil
6. actividades para fortalecer la interacción entre padres e hijos

La relevancia se revisa por consulta. No existe un umbral que convierta una
valoración editorial o clínica en un `PASS` automático.
