# KAIROS — comparación decisiva pre-registrada

Estado: NO EJECUTADA. Objetivo: SES válidas por euro, no conexiones abiertas.

## Brazos
- B-alto+Q: capacidad de conexiones suficiente para igualar C; cola FIFO de generación; **tope fijo 2** generaciones simultáneas; espera máxima 80 ms (o valor optimizado y congelado mediante un conjunto separado de calibración). No confundir con B-8, cuyo permiso se retiene durante toda la conexión.
- C: política KAIROS con conexiones ociosas independientes y admisión por generación; su regla de asignación de permisos debe estar explícita y congelada **antes** de medir. El parche histórico `kairos_patch_ws_c.py` solo proporciona FIFO con `--max-concurrent-requests` fijo, no un controlador dinámico demostrado.
- Igual hardware, checkpoint, texto, clientes, patrón de actividad, inicio de reproducción M1, tiempo de inactividad, límites de conexión, warm-up descartado, observación y criterios C1–C5.

## Prueba válida
- Cinco repeticiones independientes por brazo, reiniciando servidor y conservando cada una; ocho si aparece un agotamiento.
- Guardar run_id, rama, SHA de código y scripts, hashes de ZIP y manifiesto, configuración de cola y permisos por brazo, marcas monotónicas y trazas PCM.
- C1 cero agotamientos; C2 reserva mínima evaluable >=30 ms; C3 duración sin audio <=20 ms y profundidad <=1 fragmento; C4 TTFA desde petición y desde admisión diferenciados, p95 y máximo <=200 ms; C5 huecos relativos solo informativos.
- No certificar C1–C3 hasta reconciliar el modelo de pausa/reanudación v2 con el analizador M1 y congelar duración de episodios; no certificar C4 sin timestamp de admisión.
- Comparar SES válidas por repetición, rechazos, espera, cola y tiempo de ocupación; después coste de instancia y euros por 1000 SES válidas con fuente de precio fechada.

## Bloqueos concretos antes de lanzar
1. Implementar y probar B-alto+Q genuino: no sustituirlo por B-8.
2. Especificar qué distingue a C del mismo tope fijo 2: si ambos usan la misma cola y los mismos permisos, no atribuirle una ventaja dinámica.
3. Verificar el analizador congelado sobre ZIP históricos y dejar los criterios computables sin ambigüedad.
4. Ensayo mínimo de protocolo y compilación antes de la tanda. No repetir k=1.

Regla de interpretación: ninguna ganancia en conexiones admitidas cuenta como SES válida sin cumplir todas las puertas duras. No extrapolar tres repeticiones históricas a cinco ni afirmar ahorro sin precios y denominadores.
