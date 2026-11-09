#!/usr/bin/env python3
"""Diagnose TTFA and M0 by load wave and turn from original archived evidence."""
import argparse,json,math,statistics,zipfile
from pathlib import Path

def quantile(values,q):
    if not values:return None
    xs=sorted(values)
    return round(xs[min(len(xs)-1,math.ceil(q*len(xs))-1)],3)

def audit(archive):
    output={}
    with zipfile.ZipFile(archive) as z:
        for arm in ("b8","fifo_expire","edf"):
            rows=json.loads(z.read(f"{arm}/runs.json"))
            by_wave=[]
            for activity in (.10,.25,.50):
                for turn in range(4):
                    samples=[ss[turn] for wave in rows if not wave["warmup"] and wave["activity"]==activity for ss in wave["turns"].values()]
                    completed=[x for x in samples if x.get("status")=="completed"]
                    ttfa=[x["ttfa_ms"] for x in completed]
                    by_wave.append({"activity":activity,"turn":turn,"offered":len(samples),
                        "completed":len(completed),"rejected_or_error":len(samples)-len(completed),
                        "ttfa_p50_completed_ms":quantile(ttfa,.50),
                        "ttfa_p95_completed_ms":quantile(ttfa,.95),
                        "ttfa_p99_completed_ms":quantile(ttfa,.99),
                        "completed_ttfa_over_200ms":sum(x>200 for x in ttfa),
                        "completed_m0_stall":sum(x.get("m0_episodes",0)>0 for x in completed)})
            output[arm]=by_wave
    return {"schema":"kairos-wave-turn-diagnosis-v1",
      "source":"original GitHub Actions artifact ZIP; measured waves only",
      "run_id":42621484283,"source_commit":"061ad07802ddeeb66140dcec80470404567ad62b",
      "warning":"p99 conditional on completed turns, not full offered SLA; no per-request enqueue/admission times in these archived runs.",
      "by_arm":output}

def main():
    p=argparse.ArgumentParser()
    p.add_argument("archive",type=Path)
    p.add_argument("--output",type=Path)
    args=p.parse_args()
    data=audit(args.archive)
    raw=json.dumps(data,indent=2)+"\n"
    if args.output:
        args.output.parent.mkdir(parents=True,exist_ok=True)
        args.output.write_text(raw)
    print(raw,end="")

if __name__=="__main__":main()
