#!/usr/bin/env python3
"""Pre-registered two-arm idle-time causal probe, strict gate, all offered sessions."""
import argparse,json,math
from pathlib import Path
def q(xs,p):
    if not xs:return None
    xs=sorted(xs);return round(xs[min(len(xs)-1,math.ceil(len(xs)*p)-1)],3)
def measure(path):
    waves=json.loads((path/"runs.json").read_text())
    measured=[w for w in waves if not w["warmup"]]
    sessions=[v for w in measured for v in w["turns"].values()]
    turns=[t for s in sessions for t in s]
    completed=[t for t in turns if t.get("status")=="completed"]
    ttfa=[t["ttfa_ms"] for t in completed if t.get("ttfa_ms") is not None]
    strict=sum(all(t.get("status")=="completed" and t.get("ttfa_ms",1e9)<=200 and
                       t.get("m0_episodes",1)>0 is False and t.get("max_abs_lsb") is not None and t["max_abs_lsb"]<=1
                       for t in s) for s in sessions)
    # Explicit condition, avoid reliance on truthiness or chained bool identity.
    strict=sum(all(t.get("status")=="completed" and t.get("ttfa_ms",1e9)<=200 and
                       t.get("m0_episodes",1)==0 and t.get("max_abs_lsb") is not None and t["max_abs_lsb"]<=1
                       for t in s) for s in sessions)
    return {"offered_sessions":len(sessions),"pilot_deadline_useful_sessions":sum(all(t.get("valid",False) for t in s) for s in sessions),
            "strict_200ms_complete_sessions":strict,"completed_turns":len(completed),
            "offered_turns":len(turns),"failed_or_rejected_turns":len(turns)-len(completed),
            "completed_ttfa_p99_ms":q(ttfa,.99),"completed_ttfa_over_200ms":sum(x>200 for x in ttfa),
            "m0_stalled_completed_turns":sum(t.get("m0_episodes",0)>0 for t in completed),
            "pcm_gt_1lsb_or_missing_completed_turns":sum(t.get("max_abs_lsb") is None or t["max_abs_lsb"]>1 for t in completed),
            "elapsed_measured_s":round(sum(w["elapsed_s"] for w in measured),3),
            "global_ttfa_p99_200ms_pass":bool(ttfa) and q(ttfa,.99)<=200}
def main():
    a=argparse.ArgumentParser();a.add_argument("--root",type=Path,required=True);args=a.parse_args()
    result={"schema":"kairos-causa-probe-v1","causal_variable":"interturn idle time 20s vs 2s",
       "arms":{},"limitations":["Pilot not sustained production SES/euro","B8 is original max-8-connections control, FIFO uses 3 slots","Per-turn 240/1000ms deadlines differ from strict 200ms gate","No inference of cause unless matched setup and measurement checks pass"]}
    for regime in ("idle20","idle2"):
        result["arms"][regime]={arm:measure(args.root/regime/arm) for arm in ("fifo_expire","b8")}
    (args.root/"causa-verdict.json").write_text(json.dumps(result,indent=2)+"\n")
    print(json.dumps(result,indent=2))
if __name__=="__main__":main()
