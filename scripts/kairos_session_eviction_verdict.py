#!/usr/bin/env python3
import json,sys,math
from pathlib import Path
from array import array
p=Path(sys.argv[1])
a=json.loads((p/"control/measure.json").read_text())
b=json.loads((p/"evict/measure.json").read_text())
def lsb(x,y):
    if len(x)!=len(y):return None
    u=array("h");v=array("h");u.frombytes(x);v.frombytes(y)
    return max((abs(i-j) for i,j in zip(u,v)),default=0)
diffs=[lsb((p/f"control/turn-{i}.pcm").read_bytes(),(p/f"evict/turn-{i}.pcm").read_bytes()) for i in range(1,5)]
rs=[(x["rss_after_bytes"]-y["rss_after_bytes"])/1048576 for x,y in zip(a["records"],b["records"])]
turn2=b["records"][1]
m1=[x.get("m1",{}).get("episodes") for x in b["records"]]
result={"pcm_max_lsb_by_turn":diffs,"rss_control_minus_evict_after_turn_mib":rs,
  "turn2_evicted_ttfa_ms":turn2.get("ttfa_ms"),"m1_episodes_by_turn":m1,
  "eviction_rebuild_log":"see evict/server.log",
  "go_to_scale":bool(all(x is not None and x<=1 for x in diffs) and turn2.get("ttfa_ms",1e9)<=200 and all(x==0 for x in m1) and rs[0]>=50),
  "warning":"RSS difference across independent processes is not a per-session causal estimate. Require matched multi-session memory slope before commercial claims."}
(p/"verdict.json").write_text(json.dumps(result,indent=2)+"\n")
print(json.dumps(result,indent=2))
