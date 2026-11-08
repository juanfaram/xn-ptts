#!/usr/bin/env python3
"""Nonblocking f32 identity/tolerance report. PCM16 equivalent: 1 LSB max.
A failure to compare is explicitly INCONCLUSIVE, never silently PASS."""
import csv, json, math, struct, sys
from pathlib import Path

def read_hash(path):
    with open(path,newline="") as f:
        rows=list(csv.DictReader(f))
    if not rows: raise ValueError(f"empty {path}")
    return rows[0]["sha256"]

def samples(path):
    raw=Path(path).read_bytes()
    if len(raw)%4: raise ValueError(f"invalid f32le {path}")
    return struct.unpack("<"+str(len(raw)//4)+"f",raw)

def pcm16(x):
    if not math.isfinite(x): raise ValueError("nonfinite sample")
    return max(-32768,min(32767,round(x*32768)))

def compare(a,b):
    x,y=samples(a),samples(b)
    if len(x)!=len(y):return {"status":"FAIL_LENGTH","samples_a":len(x),"samples_b":len(y)}
    if not x:return {"status":"INCONCLUSIVE_EMPTY"}
    diffs=[abs(pcm16(v)-pcm16(w)) for v,w in zip(x,y)]
    mx=max(diffs)
    return {"status":"PASS_TOLERANCE_1LSB" if mx<=1 else "FAIL_TOLERANCE_1LSB",
            "max_pcm16_lsb":mx,"samples":len(x),"different_samples":sum(d>0 for d in diffs)}

def main():
    root=Path("out")
    ref=read_hash(root/"k1_r1/flows.csv")
    second=read_hash(root/"k1_r2/flows.csv")
    report={"reference_hash":ref,"repeat_hash":second,
            "k1":{"status":"PASS_IDENTITY" if ref==second else "NONDETERMINISTIC"}}
    if ref!=second:
        report["k1"]["tolerance"]=compare(root/"k1_r1/audio_w0_f0.f32le",root/"k1_r2/audio_w0_f0.f32le")
    k2=root/"k2/flows.csv"
    if k2.exists():
        with k2.open(newline="") as f:
            rows=list(csv.DictReader(f))
        flows=sorted({int(r["flow"]) for r in rows})
        report["k2"]={}
        for flow in flows:
            h=next(r["sha256"] for r in rows if int(r["flow"])==flow)
            item={"status":"PASS_IDENTITY" if h==ref else "HASH_MISMATCH","hash":h}
            if h!=ref:
                item["tolerance"]=compare(root/"k1_r1/audio_w0_f0.f32le",root/f"k2/audio_w0_f{flow}.f32le")
            report["k2"][str(flow)]=item
    (root/"hash-report.json").write_text(json.dumps(report,indent=2)+"\n")
    print(json.dumps(report,indent=2))

if __name__=="__main__":
    try:main()
    except Exception as exc:
        print("INCONCLUSIVE_HASH_ANALYSIS:",repr(exc),file=sys.stderr)
        sys.exit(1)
