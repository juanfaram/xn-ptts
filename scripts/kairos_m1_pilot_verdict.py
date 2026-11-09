#!/usr/bin/env python3
import json,math,sys
from pathlib import Path
p=Path(sys.argv[1]);rows=json.loads((p/"fifo_expire/runs.json").read_text())
rows=[r for r in rows if not r["warmup"]]
assert len(rows)==2 and all(r["offered_sessions"]==2 and r["activity"]==.10 for r in rows)
turns=[t for r in rows for seq in r["turns"].values() for t in seq]
assert len(turns)==16
completed=[t for t in turns if t["status"]=="completed"]
tt=sorted(t["ttfa_ms"] for t in completed)
aud=sorted(t["m1"]["ttaudible_ms"] for t in completed if t.get("m1"))
m0=sum(t.get("m0_episodes",0)>0 for t in turns)
m1=sum(t.get("m1") is not None and t["m1"]["episodes"]>0 for t in turns)
missing=sum(t.get("m1") is None or not t.get("fragments") for t in completed)
pcm=sum(t.get("max_abs_lsb") is None or t["max_abs_lsb"]>1 for t in completed)
rejected=len(turns)-len(completed)
useful=sum(all(t["status"]=="completed" and t.get("m1") is not None and t["m1"]["episodes"]==0 and t.get("ttfa_ms",1e9)<=200 and t.get("max_abs_lsb") is not None and t["max_abs_lsb"]<=1 for t in seq) for r in rows for seq in r["turns"].values())
result={"offered_conversations":4,"offered_turns":16,"completed_turns":len(completed),"m0_affected_turns":m0,"m1_affected_turns":m1,"missing_fragment_traces":missing,"pcm_failures":pcm,"rejected_or_failed_turns":rejected,"m1_useful_conversations":useful,"ttfa_p99_ms":tt[-1] if tt else None,"ttaudible_p99_ms":aud[-1] if aud else None,"pre_registered_pilot_pass":bool(len(completed)==16 and m1==0 and missing==0 and pcm==0 and tt[-1]<=200 and aud and aud[-1]<=400),"warning":"Pilot n=4 conversations, NOT production reliability or economic evidence"}
(p/"m1-pilot-verdict.json").write_text(json.dumps(result,indent=2)+"\n")
print(json.dumps(result,indent=2))
