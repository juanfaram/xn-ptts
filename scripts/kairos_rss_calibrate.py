#!/usr/bin/env python3
"""Measure original-server idle-connection RSS at N=10,25,50,100."""
import argparse, asyncio, json, os, statistics
from pathlib import Path
import websockets

def rss_kib(pid):
    for line in Path(f"/proc/{pid}/status").read_text().splitlines():
        if line.startswith("VmRSS:"):
            return int(line.split()[1])
    raise RuntimeError("VmRSS unavailable")

def mem_kib():
    data={}
    for line in Path("/proc/meminfo").read_text().splitlines():
        k,_,v=line.partition(":")
        data[k]=int(v.split()[0])
    return data["MemTotal"]

async def run(args):
    sessions=[]
    results=[]
    base=rss_kib(args.pid)
    for target in (10,25,50,100):
        while len(sessions)<target:
            ws=await websockets.connect(args.url,open_timeout=10,max_size=2**22)
            await ws.send(json.dumps({"type":"setup","json_config":"","model_name":"",
                 "output_format":"pcm","voice":None,"voice_id":None,"voice_emb":None}))
            while True:
                msg=json.loads(await asyncio.wait_for(ws.recv(),15))
                if msg.get("type")=="ready":break
                if msg.get("type")=="error":raise RuntimeError(msg)
            sessions.append(ws)
        await asyncio.sleep(1)
        values=[]
        for _ in range(5):
            values.append(rss_kib(args.pid))
            await asyncio.sleep(.2)
        results.append({"connections":target,"rss_kib_median":statistics.median(values),"rss_kib_samples":values})
    for ws in sessions:await ws.close()
    xs=[0]+[r["connections"] for r in results]
    ys=[base]+[r["rss_kib_median"] for r in results]
    xm=statistics.mean(xs);ym=statistics.mean(ys)
    slope=sum((x-xm)*(y-ym) for x,y in zip(xs,ys))/sum((x-xm)**2 for x in xs)
    intercept=ym-slope*xm
    budget=.8*mem_kib()
    limit=max(0,int((budget-intercept)/slope)) if slope>0 else None
    out={"pid":args.pid,"base_rss_kib":base,"points":results,
         "fit_intercept_kib":intercept,"fit_slope_kib_per_connection":slope,
         "memory_total_kib":mem_kib(),"budget_80pct_kib":budget,
         "limit_connections":limit,"warning":"Extrapolation beyond 100 connections is not validated"}
    Path(args.output).write_text(json.dumps(out,indent=2)+"\n")
    print(json.dumps(out,indent=2))

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--pid",type=int,required=True)
    p.add_argument("--url",default="ws://127.0.0.1:8080/speech/tts")
    p.add_argument("--output",default="out/rss-calibration.json")
    a=p.parse_args()
    asyncio.run(run(a))
