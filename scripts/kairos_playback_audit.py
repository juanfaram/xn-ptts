#!/usr/bin/env python3
"""Offline KAIROS playback audit. No server run, no network, no changed thresholds.

Usage: python3 scripts/kairos_playback_audit.py evidence.zip --output audit.json
Model: immediate, uninterrupted playback starts at first PCM audio arrival.
For chunk i, reserve_before_i = sum(duration[0:i]) - (arrival[i]-arrival[0]).
A negative reserve is a predicted starvation under this ideal model, NOT
proof of an audible interruption on an actual playback device.
"""
import argparse, hashlib, json, math, re, statistics, zipfile
from pathlib import Path

def audit(archive):
    with zipfile.ZipFile(archive) as z:
        names=set(z.namelist())
        manifest=json.loads(z.read("manifest.json").decode().removesuffix("\\n")) if "manifest.json" in names else None
        manifest_errors=[]
        if manifest:
            for name,expected in manifest.get("sha256_files",{}).items():
                if name not in names:
                    manifest_errors.append("missing "+name)
                elif hashlib.sha256(z.read(name)).hexdigest()!=expected:
                    manifest_errors.append("sha256 mismatch "+name)
        wave_files=sorted((n for n in names if re.fullmatch(r"k1-r\d+-ratios\.json",n)),
                          key=lambda n:int(re.search(r"-r(\d+)",n).group(1)))
        waves=[]
        for name in wave_files:
            flows=json.loads(z.read(name))
            for flow in flows:
                fragments=flow.get("fragments",[])
                if not fragments:
                    waves.append({"file":name,"flow":flow.get("flow"),"error":"no fragments"})
                    continue
                arrivals=[float(f["ts_recv_monotonic_s"]) for f in fragments]
                durations=[float(f["frag_ms"]) for f in fragments]
                if any(x<=0 for x in durations) or any(arrivals[i]<arrivals[i-1] for i in range(1,len(arrivals))):
                    raise ValueError("invalid duration or unordered timestamps: "+name)
                elapsed=[(t-arrivals[0])*1000 for t in arrivals]
                reserve=[];audio_before=0.0;gap_positions=[];risk_positions=[]
                for i,(e,d) in enumerate(zip(elapsed,durations)):
                    lead=audio_before-e
                    if i>0:
                        reserve.append(lead)
                        if lead<0:risk_positions.append(i)
                        if (arrivals[i]-arrivals[i-1])*1000>durations[i-1]:
                            gap_positions.append(i)
                    audio_before+=d
                waves.append({"file":name,"flow":flow.get("flow"),
                              "fragments":len(fragments),"audio_ms":round(sum(durations),3),
                              "last_arrival_since_first_ms":round(elapsed[-1],3),
                              "long_intervals":len(gap_positions),"long_interval_indices":gap_positions,
                              "predicted_starvation_events":len(risk_positions),
                              "predicted_starvation_indices":risk_positions,
                              "minimum_reserve_after_first_ms":round(min(reserve),3) if reserve else None,
                              "minimum_reserve_index":reserve.index(min(reserve))+1 if reserve else None,
                              "first_10_reserve_ms":[round(v,3) for v in reserve[:9]],
                              "max_negative_reserve_ms":round(min(0,min(reserve)),3) if reserve else 0})
        flows=[]
        if "flows.csv" in names:
            import csv,io
            flows=list(csv.DictReader(io.StringIO(z.read("flows.csv").decode())))
        hashes=sorted(set(r.get("pcm16_sha256","") for r in flows if r.get("pcm16_sha256")))
        rss=[{"repeat":r.get("repeat"),"rss_mib":float(r["memory_rss_mib"])} for r in flows if r.get("memory_rss_mib")]
        return {"status":"diagnostic_not_SLA_certification",
                "archive_sha256":hashlib.sha256(Path(archive).read_bytes()).hexdigest(),
                "manifest_verified":manifest is not None and not manifest_errors,
                "manifest_errors":manifest_errors,
                "playback_assumption":"instant playback from first arrival, no device buffering, no pause",
                "clock":"client monotonic timestamps only; server emission not measured",
                "waves":waves,"wave_count":len(waves),
                "total_long_intervals":sum(w.get("long_intervals",0) for w in waves),
                "total_predicted_starvation_events":sum(w.get("predicted_starvation_events",0) for w in waves),
                "unique_pcm16_hashes":hashes,"rss_by_wave":rss,
                "warnings":["No actual audio device observed; zero predicted starvation is not zero audible glitches.",
                            "Single k1 original-server host, not a C improvement.",
                            "RSS values sampled at wave boundaries, not per-session retained state."]}
if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("evidence",type=Path)
    p.add_argument("--output",type=Path,default=Path("playback-audit.json"))
    args=p.parse_args()
    result=audit(args.evidence)
    args.output.write_text(json.dumps(result,indent=2)+"\n")
    print(json.dumps({"waves":result["wave_count"],"long_intervals":result["total_long_intervals"],
                      "predicted_starvation":result["total_predicted_starvation_events"],
                      "manifest_verified":result["manifest_verified"]},indent=2))
