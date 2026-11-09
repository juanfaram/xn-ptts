# KAIROS M1 paired commercial confirmation — preregistered before measurements

## Fixed objective
Compare EDF policy against the **best conventional FIFO+expiry proxy**, both with identical two-fragment M1 virtual client playback. The proxy is shared; this estimates only the exclusive EDF policy advantage, **not** the architecture's gain over the original B8 server.

## Workload
Frozen upstream Phonon e5110afd3ead725c940b6411eec4985fb8b111aa; one GitHub Actions runner; original server m32; proxy 3 slots, K64, 20 persistent clients; 10% activity = exactly 2 concurrent generation requests offered per wave; 16 waves (1 excluded warmup, 15 measured); 4 turns, 20s idle; 30 offered conversations per arm, 120 turns. Same model, text, seeds and reference PCM. Order FIFO then EDF; possible thermal/order confounding is disclosed.

## Preregistered validity
Each of 4 turns: TTFA from flush request <=200ms; virtual M1 zero stalls; virtual time to second fragment (TTAudible) <=400ms; PCM difference <=1 LSB. Every rejected/errored turn invalidates the whole conversation. M0 always reported as a conservative diagnostic. Do not relabel M1 as real device audio.

## Statistics and commercial gate
Primary: difference in complete-conversation success probability EDF−FIFO, with paired-wave bootstrap 95% CI; require CI lower bound >0 for evidence of exclusive advantage. Also report all-offered success, completed-turn p99, M0/M1, PCM, batch wall seconds, indicative batch useful/hour. A CI runner does not have a verified comparable billed hourly price; **no real SES/euro claim**. Zero failures in n=30 cannot certify perfect reliability. If CI includes zero, no exclusive EDF advantage; keep conventional FIFO as main implementation.

## Stop rule
No new algorithms, no k=3 or k=4, no 28ms admitted gate, no engine modifications. After this run either move to matched billed-hardware economics with a demonstrated advantage or close EDF differentiation.
