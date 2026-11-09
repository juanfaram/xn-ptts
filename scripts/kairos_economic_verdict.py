#!/usr/bin/env python3
"""Economic verdict from measured 4-turn session batches; price is illustrative, not CI runner cost.
All offered conversations count; paired bootstrap resamples (activity,repeat) blocks.
"""
import argparse,json,math,random
from pathlib import Path

def pct(v,q):
    s=sorted(v)
    return s[max(0,min(len(s)-1,math.ceil(q*len(s))-1))]
def load(root,arm):
    rows=json.loads((root/arm/"runs.json").read_text())
    return {(float(x["activity"]),int(x["repeat"])):x for x in rows if not x["warmup"]}
def main(a):
    root=Path(a.root)
    arms=("b8","fifo_expire","edf")
    d={arm:load(root,arm) for arm in arms}
    common=set.intersection(*(set(v) for v in d.values()))
    if not common:raise SystemExit("no matched measured waves")
    if any(set(v)!=common for v in d.values()):raise SystemExit("missing matched waves")
    keys=sorted(common)
    if any(d[arm][k]["offered_sessions"]!=d["b8"][k]["offered_sessions"] for arm in arms for k in keys):
        raise SystemExit("offered sessions mismatch")
    result={"price_reference_eur_per_hour":a.price,"price_reference":"Hetzner CCX23 indicative, not runner cost",
            "method":"useful sessions / measured wave wall time; short-batch throughput, NOT sustained SES/hour",
            "definition":"4 turns each TTFA <= deadline, M0 no stalls, PCM <=1 LSB; any rejected turn fails conversation",
            "matched_waves":len(keys),"arms":{},"paired_comparisons":{}}
    for arm in arms:
        rows=[d[arm][k] for k in keys]
        useful=sum(x["useful_sessions"] for x in rows)
        offered=sum(x["offered_sessions"] for x in rows)
        duration=sum(x["elapsed_s"] for x in rows)
        rate=useful*3600/duration
        result["arms"][arm]={"useful":useful,"offered":offered,"success_fraction":useful/offered,
           "service_wall_seconds":duration,"batch_rate_useful_per_hour":rate,
           "indicative_SES_per_eur":rate/a.price,
           "indicative_eur_per_1000_useful":1000*a.price/rate if rate else None,
           "by_activity":[{"activity":act,"offered":sum(x["offered_sessions"] for x in rows if x["activity"]==act),
             "useful":sum(x["useful_sessions"] for x in rows if x["activity"]==act)}
             for act in sorted({k[0] for k in keys})]}
    rng=random.Random(20261109)
    for other in ("b8","fifo_expire"):
        diffs=[];ratios=[]
        for _ in range(10000):
            sample=[keys[rng.randrange(len(keys))] for _ in keys]
            u1=sum(d["edf"][k]["useful_sessions"] for k in sample)
            u0=sum(d[other][k]["useful_sessions"] for k in sample)
            offered=sum(d["edf"][k]["offered_sessions"] for k in sample)
            diffs.append((u1-u0)/offered)
            t1=sum(d["edf"][k]["elapsed_s"] for k in sample)
            t0=sum(d[other][k]["elapsed_s"] for k in sample)
            if u0:ratios.append((u1/t1)/(u0/t0))
        obs=(result["arms"]["edf"]["useful"]-result["arms"][other]["useful"])/result["arms"]["edf"]["offered"]
        result["paired_comparisons"]["edf_vs_"+other]={
            "difference_success_pp":100*obs,
            "paired_wave_bootstrap_95pct_CI_pp":[100*pct(diffs,.025),100*pct(diffs,.975)],
            "batch_rate_ratio":result["arms"]["edf"]["batch_rate_useful_per_hour"]/result["arms"][other]["batch_rate_useful_per_hour"] if result["arms"][other]["batch_rate_useful_per_hour"] else None,
            "rate_ratio_bootstrap_95pct_CI":[pct(ratios,.025),pct(ratios,.975)] if ratios else None,
            "verdict":"exploratory: not a sustained or production-price claim"}
    path=root/"economic-verdict.json";path.write_text(json.dumps(result,indent=2)+"\n")
    print(json.dumps(result,indent=2))
if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("--root",required=True)
    p.add_argument("--price",type=float,default=.1378)
    main(p.parse_args())
