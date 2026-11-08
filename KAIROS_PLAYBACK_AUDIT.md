# KAIROS — reserva de reproducción, auditoría offline v1

**Objetivo:** distinguir un intervalo largo entre fragmentos de un agotamiento real de reserva bajo reproducción inmediata. No modifica Phonon ni ejecuta un servidor.

**Evidencia:** GitHub Actions run 42510422243; artifact 13629272369; ZIP SHA-256 `b83901c4d9955717da22b1e6f0f4cac445221adb4a7a5effc54691ebad900e29`. El manifiesto original contiene un sufijo literal `\\n` después del JSON; el lector lo tolera, sin alterar el ZIP. Los 15 hashes internos coinciden.

**Reproducir:** descargar el ZIP original y ejecutar `python3 scripts/kairos_playback_audit.py kairos-k1-integrity.zip --output playback-audit.json`. No requiere dependencias externas.

**Definición:** para el fragmento i>0, `reserve_before_i = sum(frag_ms[0:i]) - (ts_recv_i-ts_recv_0)*1000`. Valor negativo implica agotamiento **simulado** bajo reproducción inmediata desde el primer fragmento. No equivale a una medición de interrupciones audibles en dispositivo real.

**Resultado observado en 5 tandas k=1:** 42 fragmentos por tanda, 3 intervalos largos por tanda (15 en total), **0 agotamientos simulados**, mínimo de reserva después del primero entre **38,05 y 39,79 ms**. Hash PCM16 idéntico en las cinco. RSS máxima por tanda 426,52 / 483,68 / 556,51 / 578,12 / 598,73 MiB: no prueba fuga ni estado por sesión.

**Límites:** un único servidor original y un único tipo de CPU, sin reloj de emisión del servidor, sin reproducción real, sin C ni comparación con cola FIFO. No se infiere k_max, SLA real, SES ni ahorro.

**Siguiente puerta:** aplicar exactamente este mismo cálculo a trazas por fragmento de k=2, luego comparar a carga emparejada contra B-8+Q y C. Preservar también el indicador antiguo de intervalo largo.
