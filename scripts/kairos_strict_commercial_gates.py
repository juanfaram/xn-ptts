#!/usr/bin/env python3
"""Strict commercial gate for four-turn Phonon evidence; never equate deadline pass with 200ms p99."""
import argparse,json,math
from pathlib import Path

ARMS=("b8","fifo_expire","edf")
def percentile(xs,q):
    if not xs:return None
    s=sorted(xs);return s[max(0,min(len(s)-1,math.ceil(q*len(s))-1))]
def inspect(root,arm):
    rows=json.loads((root/arm/"runs.json").read_text())
    measured=[r for r in rows if not r["warmup"]]
    turns=[t for r in measured for ss in r["turns"].values() for t in ss]
    offered=sum(r["offered_sessions"] for r in measured)
    useful=sum(r["useful_sessions"] for r in measured)
    completed=[t for t in turns if t.get("status")=="completed"]
    ttfa=[t["ttfa_ms"] for t in completed if t.get("ttfa_ms") is not None]
    bad_m0=sum(t.get("m0_episodes",0)>0 for t in completed)
    bad_pcm=sum(t.get("max_abs_lsb") is None or t["max_abs_lsb"]>1 for t in completed)
    invalid_completed=sum(not t.get("valid",False) for t in completed)
    if len(turns)!=offered*4:raise ValueError(f"{arm}: turn denominator mismatch")
    if any(len(ss)!=4 for r in measured for ss in r["turns"].values()):
        raise ValueError(f"{arm}: incomplete session")
    if sum(all(t.get("valid",False) for t in ss) for r in measured for ss in r["turns"].values())!=useful:
        raise ValueError(f"{arm}: useful session mismatch")
    return {"arm":arm,"offered_sessions":offered,"useful_sessions":useful,
            "turns":len(turns),"completed_turns":len(completed),
            "rejected_or_error_turns":len(turns)-len(completed),
            "ttfa_p50_completed_ms":percentile(ttfa,.50),
            "ttfa_p95_completed_ms":percentile(ttfa,.95),
            "ttfa_p99_completed_ms":percentile(ttfa,.99),
            "completed_turns_m0_stall":bad_m0,
            "completed_turns_pcm_gt_1_lsb_or_unavailable":bad_pcm,
            "completed_turns_not_valid":invalid_completed,
            "ttfa_p99_200ms_gate":bool(ttfa) and percentile(ttfa,.99)<=200,
            "m0_zero_gate":bad_m0==0,
            "pcm_gate":bad_pcm==0,
            "commercial_certified":False}
def main():
    p=argparse.ArgumentParser()
    p.add_argument("--root",type=Path,required=True)
    p.add_argument("--output",type=Path)
    a=p.parse_args()
    result={"schema":"kairos-strict-four-turn-gates-v1",
            "run_type":"short-batch pilot, not sustained throughput",
            "metrics":[inspect(a.root,arm) for arm in ARMS],
            "decision":"NO COMMERCIAL SLA CLAIM if any candidate fails TTFA p99 <=200ms, M0 zero, PCM <=1 LSB, or hardware equivalence.",
            "limitations":["TTFA p99 is conditional on completed turns; rejections remain failures in session success.",
              "The benchmark's per-turn 240/1000ms deadline validity is NOT the same as the global 200ms p99 SLA.",
              "Short-batch wall time includes 20s idle periods and is not a sustained production cost.",
              "No demonstrated exclusive EDF benefit when paired 95% CI crosses zero."]}
    raw=json.dumps(result,indent=2)+"\n"
    if a.output:
        a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(raw)
    print(raw,end="")
if __name__=="__main__":main()
