#!/usr/bin/env python3
"""Precommitted paired M1 economic gate. No billed hardware, no commercial cost claim."""
import argparse,json,math,random
from pathlib import Path
def quant(v,q):
    s=sorted(v);return s[max(0,min(len(s)-1,math.ceil(q*len(s))-1))] if s else None
def success(t):
    m=t.get("m1")
    return t.get("status")=="completed" and t.get("ttfa_ms",1e9)<=200 and m is not None and m.get("episodes",1)==0 and m.get("ttaudible_ms",1e9)<=400 and t.get("max_abs_lsb") is not None and t["max_abs_lsb"]<=1
def main(root):
    root=Path(root)
    arms=("fifo_expire","edf")
    data={}
    for arm in arms:
        rows=json.loads((root/arm/"runs.json").read_text())
        data[arm]={int(r["repeat"]):r for r in rows if not r["warmup"]}
    keys=sorted(set(data["fifo_expire"]) & set(data["edf"]))
    if len(keys)!=15 or any(set(data[a])!=set(keys) for a in arms):raise SystemExit("expected exactly 15 paired measured waves")
    out={"protocol":"k=2 offered, 20 sessions, 10% activity, 15 measured waves + warmup, 4 turns, 20s idle",
      "criteria":"TTFA request<=200ms; virtual M1=0 stalls; virtual TTAudible<=400ms; PCM<=1 LSB; rejects count as failure",
      "arms":{},"matched_waves":len(keys),"economic_warning":"CI runner has no verified billed price; batch rates are NOT sustained SES/h"}
    for arm in arms:
        rows=[data[arm][k] for k in keys]
        if any(r["offered_sessions"]!=2 or r["activity"]!=.10 for r in rows):raise SystemExit("load mismatch")
        seqs=[s for r in rows for s in r["turns"].values()]
        turns=[t for s in seqs for t in s]
        completed=[t for t in turns if t.get("status")=="completed"]
        useful=sum(all(success(t) for t in s) for s in seqs)
        duration=sum(r["elapsed_s"] for r in rows)
        out["arms"][arm]={"offered_conversations":len(seqs),"useful_conversations":useful,
          "success_fraction":useful/len(seqs),"completed_turns":len(completed),
          "m0_affected_turns":sum(t.get("m0_episodes",0)>0 for t in completed),
          "m1_affected_turns":sum((t.get("m1") or {}).get("episodes",0)>0 for t in completed),
          "missing_fragment_traces":sum(not t.get("fragments") for t in completed),
          "rejected_or_failed_turns":len(turns)-len(completed),
          "pcm_failures":sum(t.get("max_abs_lsb") is None or t["max_abs_lsb"]>1 for t in completed),
          "ttfa_request_p99_ms":quant([t["ttfa_ms"] for t in completed],.99),
          "ttaudible_virtual_p99_ms":quant([t["m1"]["ttaudible_ms"] for t in completed if t.get("m1")],.99),
          "measured_batch_seconds":duration,
          "illustrative_batch_useful_per_hour":3600*useful/duration}
    rng=random.Random(20261109);diff=[]
    for _ in range(20000):
        sample=[keys[rng.randrange(len(keys))] for _ in keys]
        def count(arm):
            return sum(all(success(t) for t in s) for k in sample for s in data[arm][k]["turns"].values())
        diff.append((count("edf")-count("fifo_expire"))/30*100)
    point=(out["arms"]["edf"]["useful_conversations"]-out["arms"]["fifo_expire"]["useful_conversations"])/30*100
    out["edf_minus_fifo_success_percentage_points"]={"estimate":point,"paired_wave_bootstrap_95pct":[quant(diff,.025),quant(diff,.975)],
      "exclusive_advantage_demonstrated":quant(diff,.025)>0}
    (root/"m1-paired-verdict.json").write_text(json.dumps(out,indent=2)+"\n")
    print(json.dumps(out,indent=2))
if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("root");main(p.parse_args().root)
