#!/usr/bin/env python3
"""Audit all offered proxy flush requests, including rejected; compute occupancy 1s bins."""
import json,sys,collections,math
from pathlib import Path
def percentile(xs,p):
    return sorted(xs)[max(0,math.ceil(len(xs)*p)-1)] if xs else None
def main(path,out):
    events=[]
    for line in Path(path).read_text().splitlines():
        try:
            obj=json.loads(line)
            if obj.get("event") in ("arrival","admission","rejection","release"):events.append(obj)
        except ValueError:pass
    by=collections.defaultdict(dict)
    for e in events:
        by[e["trace_id"]][e["event"]]=e
    rows=[]
    for tid,x in by.items():
        arrival=x.get("arrival");adm=x.get("admission");rej=x.get("rejection");rel=x.get("release")
        if not arrival:continue
        t=arrival["t_enqueue_ns"]
        row={"trace_id":tid,"deadline_ms":arrival.get("deadline_ms"),"status":"released" if rel else ("rejected" if rej else ("admitted_unreleased" if adm else "unresolved")),
             "wait_ms":((adm["t_admission_ns"] if adm else rej["t_reject_ns"])-t)/1e6 if adm or rej else None,
             "hold_ms":(rel["t_release_ns"]-adm["t_admission_ns"])/1e6 if rel and adm else None,
             "reason":rej.get("reason") if rej else None}
        rows.append(row)
    events_ts=[]
    for x in by.values():
        if "admission" in x:events_ts.append((x["admission"]["t_admission_ns"],1))
        if "release" in x:events_ts.append((x["release"]["t_release_ns"],-1))
    events_ts.sort()
    occupancy=0;max_occupancy=0
    for _,delta in events_ts:
        occupancy+=delta;max_occupancy=max(max_occupancy,occupancy)
        if occupancy<0:raise RuntimeError("negative permit occupancy")
    groups={}
    for deadline in sorted(set(r["deadline_ms"] for r in rows)):
        subset=[r for r in rows if r["deadline_ms"]==deadline]
        waits=[r["wait_ms"] for r in subset if r["wait_ms"] is not None]
        groups[str(deadline)]={"offered":len(subset),"rejected":sum(r["status"]=="rejected" for r in subset),
            "unresolved":sum(r["status"]=="unresolved" for r in subset),
            "wait_p50_ms":percentile(waits,.5),"wait_p95_ms":percentile(waits,.95)}
    result={"arrivals":len(rows),"admitted":sum("admission" in x for x in by.values()),
            "rejected":sum("rejection" in x for x in by.values()),
            "released":sum("release" in x for x in by.values()),
            "max_active":max_occupancy,"groups":groups,"rows":rows}
    Path(out).write_text(json.dumps(result,indent=2)+"\n")
    print(json.dumps({k:v for k,v in result.items() if k!="rows"},indent=2))
if __name__=="__main__":main(sys.argv[1],sys.argv[2])
