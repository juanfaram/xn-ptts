#!/usr/bin/env python3
"""Minimal real-Phonon paired eviction pilot: four turns, same stream seeds, server RSS.
Runs once per process: control KAIROS_EVICT_AFTER_FLUSH=0 and experiment =1.
"""
import argparse,asyncio,json,time,os,resource
from pathlib import Path
from kairos_multiturn import setup,generate,lsb
def rss(pid):
    with open(f"/proc/{pid}/status") as f:
        for s in f:
            if s.startswith("VmRSS:"):return int(s.split()[1])*1024
    raise RuntimeError("VmRSS missing")
async def main(a):
    out=Path(a.output);out.mkdir(parents=True,exist_ok=True)
    ws=await setup(a.url)
    records=[];raw=[]
    try:
        for turn in range(4):
            if turn:await asyncio.sleep(a.idle)
            before=rss(a.pid)
            t0=time.perf_counter()
            x=await generate(ws,turn,200,reference=None,capture_fragments=True)
            elapsed=time.perf_counter()-t0
            pcm=x.pop("_pcm",b"")
            raw.append(pcm)
            after=rss(a.pid)
            records.append({"turn":turn+1,"rss_before_bytes":before,"rss_after_bytes":after,
               "request_elapsed_ms":round(elapsed*1000,3),**x})
            print(json.dumps({"turn":turn+1,"status":x["status"],"ttfa_ms":x.get("ttfa_ms"),
              "rss_before_mib":round(before/1048576,2),"rss_after_mib":round(after/1048576,2)}),flush=True)
        await asyncio.sleep(2)
        final_rss=rss(a.pid)
    finally:await ws.close()
    result={"arm":a.arm,"pid":a.pid,"rss_final_bytes":final_rss,"records":records,
      "pcm_lengths":[len(v) for v in raw],"note":"RSS is allocator-dependent; four-turn single-session pilot cannot establish per-session 50MiB reclaim."}
    (out/"measure.json").write_text(json.dumps(result,indent=2)+"\n")
    for i,pcm in enumerate(raw): (out/f"turn-{i+1}.pcm").write_bytes(pcm)
if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("--url",default="ws://127.0.0.1:8080/speech/tts")
    p.add_argument("--pid",type=int,required=True);p.add_argument("--arm",required=True)
    p.add_argument("--output",required=True);p.add_argument("--idle",type=float,default=20)
    asyncio.run(main(p.parse_args()))
