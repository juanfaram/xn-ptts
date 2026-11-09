#!/usr/bin/env python3
"""Independent offline validation of four-turn economic verdict artifacts."""
import argparse,json,math
from pathlib import Path

ARMS=("b8","fifo_expire","edf")
def main():
    p=argparse.ArgumentParser()
    p.add_argument("root",type=Path)
    args=p.parse_args()
    data={}
    issues=[]
    for arm in ARMS:
        f=args.root/arm/"runs.json"
        if not f.exists():
            issues.append(f"{arm}: missing runs.json");continue
        rows=json.loads(f.read_text())
        data[arm]={}
        for row in rows:
            key=(row["activity"],row["repeat"])
            if key in data[arm]:issues.append(f"{arm}: duplicate {key}")
            outcomes=row["turns"]
            if len(outcomes)!=row["offered_sessions"]:issues.append(f"{arm} {key}: offered denominator mismatch")
            for sid,turns in outcomes.items():
                if len(turns)!=4:issues.append(f"{arm} {key}: session {sid} has {len(turns)} turns")
            useful=sum(all(t.get("valid") is True for t in turns) for turns in outcomes.values())
            if useful!=row["useful_sessions"]:issues.append(f"{arm} {key}: useful mismatch {useful} vs {row['useful_sessions']}")
            if row["invalid_sessions"]+useful!=row["offered_sessions"]:
                issues.append(f"{arm} {key}: accounting mismatch")
            data[arm][key]=row
    if len(data)==3:
        keys=[set(data[arm]) for arm in ARMS]
        if not all(x==keys[0] for x in keys[1:]):issues.append("Unmatched (activity,repeat) blocks")
        for key in set.intersection(*keys):
            n={data[arm][key]["offered_sessions"] for arm in ARMS}
            if len(n)!=1:issues.append(f"{key}: offered denominator differs")
            ids=[set(data[arm][key]["turns"]) for arm in ARMS]
            if not all(x==ids[0] for x in ids[1:]):issues.append(f"{key}: session IDs differ")
    result={"schema":"kairos-four-turn-evidence-audit-v1",
        "arms_present":sorted(data),"matched_blocks":len(set.intersection(*(set(v) for v in data.values()))) if len(data)==3 else 0,
        "issues":issues,"pass":not issues,
        "limitations":["Matching session IDs does not prove identical arrival timestamps.",
                       "Four-turn M0 is not equivalent to three-turn M1/v3.",
                       "Proxy EDF is not automatically equivalent to Rust EDF.",
                       "Short-batch SES/hour is not sustained capacity or billed runner cost."]}
    print(json.dumps(result,indent=2))
    if issues:raise SystemExit(1)
if __name__=="__main__":main()
