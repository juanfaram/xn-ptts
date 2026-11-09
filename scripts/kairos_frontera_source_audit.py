#!/usr/bin/env python3
"""Zero-model frontier audit: identify whether frozen Phonon has an unexploited cross-session batching path."""
import json,re,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
frozen="e5110afd3ead725c940b6411eec4985fb8b111aa"
def read_frozen(path):
    return subprocess.check_output(["git","show",f"{frozen}:{path}"],cwd=ROOT,text=True)
def main():
    synth=read_frozen("ptts/src/synth.rs")
    handler=read_frozen("ptts-ws-server/src/handler.rs")
    flow=read_frozen("ptts/src/flow_lm.rs")
    required={
      "latent_queue_16":bool(re.search(r"const LATENT_QUEUE:\s*usize\s*=\s*16;",synth)),
      "decode_batch_equals_latent_queue":"const DECODE_BATCH: usize = LATENT_QUEUE;" in synth,
      "nonblocking_decode_batch":"latent_rx.try_recv()" in synth,
      "decode_batch_does_not_wait_to_fill":"no frame is ever" in synth and "held back for a batch to fill" in synth,
      "ws_permit_on_upgrade":"try_acquire_owned()" in handler and "ws.on_upgrade" in handler,
      "flow_lm_accepts_batch_state":"init_state(&self, batch_size: usize" in flow,
    }
    if not all(required.values()):raise SystemExit("frozen source invariant failed: "+json.dumps(required))
    result={"frozen_commit":frozen,"invariants":required,
      "verified":"Within-generation opportunistic Mimi latent batching up to 16; WS permit acquired on upgrade.",
      "not_verified":"Cross-session dynamic batching, throughput gain on this runner, any SLA-safe k>3, commercial advantage.",
      "decision":"Do not change Phonon or claim 16 concurrent generations. Test only if measured CPU/latency frontier can change SES/euro.",
      "next_discriminant":"Matched same-hardware B8 vs FIFO+expiry vs candidate batching route, TTFA global p99<=200ms, M0, PCM16 <=1LSB, offered failures included."}
    out=ROOT/"out/frontera"
    out.mkdir(parents=True,exist_ok=True)
    (out/"source-audit.json").write_text(json.dumps(result,indent=2)+"\n")
    print(json.dumps(result,indent=2))
if __name__=="__main__":main()
