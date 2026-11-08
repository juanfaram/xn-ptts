# KAIROS — WebSocket arm B (isolated, no production load)

Source frozen: `e5110afd3ead725c940b6411eec4985fb8b111aa`. This measures **only arm B**: the unmodified Gradium server with a connection-held semaphore. Arm C is not implemented here; do not infer a C-vs-B improvement.

On an isolated machine with the public checkpoint downloaded to `phonon-model/`:

```bash
python3 -m pip install 'websockets>=13,<17'
cargo build --release -p ptts-ws-server
./target/release/ptts-ws-server --model phonon-model --voice-catalog '' --lang en --device cpu --max-concurrent-requests 8 --addr 127.0.0.1:8080
# Second terminal:
python3 scripts/kairos_ws_load.py --limit 8 --sessions 10 --idle-seconds 2 --output out/ws-B-m8.csv
```

The client attempts simultaneous upgrades, holds successful connections idle, records HTTP 429, then sends setup/text/flush and captures TTFA and delivery timing. `--limit` is a **label**, not a server configuration flag. Do not test third-party/production endpoints without explicit authorization.

`ttfa_request_ms` begins after sending text; `ttfa_admitted_ms` begins at the successful WebSocket upgrade and therefore includes deliberate idle time. Neither is a true server admission-queue latency; upgrade_ms is separate. `delivery_gaps` compares inter-arrival with preceding chunk playback time; it is a transport proxy, not a perceptual underrun.

For C versus B, implement the admission policy change in an isolated server branch, preserve model/CPU/load and measure both arms at matched TTFA. An unchanged server with `m=8` is B, not C. The client is not a proof of advantage. A p99 computed from ten connections is a sample maximum, not a stable tail percentile.

Reproducibility: preserve server SHA, CPU, nproc, memory, model checkpoint/dtype, CSV, JSON and command line in each run.
