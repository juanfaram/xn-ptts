#!/usr/bin/env python3
"""Offline audit of first-load artifacts: no execution or assumptions about permit hold."""
import argparse, json, statistics, zipfile
from pathlib import Path

def percentile(xs,p):
    if not xs:return None
    xs=sorted(xs); return xs[min(len(xs)-1,int((len(xs)-1)*p))]

def audit(path):
    with zipfile.ZipFile(path) as z:
        raw=json.loads(z.read("10-1.json"))
    sessions=raw["sessions"]
    turns=[t for s in sessions for t in s["turns"]]
    attempted=[t for t in turns if "request_ns" in t]
    audio=[t for t in attempted if t.get("chunks")]
    spans=[(t["chunks"][-1]["arrival_ns"]-t["chunks"][0]["arrival_ns"])/1e9 for t in audio]
    starts=[t["request_ns"] for t in attempted]
    return {
        "arm":raw["arm"],"activity_nominal_pct":raw["activity_pct"],
        "scheduled_generations":len(turns),"actually_sent_generations":len(attempted),
        "not_sent_due_to_prior_failure":len(turns)-len(attempted),
        "sent_by_turn":[sum(t.get("turn")==i for t in attempted) for i in range(3)],
        "actual_request_window_s":(max(starts)-min(starts))/1e9 if len(starts)>1 else None,
        "observed_audio_generations":len(audio),
        "first_to_last_audio_chunk_span_median_s":statistics.median(spans) if spans else None,
        "first_to_last_audio_chunk_span_p95_s":percentile(spans,.95),
        "valid_generations_preliminary":raw["valid_preliminary"],
        "valid_complete_sessions_preliminary":raw["valid_sessions_preliminary"],
        "important":"Audio chunk span is NOT admission-to-release permit occupancy; rho cannot be certified from these artifacts."
    }

def main():
    p=argparse.ArgumentParser()
    p.add_argument("artifacts",nargs="+",type=Path)
    args=p.parse_args()
    reports=[audit(path) for path in args.artifacts]
    print(json.dumps(reports,indent=2))
    assert len({r["arm"] for r in reports})==len(reports),"Duplicate arm"
    assert all(r["scheduled_generations"]==180 for r in reports)

if __name__=="__main__":main()
