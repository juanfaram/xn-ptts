#!/usr/bin/env python3
"""Join client and proxy timestamps from original trace ZIP; no new load."""
import argparse,collections,json,math,zipfile
from pathlib import Path

def pct(values,q):
    if not values:return None
    values=sorted(values)
    return round(values[min(len(values)-1,math.ceil(q*len(values))-1)],3)

def main():
    p=argparse.ArgumentParser()
    p.add_argument("archive",type=Path)
    p.add_argument("--output",type=Path)
    args=p.parse_args()
    result={"schema":"kairos-queue-vs-generation-v1","source_run_id":42616852294,
            "source_commit":"eb0dcb7b16dd592b2d7c956bc954f67a06a572cd",
            "units":"milliseconds","policies":{}}
    with zipfile.ZipFile(args.archive) as z:
        for arm in ("fifo_expire","edf"):
            events=collections.defaultdict(dict)
            for line in z.read(f"{arm}/proxy.log").decode().splitlines():
                try:e=json.loads(line)
                except (ValueError,TypeError):continue
                if "trace_id" in e:events[e["trace_id"]][e["event"]]=e
            rows=json.loads(z.read(f"{arm}/runs.json"))
            result["policies"][arm]={}
            for activity in (.25,.50):
                measures=[]
                for row in rows:
                    if float(row["activity"])!=activity:continue
                    for turns in row["turns"].values():
                        for t in turns:
                            if t.get("status")!="completed":continue
                            e=events.get(t.get("trace_id"),{})
                            if "admission" not in e:continue
                            a=e["admission"]
                            queue=(a["t_admission_ns"]-a["t_enqueue_ns"])/1e6
                            upstream=(t["t_first_audio_ns"]-a["t_admission_ns"])/1e6
                            before=(a["t_enqueue_ns"]-t["t_request_ns"])/1e6
                            measures.append((queue,upstream,before,t["ttfa_ms"],t["m0_episodes"]))
                def stats(i):
                    v=[m[i] for m in measures]
                    return {"p50":pct(v,.5),"p95":pct(v,.95),"p99":pct(v,.99)}
                result["policies"][arm][str(activity)]={
                    "matched_completed_turns":len(measures),
                    "queue_ms":stats(0),"admission_to_first_audio_ms":stats(1),
                    "client_to_enqueue_ms":stats(2),"ttfa_request_ms":stats(3),
                    "m0_stall_completed_turns":sum(m[4]>0 for m in measures),
                    "queue_fraction_of_ttfa_p50":pct([m[0]/m[3] for m in measures if m[3]>0],.5)}
    result["limitations"]=["Measured in short four-turn diagnostic; not sustained utilization.",
        "Client and proxy monotonic clocks are comparable because processes run on the same host.",
        "Completed-turn percentiles exclude rejected turns; those count as session failures.",
        "No production SES/euro claim from this trace."]
    raw=json.dumps(result,indent=2)+"\n"
    if args.output:
        args.output.parent.mkdir(parents=True,exist_ok=True)
        args.output.write_text(raw)
    print(raw,end="")

if __name__=="__main__":main()
