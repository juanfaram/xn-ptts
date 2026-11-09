#!/usr/bin/env python3
"""Paired k=2 direct32 vs FIFO+expiry, strict offered-session results."""
import json,math,sys
from pathlib import Path
root=Path(sys.argv[1]);out={"scope":"same host, fixed 2 active sessions, four turns, 200ms TTFA, M0 immediate, PCM<=1 LSB","arms":{}}
for arm in ("direct32","fifo_expire"):
    rows=json.loads((root/arm/"runs.json").read_text())
    measured=[w for w in rows if not w["warmup"]]
    turns=[t for w in measured for seq in w["turns"].values() for t in seq]
    completed=[t for t in turns if t["status"]=="completed"]
    offered=sum(w["offered_sessions"] for w in measured)
    good=sum(all(t["status"]=="completed" and t["ttfa_ms"]<=200 and t["m0_episodes"]==0 and t["max_abs_lsb"] is not None and t["max_abs_lsb"]<=1 for t in seq) for w in measured for seq in w["turns"].values())
    times=sorted(t["ttfa_ms"] for t in completed)
    out["arms"][arm]={"offered_sessions":offered,"strict_valid_sessions":good,"completed_turns":len(completed),
       "failed_turns":len(turns)-len(completed),"m0_affected_turns":sum(t["m0_episodes"]>0 for t in completed),
       "pcm_fail_turns":sum(t["max_abs_lsb"] is None or t["max_abs_lsb"]>1 for t in completed),
       "ttfa_p99_completed_ms":times[math.ceil(.99*len(times))-1] if times else None,
       "batch_elapsed_seconds":round(sum(w["elapsed_s"] for w in measured),3)}
out["limits"]="Exploratory matched k2 load; no production cost, no k_max certificate; direct32 lacks admission-based generation cap."
(root/"paired-k2-verdict.json").write_text(json.dumps(out,indent=2)+"\n")
print(json.dumps(out,indent=2))
