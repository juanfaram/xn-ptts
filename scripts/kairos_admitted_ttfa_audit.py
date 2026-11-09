#!/usr/bin/env python3
"""Audit TTFA from proxy admission against client first audio on the same runner.
Usage: python scripts/kairos_admitted_ttfa_audit.py artifact.zip
"""
import argparse,zipfile,json,math,statistics
def percentile(x,q):
    a=sorted(x);return a[math.ceil(q*len(a))-1] if a else None
def main(path):
    with zipfile.ZipFile(path) as z:
        logs=[json.loads(x) for x in z.read("fifo_expire/proxy.log").decode().splitlines() if x.startswith("{")]
        rows=json.loads(z.read("fifo_expire/runs.json"))
    admissions={x["trace_id"]:x for x in logs if x.get("event")=="admission"}
    measures=[]
    for row in rows:
        if row["warmup"]:continue
        for turns in row["turns"].values():
            for t in turns:
                if t.get("status")!="completed":continue
                a=admissions.get(t.get("trace_id"))
                if not a:raise ValueError("missing admission for "+str(t.get("trace_id")))
                admitted=(t["t_first_audio_ns"]-a["t_admission_ns"])/1e6
                if admitted<0:raise ValueError("non-monotonic clocks")
                measures.append({"trace_id":t["trace_id"],"ttfa_request_ms":t["ttfa_ms"],
                                 "ttfa_admitted_ms":admitted,"queue_ms":a["queue_ms"]})
    if not measures:raise ValueError("no measured turns")
    out={"completed_turns":len(measures),"ttfa_request_p99_ms":percentile([x["ttfa_request_ms"] for x in measures],.99),
         "ttfa_admitted_p99_ms":percentile([x["ttfa_admitted_ms"] for x in measures],.99),
         "max_queue_ms":max(x["queue_ms"] for x in measures),
         "request_gate_200ms_pass":percentile([x["ttfa_request_ms"] for x in measures],.99)<=200,
         "admission_gate_28ms_pass":percentile([x["ttfa_admitted_ms"] for x in measures],.99)<=28,
         "caveat":"Small pilot; same-run monotonic clock. Does not establish production p99."}
    print(json.dumps(out,indent=2))
if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("artifact_zip");a=p.parse_args();main(a.artifact_zip)
