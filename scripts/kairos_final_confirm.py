#!/usr/bin/env python3
"""Confirmatory FIFO-vs-EDF report: fixed offered load, global 200ms TTFA, M0 and PCM.
Billed cost requires a measured rate on the same priced machine, not an imported tariff.
"""
import argparse,json,math,random
from pathlib import Path
def quant(a,p):
    if not a:return None
    x=sorted(a);return x[min(len(x)-1,max(0,math.ceil(p*len(x))-1))]
def read(root,arm):
    rows=json.loads((root/arm/"runs.json").read_text())
    rows=[r for r in rows if not r["warmup"]]
    return {int(r["repeat"]):r for r in rows}
def main(a):
    root=Path(a.root);data={arm:read(root,arm) for arm in ("fifo_expire","edf")}
    if set(data["fifo_expire"])!=set(data["edf"]):raise SystemExit("unpaired waves")
    keys=sorted(data["edf"])
    if len(keys)<10:raise SystemExit("insufficient measured waves")
    out={"strict_global_ttfa_ms":200,"arms":{},"matched_waves":len(keys),
       "cost_status":"NOT VERIFIED: no billed, matched machine; only hardware-normalized rates on CI",
       "definition":"4 turns <=200ms each from first request, M0=0, PCM<=1LSB; all offered included"}
    for arm,rr in data.items():
        rows=[rr[k] for k in keys]
        if any(abs(r["activity"]-.10)>1e-8 for r in rows):raise SystemExit("wrong activity")
        turns=[t for r in rows for seq in r["turns"].values() for t in seq]
        tt=[t["ttfa_ms"] for t in turns if t["status"]=="completed"]
        offered=sum(r["offered_sessions"] for r in rows)
        good=sum(all(t.get("status")=="completed" and t.get("ttfa_ms",float("inf"))<=200 and t.get("m0_episodes",1)==0 and t.get("max_abs_lsb") is not None and t["max_abs_lsb"]<=1 for t in seq) for r in rows for seq in r["turns"].values())
        duration=sum(r["elapsed_s"] for r in rows)
        rejected=sum(t["status"]=="rejected" for t in turns)
        m0=sum(t.get("m0_episodes",0)>0 for t in turns)
        pcm=sum(t.get("max_abs_lsb") is not None and t["max_abs_lsb"]>1 for t in turns)
        q=quant(tt,.99)
        out["arms"][arm]={"offered":offered,"strict_useful":good,"success_rate":good/offered,
          "completed_turns":len(tt),"rejected_turns":rejected,"m0_affected_turns":m0,
          "pcm_outside_1lsb":pcm,"completed_turn_ttfa_p99_ms":q,
          "global_sla_gate":q is not None and q<=200 and rejected==0 and m0==0 and pcm==0 and good==offered,
          "measured_batch_wall_s":duration,"batch_useful_per_hour":good*3600/duration,
          "warning":"Batch rate includes 20s idle, excludes server build/model load; NOT sustained SES/h"}
    rng=random.Random(20261109);dif=[]
    for _ in range(20000):
        sample=[keys[rng.randrange(len(keys))] for _ in keys]
        n=sum(data["edf"][k]["offered_sessions"] for k in sample)
        def count(arm):
            return sum(all(t.get("status")=="completed" and t.get("ttfa_ms",float("inf"))<=200 and t.get("m0_episodes",1)==0 and t.get("max_abs_lsb") is not None and t["max_abs_lsb"]<=1 for t in seq) for k in sample for seq in data[arm][k]["turns"].values())
        dif.append(100*(count("edf")-count("fifo_expire"))/n)
    out["edf_minus_fifo_success_pp"]={"point":100*(out["arms"]["edf"]["success_rate"]-out["arms"]["fifo_expire"]["success_rate"]),"paired_wave_bootstrap_95pct":[quant(dif,.025),quant(dif,.975)]}
    (root/"final-confirmation.json").write_text(json.dumps(out,indent=2)+"\n")
    print(json.dumps(out,indent=2))
if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("--root",required=True);main(p.parse_args())
