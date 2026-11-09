# KAIROS — correction of concurrency accounting (2026-11-09)

Evidence: GitHub Actions run 42644934794, artifact 13689983059, `fifo_expire/runs.json` and `edf/runs.json`.

## Critical correction

`--sessions 20 --activities 0.10 --repeats 20` yields `round(20 * .10) = 2` generation requests per wave. The first wave is warmup; the 19 measured waves produce `19 * 2 = 38` offered conversations **cumulatively** per arm, NOT 3.8 concurrent generations. The four turns are sequential, with 20 seconds idle between turns. A wave contains no more than two active generation requests, even if the actual permit occupancy is lower.

## Verified metrics

| Metric | FIFO+expiry | EDF |
|---|---:|---:|
| Measured waves | 19 | 19 |
| Offered generation requests per wave | 2 | 2 |
| Offered conversations total | 38 | 38 |
| Completed turns | 152/152 | 152/152 |
| Useful conversations | 3/38 | 1/38 |
| TTFA completed-turn p99 from flush request | 62.994 ms | 65.297 ms |
| M0-affected turns | 66 | 74 |
| M0 turns 1/2/3/4 | 16/17/18/15 | 16/17/15/26 |

The proxy logs in this artifact have no per-permit admission/release timestamps. Therefore **actual permit occupancy by 1-second window cannot be reconstructed** from this artifact. Report the exact offered concurrency (2 per wave) and mark observed permit occupancy unavailable, rather than inventing a number.

## Decision

The 38/10% argument does not establish overload: 38 is an aggregate count, not the simultaneous population. The run refutes reproducible M0-zero performance under the observed two-request waves, but does **not** prove why M0 fails. EDF is not statistically distinguishable from FIFO with 1 versus 3 useful conversations. Do not change the motor or claim a commercial win. Next discriminant is audio fragment timing at two concurrent generation requests, with permit admission/release instrumentation, same fixed offered load and PCM/TTFA gates. This is a causal diagnostic, not a new economic claim.
