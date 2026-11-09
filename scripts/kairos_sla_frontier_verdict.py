#!/usr/bin/env python3
"""Frozen SLA gate: strict offered-session utility and request TTFA p99; no post-hoc threshold changes."""
import json,math,sys
from pathlib import Path
def p99(v):
    v=sorted(v)
    return v[math.ceil(.99*len(v))-1] if v else None
def main(root):
    root=Path(root)
    result={"scope":"10% and 15% offered activity, 4 turns, 20s idle, 5 measured waves plus warmup",
       "global_sla_ttfa_p99_limit_ms":200,"arms":{}}
    for arm in ("b8","fifo_expire","edf"):
        rows=[r for r in json.loads((root/arm/"runs.json").read_text()) if not r["warmup"]]
        vals={}
        for act in sorted(set(r["activity"] for r in rows)):
            rr=[r for r in rows if r["activity"]==act]
            turns=[t for r in rr for v in r["turns"].values() for t in v]
            tt=[t["ttfa_ms"] for t in turns if t["status"]=="completed"]
            rejected=sum(t["status"]=="rejected" for t in turns)
            offered=sum(r["offered_sessions"] for r in rr)
            useful=sum(r["useful_sessions"] for r in rr)
            q=p99(tt)
            vals[str(act)]={"offered_conversations":offered,"useful_conversations":useful,
                "success_fraction":useful/offered,"turns_offered":len(turns),
                "turns_rejected":rejected,"ttfa_completed_p99_ms":q,
                "sla_gate":"pass" if rejected==0 and q is not None and q<=200 else "fail",
                "note":"Completed-turn p99 alone is insufficient if rejected turns >0"}
        result["arms"][arm]=vals
    (root/"sla-frontier-verdict.json").write_text(json.dumps(result,indent=2)+"\n")
    print(json.dumps(result,indent=2))
if __name__=="__main__":main(sys.argv[1])
