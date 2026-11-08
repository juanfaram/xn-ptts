#!/usr/bin/env python3
"""M0 frozen v2 and M1 two-chunk prebuffer, evaluated on the same fragment traces."""
import json,sys,zipfile
from pathlib import Path
from kairos_playback_v2 import simulate

def m1(frags):
    if len(frags)<2:raise ValueError("M1 requires two chunks")
    times=[float(x["ts_recv_monotonic_s"])*1000 for x in frags]
    durations=[float(x["frag_ms"]) for x in frags]
    buffer=sum(durations[:2]);episodes=[]
    for i in range(2,len(frags)):
        dt=times[i]-times[i-1]
        stall=max(0,dt-buffer)
        if stall>1e-7:episodes.append({"idx":i,"duration_ms":round(stall,6)})
        buffer=max(0,buffer-dt)+durations[i]
    return {"episodes":episodes,"episode_count":len(episodes),"stall_ms":round(sum(e["duration_ms"] for e in episodes),6),"max_stall_ms":max((e["duration_ms"] for e in episodes),default=0),"prebuffer_wait_ms":round(times[1]-times[0],6)}

def main(zip_path,out):
    rows=[]
    with zipfile.ZipFile(zip_path) as z:
        names=sorted(n for n in z.namelist() if n.startswith("k3-r") and n.endswith("-ratios.json"))
        for name in names:
            for flow in json.loads(z.read(name)):
                f=flow["fragments"]
                rows.append({"wave":name,"flow":flow["flow"],"M0":simulate(f),"M1":m1(f)})
    result={"definition":"M0 immediate; M1 start on second fragment; virtual clock; same traces","rows":rows,
            "M0_total_episodes":sum(r["M0"]["episode_count"] for r in rows),
            "M1_total_episodes":sum(r["M1"]["episode_count"] for r in rows),
            "M0_total_stall_ms":round(sum(r["M0"]["total_stall_ms"] for r in rows),6),
            "M1_total_stall_ms":round(sum(r["M1"]["stall_ms"] for r in rows),6)}
    Path(out).write_text(json.dumps(result,indent=2)+"\n")
    print(json.dumps({k:v for k,v in result.items() if k!="rows"},indent=2))
if __name__=="__main__":main(sys.argv[1],sys.argv[2])
