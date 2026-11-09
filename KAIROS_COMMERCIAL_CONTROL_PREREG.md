# KAIROS — control comercial pre-registrado (v1)

**Estado:** especificación previa a construir el control; no es un resultado B/C.

## Resultado de la escalera
Servidor original, modelo virtual M1 (dos fragmentos antes de reproducir), una tanda de calentamiento excluida y ocho tandas medidas por nivel.

- k=2: 0/16 flujos afectados.
- k=3: 3/24 (12,5 %, IC95 % Clopper-Pearson aprox. 2,7–32,4 %). Repetición 2, flujo 0, fragmento 2, 63,847 ms; repetición 6, flujo 2, fragmento 2, 35,876 ms; repetición 8, flujo 2, fragmento 2, 30,768 ms. Cinco de ocho tandas limpias. **Candidato, no certificación de SLA.**
- k=4: 16/32 (50 %, IC95 % aprox. 31,9–68,1 %); ninguna de ocho tandas limpia. Peor episodio 630,24 ms. No cumple la regla pre-registrada.
- TTFA máximas observadas por nivel: k1 ~38, k2 ~80, k3 ~119, k4 ~174 ms. La extrapolación a k5 NO es un resultado medido.

**Criterio de avance:** tasa observada de flujos con episodio M1 <=20 % y límite superior IC95 % exacto <50 %. El IC de k3 incluye tasas >20 %: no es una garantía de producción.

## Control convencional obligatorio: B-alto+Q
- Servidor Phonon original sin modificar, conexiones admitidas hasta un techo de RAM medido y documentado.
- Proxy de mensajes WebSocket con cola FIFO para solicitudes lógicas de generación (flush), no una simple cola de upgrades.
- **Máximo tres generaciones activas** como límite candidato emparejado a k3. No derivar ese límite de 1/RTF.
- Una solicitud lógica, un plazo absoluto desde llegada original, igual política de timeout/reintento y contabilización de rechazos para todos los brazos.
- Cuando venza un plazo: contabilizar fallo incluso si una solicitud llega a completarse más tarde. Respuestas 429 estructuradas con Retry-After en el borde del proxy cuando corresponda.
- No llamar B-alto+Q a una cola de conexiones ni a un proxy que deja que el servidor procese más de tres generaciones.
- El control debe registrar por separado admisión WS, solicitud flush, inicio efectivo de generación, entrega final, esperas, expiraciones, RSS, CPU, bytes y audio PCM16.
- La medición de generación activa mediante mensajes flush/flushed es aproximada: incluye el envío y procesamiento; documentar la diferencia y verificar que no hay generaciones concurrentes ocultas.
- Antes de comparar, auditar si existe una implementación real de C en una rama, su diff, su política de admisión, su cola y su desalojo. **No atribuirle prioridad por plazo sin código que la implemente.**

## Diseño de comparación
- Cinco brazos previstos: B-8, B-k3, B-alto, B-8+Q y B-alto+Q, más C solo si existe parche verificable.
- Carga idéntica por brazo, niveles de solicitudes/hora pre-registrados 25, 50, 100, 200, 400, 800, mezclando actividad/inactividad y plazos heterogéneos explícitos.
- Ejecutar pares en el mismo tipo de CPU, intercalados; mismo precio de instancia, RAM, modelo, semilla y analizador. No comparar hardware heterogéneo.
- Resultado primario: **solicitudes lógicas completadas dentro de SLA por hora y dólar**, junto a tasa de incumplimiento sobre todas las solicitudes ofrecidas, rechazos, TTFA, continuidad M0/M1, RSS y coste.
- Pre-registrar dos posibles ventajas: A, SES >=2x frente a B-alto+Q sin peor SLA; B, SES >=0,9x, >=50 % menos incumplimientos y coste <=+10 %. Confirmar con IC95 % y potencia adecuada.
- **Falsador:** si C no supera B-alto+Q en resultados comercialmente relevantes, KAIROS no tiene ventaja diferencial demostrada; publicar el empate.
- Los resultados de la escalera son diagnósticos; no sustituyen un ensayo sostenido ni una comparación de producto.

**Próximo trabajo:** construir primero el proxy FIFO por flush y sus pruebas de cola/timeout/cancelación, sin tocar el motor; después una prueba emparejada de humo, no declarar economía antes de carga sostenida.
