# Preregistration — KAIROS M1 two-generation four-turn capture
Date: 2026-11-09. This document is committed before the workflow measurements.

## Hypothesis and falsifier
At exactly two offered generation requests per wave, FIFO+expiry with three permits and two-fragment client prebuffer produces zero **virtual M1** stalls in measured four-turn conversations, with TTFA from flush request p99 <=200 ms, PCM16 <=1 LSB, and no rejects. Any measured M1 stall, rejection, PCM failure or p99 >200ms falsifies the **zero-observed-failures** pilot gate. Zero observed stalls does not prove zero population risk.

## Workload and controls
Real frozen Phonon model, unchanged Rust server, FIFO+expiry proxy, slots=3, queue=64, sessions=20, activity=10% (exactly two offered simultaneous requests), four turns, 20 seconds between turns. Three waves total, first warmup excluded, two measured waves = four conversations and 16 measured turns. Small diagnostic, NOT certification or economic proof. No policy comparisons or tuning after seeing data.

## Metrics
TTFA: client flush-request timestamp to first audio received. M0: virtual immediate-start playback, no buffer. M1: virtual playback starts when second fragment arrives; initial buffer is duration of first two fragments. TTAudible = request to arrival of second fragment, **not TTFA +160ms**. Also record first-to-second fragment delay, all fragment arrival timestamps/durations, PCM16 difference, rejects, useful four-turn conversations, and proxy arrival/admission/release events where available. M1 is a simulation, not physical audio-device measurement.

## Economic interpretation
No claimed savings or SES/euro from this diagnostic. If M1 fails at k=2, do not promote M1 to product criterion. If it passes, run a larger preregistered paired test against the best conventional FIFO and obtain comparable billed hardware before making a commercial claim.
