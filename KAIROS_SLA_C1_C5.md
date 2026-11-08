# KAIROS — criterios C1–C5 pre-registrados (puerta 1b)

Estado: **umbrales predefinidos; puerta 1b NO certificada**. No reinterpretar ni modificar después de observar resultados k=2. Aplicar idénticas reglas a B-8, B-8+Q y C. No cambiar el motor.

## Procedencia del basal
- Run ID: `42512393491`; rama: `run/kairos-k1-integrity`; commit: `8e58af387d9bccef84e4b0c9d0295c4084012e04`.
- Script SHA-256 reportado en auditoría: `78d0df4509bddfc5ceadc174b86147652e8cc320caecbf1c2ed9292e92f8ce17` (reverificar con artefacto al usarlo).
- 5 repeticiones; 42 fragmentos por repetición; un hueco relativo de 0,7094 ms sobre el plazo en repetición 4, índice 22. Son datos diagnósticos, no certificación de SLA.

## Puertas duras (por flujo y repetición)
- **C1:** cero agotamientos de reserva de audio. Un agotamiento ocurre si la reserva de reproducción alcanza 0 antes de la llegada del siguiente fragmento, con el estado inicial y el instante de inicio de reproducción definidos explícitamente.
- **C2:** reserva mínima >= 30 ms durante la ventana de reproducción evaluable. La referencia basal de 38,05 ms y el margen del 20 % son hipótesis históricas **pendientes de verificar** en evidencia cruda; no declarar C2 medido hasta fijar la convención de arranque y calcularlo.
- **C3:** si se producen eventos de falta de audio: duración total sin audio <= 20 ms y profundidad máxima <= 1 fragmento. C1 sigue siendo una puerta dura: cumplir C3 no neutraliza un fallo C1.
- **C4:** TTFA p95 y TTFA máximo <= 200 ms, desde la solicitud de audio hasta la recepción del primer fragmento; informar n y evitar interpretar p95 con muestras pequeñas como cola poblacional.
- **C5 (informativo):** huecos relativos `inter_ms > frag_ms_anterior`. Mantenerlo para comparabilidad histórica, pero nunca usarlo como veredicto de SLA. Registrar además conteos de intervalos >200 ms y >400 ms y huecos de índice <=3, sin redefinir C1–C4.

## Regla de decisión pre-comprometida
- Continuidad gana: C1 y C2 cumplen en **todas** las repeticiones; siempre exigir además C3 y C4 para declarar SES válido.
- Continuidad empata: C1 cumple y C2 falla; **no** equivale a SES válido.
- Continuidad pierde: C1 falla.
- 5 repeticiones por brazo para k=2; ampliar a 8 si se observa al menos un agotamiento. La unidad experimental para inferencia es la repetición, no el fragmento.
- Comparar audio PCM muestra a muestra con máximo desvío LSB, no por igualdad SHA-256. La tolerancia debe conservarse documentada antes de evaluar los brazos.

## Verificación de instrumentación (bloqueo actual)
El script `scripts/kairos_ws_k1_control.py` contiene `ts_recv_monotonic_s`, `frag_ms`, `inter_ms`, `margin_ratio`, `gap`, `ttfa_ms`, RSS y hashes. **No** registra explícitamente reserva mínima de reproducción, eventos de agotamiento, duración sin audio ni profundidad de agotamiento. El proxy `gap` no es un underrun. Por tanto C1–C3 están **NO MEDIBLES** con las columnas actuales; no se certifica la puerta 1b ni se lanza k=2 hasta cerrar ese mínimo de instrumentación y verificarlo con datos basales, sin cambiar criterios.

## Alcance
No construir proxy, panel ni diagnóstico comercial; no tocar KV, caché, cuantización ni GPU. Los precios, SES y cruce de actividad quedan para puertas posteriores.

## Nota matemática crítica (v3, pendiente de reconciliar con v2)
La expresión propuesta `R_i = t_i - (t_0 + P + i*frag_ms)` es **tardanza**, no reserva: un valor negativo indica llegada temprana. Por ello, imponer `R_i < 0` como agotamiento invierte la desigualdad física. El analizador v3 emplea **reserva** `B_i=(t_0+P+sum_{j<i} frag_ms_j)-t_i`, con agotamiento `B_i<0`. Se conserva la fórmula propuesta como especificación pendiente de reconciliación con el v2, no como umbral certificado. M0 usa P=0 y M1 P=2*frag_ms_0. El primer fragmento define t0. Un episodio es una racha contigua de B_i<0. El valor inicial B_0=0 en M0 no constituye agotamiento.

**Advertencia:** esta convención de reproducción produce reserva basal mínima 0 ms (M0) y 160 ms (M1) para el k1 de 42 fragmentos; no reproduce el basal de 38,05 ms citado anteriormente. Por tanto **C2 y puerta 1b siguen abiertos** hasta recuperar y comparar el v2, su código y su definición exacta. No se ajustan fórmulas retrospectivamente para forzar una coincidencia.

**Warm-up:** una generación de calentamiento independiente se descarta de la muestra de cinco repeticiones, pero se conserva en evidencia. La referencia separada de k1 en run 42512393491 es una generación previa, no se certifica como warm-up equivalente sin comprobar el procedimiento.

**C4:** el arnés histórico registra `ttfa_ms` medido después de enviar el texto y alrededor del flush. No identifica por separado `ttfa_request_ms` (desde petición original, incluye espera) y `ttfa_admitted_ms` (desde admisión efectiva). No se declara C4 medido de forma comparable entre brazos hasta reconstruir o capturar ambas marcas.
