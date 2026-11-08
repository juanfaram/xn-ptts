#!/usr/bin/env python3
"""Frozen KAIROS v2: virtual immediate-start playback, resume after starvation.
Client monotonic timestamps only; does not establish audible device underruns.
"""
import argparse,csv,hashlib,json,re,zipfile
from pathlib import Path

def simulate(frags):
    if not frags:raise ValueError("empty trace")
    ts=[float(f["ts_recv_monotonic_s"])*1000 for f in frags]
    ds=[float(f["frag_ms"]) for f in frags]
    if any(d<=0 for d in ds) or any(ts[i]<ts[i-1] for i in range(1,len(ts))):raise ValueError("bad trace")
    buffer=ds[0];lead=0;episodes=[];reserves=[];long=[]
    for i in range(1,len(frags)):
        dt=ts[i]-ts[i-1]
        if dt>ds[i-1]:long.append(i)
        lead+=ds[i-1]-dt
        stall=max(0,dt-buffer)
        buffer=max(0,buffer-dt)
        if stall>1e-7:episodes.append({"idx":i,"duration_ms":round(stall,6)})
        reserves.append({"idx":i,"reserve_before_ms":round(buffer,6),"uninterrupted_lead_ms":round(lead,6)})
        buffer+=ds[i]
    return {"fragments":len(frags),"audio_ms":round(sum(ds),6),
            "long_interval_indices":long,"long_intervals":len(long),
            "episodes":episodes,"episode_count":len(episodes),
            "total_stall_ms":round(sum(x["duration_ms"] for x in episodes),6),
            "max_stall_ms":max((x["duration_ms"] for x in episodes),default=0),
            "max_uninterrupted_deficit_ms":round(max(0,-min((r["uninterrupted_lead_ms"] for r in reserves),default=0)),6),
            "min_uninterrupted_lead_ms":min((r["uninterrupted_lead_ms"] for r in reserves),default=None),
            "first_10":reserves[:9]}

def audit(path,allow_legacy=False):
    with zipfile.ZipFile(path) as z:
        names=set(z.namelist())
        if "manifest.json" not in names:raise ValueError("manifest missing")
        raw=z.read("manifest.json")
        try:manifest=json.loads(raw);legacy=False
        except json.JSONDecodeError:
            if not allow_legacy or not raw.endswith(b'}\\n'):raise
            manifest=json.loads(raw[:-2]);legacy=True
        for name,sha in manifest.get("sha256_files",{}).items():
            if name not in names or hashlib.sha256(z.read(name)).hexdigest()!=sha:raise ValueError("hash mismatch: "+name)
        files=sorted((n for n in names if re.fullmatch(r"k\d+-r\d+-ratios\.json",n)),
                     key=lambda s:tuple(map(int,re.search(r"k(\d+)-r(\d+)",s).groups())))
        # Regex strings above intentionally use single backslash in resulting Python source.
        waves=[]
        for name in files:
            for flow in json.loads(z.read(name)):
                entry=simulate(flow["fragments"]);entry.update(file=name,flow=flow.get("flow"));waves.append(entry)
        rows=list(csv.DictReader(z.read("flows.csv").decode().splitlines())) if "flows.csv" in names else []
        return {"model":"v2 immediate-start, virtual clock, pause/resume; no prebuffer",
                "zip_sha256":hashlib.sha256(Path(path).read_bytes()).hexdigest(),
                "legacy_manifest":legacy,"verified_files":len(manifest.get("sha256_files",{})),
                "waves":waves,"total_episodes":sum(x["episode_count"] for x in waves),
                "total_stall_ms":round(sum(x["total_stall_ms"] for x in waves),6),
                "pcm16_hashes":sorted({r["pcm16_sha256"] for r in rows if r.get("pcm16_sha256")}),
                "warning":"Virtual playback model, not a measured audible SLA"}
if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("zip",type=Path);p.add_argument("--output",type=Path,default=Path("playback-v2.json"));p.add_argument("--allow-legacy-manifest",action="store_true")
    a=p.parse_args();j=audit(a.zip,a.allow_legacy_manifest);a.output.write_text(json.dumps(j,indent=2)+"\n")
    print(json.dumps({"waves":len(j["waves"]),"episodes":j["total_episodes"],"stall_ms":j["total_stall_ms"]}))
