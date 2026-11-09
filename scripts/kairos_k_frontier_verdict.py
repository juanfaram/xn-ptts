#!/usr/bin/env python3
"""Concurrence frontier on real Phonon; strict M0, TTFA, PCM; no economic extrapolation."""
import json,math,sys
from pathlib import Path
p=Path(sys.argv[1]); rows=json.loads((p/"direct32"/"runs.json").read_text())
out=[]
for k in (1,2,4,8):
    waves=[r for r in rows if round(20*r["activity"])==k and not r["warmup"]]
    turns=[t for w in waves for seq in w["turns"].values() for t in seq]
    completed=[t for t in turns if t["status"]=="completed"]
    tt=sorted(t["ttfa_ms"] for t in completed)
    q=lambda x:tt[min(len(tt)-1,math.ceil(x*len(tt))-1)] if tt else None
    good=sum(all(t["status"]=="completed" and t["ttfa_ms"]<=200 and t["m0_episodes"]==0 and t["max_abs_lsb"] is not None and t["max_abs_lsb"]<=1 for t in seq) for w in waves for seq in w["turns"].values())
    m0=sum(t["m0_episodes"]>0 for t in completed)
    pcm=sum(t["max_abs_lsb"] is None or t["max_abs_lsb"]>1 for t in completed)
    failures=len(turns)-len(completed)
    out.append({"k_offered_simultaneously":k,"measured_waves":len(waves),"offered_sessions":k*len(waves),
      "strict_valid_sessions":good,"completed_turns":len(completed),"failed_turns":failures,
      "ttfa_request_p99_ms":q(.99),"m0_affected_turns":m0,"pcm_fail_turns":pcm,
      "strict_pass":bool(tt and q(.99)<=200 and m0==0 and pcm==0 and failures==0),
      "ttfa_admitted_p99_ms":None})
result={"model":"real frozen Phonon, direct WS, virtual immediate-start M0, no proxy",
 "thresholds":{"ttfa_request_p99_ms":200,"ttfa_admitted_p99_ms":28,"m0_episodes":0,"pcm_max_lsb":1},
 "note":"TTFA admitted is NOT measured in direct path; no k is fully certified without it. k counts simultaneous generation requests, not guaranteed concurrent compute.",
 "levels":out}
(p/"k-frontier.json").write_text(json.dumps(result,indent=2)+"\n");print(json.dumps(result,indent=2))
