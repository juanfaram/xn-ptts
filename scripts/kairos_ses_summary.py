#!/usr/bin/env python3
"""Summarize actual per-repetition SES without silently certifying continuity."""
import argparse, json, math, statistics
from pathlib import Path

def main():
    p=argparse.ArgumentParser()
    p.add_argument("folder",type=Path)
    p.add_argument("--arm",required=True)
    p.add_argument("--expected",type=int,default=1)
    p.add_argument("--rate",type=float,default=0.1378)
    a=p.parse_args()
    records=[]
    for f in sorted(a.folder.glob("[0-9]*-[0-9]*.json")):
        x=json.loads(f.read_text())
        if x.get("arm")!=a.arm:continue
        if x.get("offered_sessions")!=60 or x.get("offered")!=180:
            raise SystemExit(f"Invalid denominator: {f}")
        causes=x.get("invalid_sessions_by_primary_reason",{})
        valid=x["valid_sessions_preliminary"]
        if valid+sum(causes.values())!=60:
            raise SystemExit(f"Session accounting does not reconcile: {f}")
        records.append({"activity":x["activity_pct"],"repeat":x["repeat"],
            "valid_sessions_preliminary":valid,
            "invalid_sessions":60-valid,
            "invalid_causes":causes,
            "reach_240_rate":x["reach_240_rate"],
            "duration_s":x["duration_s"],
            "cost_reference_eur":x["duration_s"]*a.rate/3600})
    total_cost=sum(x["cost_reference_eur"] for x in records)
    total_valid=sum(x["valid_sessions_preliminary"] for x in records)
    out={"arm":a.arm,"repetitions_found":len(records),"expected_repetitions":a.expected,
         "complete":len(records)==a.expected,
         "reference_rate_eur_hour":a.rate,
         "reference_cost_eur":total_cost,
         "valid_sessions_preliminary":total_valid,
         "ses_per_1000_reference_eur_preliminary":1000*total_valid/total_cost if total_cost else None,
         "continuity_v3_certified":False,
         "repetitions":records}
    (a.folder/"summary.json").write_text(json.dumps(out,indent=2)+"\n")
    print(json.dumps({k:v for k,v in out.items() if k!="repetitions"},indent=2))
    if not out["complete"]:raise SystemExit("INCOMPLETE: missing repetitions")

if __name__=="__main__":main()
