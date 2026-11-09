#!/usr/bin/env python3
"""Calibrate original Phonon server retained WS session RSS; no generation.
Local loopback only. All sessions remain open through the full 10/25/50/100 staircase.
"""
import argparse,asyncio,json,math,os,time
from pathlib import Path
from websockets.asyncio.client import connect

def rss_kib(pid):
    for line in Path(f"/proc/{pid}/status").read_text().splitlines():
        if line.startswith("VmRSS:"):return int(line.split()[1])
    raise RuntimeError("VmRSS unavailable")
def ram_kib():
    for line in Path("/proc/meminfo").read_text().splitlines():
        if line.startswith("MemTotal:"):return int(line.split()[1])
    raise RuntimeError("MemTotal unavailable")
def fit(points):
    n=len(points);mx=sum(x for x,y in points)/n;my=sum(y for x,y in points)/n
    denom=sum((x-mx)**2 for x,y in points)
    slope=sum((x-mx)*(y-my) for x,y in points)/denom
    intercept=my-slope*mx
    residual=[y-(intercept+slope*x) for x,y in points]
    ss=sum((y-my)**2 for x,y in points)
    r2=1-sum(v*v for v in residual)/ss if ss else None
    return intercept,slope,r2
async def main(a):
    if not a.url.startswith(("ws://127.0.0.1:","ws://localhost:")):raise SystemExit("local only")
    output=Path(a.output);output.parent.mkdir(parents=True,exist_ok=True)
    held=[];rows=[];ram=ram_kib();budget=.8*ram
    async def sample(n,phase):
        await asyncio.sleep(a.settle)
        readings=[]
        for _ in range(5):
            readings.append(rss_kib(a.pid))
            await asyncio.sleep(.2)
        row={"connections":n,"phase":phase,"rss_kib":max(readings),"rss_mib":round(max(readings)/1024,3),"rss_samples_kib":readings,"monotonic_s":time.monotonic()}
        rows.append(row)
        output.write_text(json.dumps({"rows":rows},indent=2)+"\n")
        print(json.dumps(row),flush=True)
    try:
        await sample(0,"baseline")
        for target in (10,25,50,100):
            for i in range(len(held),target):
                ws=await connect(a.url,open_timeout=15,max_size=2**23)
                try:
                    await ws.send(json.dumps({"type":"setup","json_config":"","model_name":"","output_format":"pcm","voice":None,"voice_id":None,"voice_emb":None}))
                    async with asyncio.timeout(25):
                        while True:
                            msg=json.loads(await ws.recv())
                            if msg.get("type")=="error":raise RuntimeError(f"setup {i}: {msg}")
                            if msg.get("type")=="ready":break
                except:
                    await ws.close()
                    raise
                held.append(ws)
            await sample(target,"held_ready_idle")
        intercept,slope,r2=fit([(r["connections"],r["rss_kib"]) for r in rows])
        if slope<=0:raise RuntimeError("non-positive fitted RSS/session: cannot set safe cap")
        cap=max(0,math.floor((budget-intercept)/slope))
        # Conservative: also bound using worst observed incremental cost per session.
        observed=[(r["rss_kib"]-rows[0]["rss_kib"])/r["connections"] for r in rows[1:]]
        worst=max(observed)
        conservative=max(0,math.floor((budget-rows[0]["rss_kib"])/worst))
        report={"ram_kib":ram,"budget_80pct_kib":budget,"server_pid":a.pid,
                "measurements":rows,"linear_fit":{"intercept_kib":intercept,"slope_kib_per_session":slope,"r_squared":r2},
                "observed_max_increment_kib_per_session":worst,
                "linear_cap_extrapolated":cap,"conservative_cap_extrapolated":conservative,
                "measured_safe_max_sessions":max((r["connections"] for r in rows if r["rss_kib"]<=budget),default=0),
                "warning":"Extrapolated cap is not measured capacity; reserve RAM for proxy, OS and other processes; RSS includes model warmup and allocator effects."}
        (output.parent/"rss-capacity.json").write_text(json.dumps(report,indent=2)+"\n")
        print(json.dumps({k:v for k,v in report.items() if k!="measurements"},indent=2),flush=True)
    finally:
        await asyncio.gather(*(ws.close() for ws in held),return_exceptions=True)
if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--url",default="ws://127.0.0.1:8080/speech/tts")
    p.add_argument("--pid",type=int,required=True)
    p.add_argument("--settle",type=float,default=1.5)
    p.add_argument("--output",default="out/rss-calibration/rows.json")
    asyncio.run(main(p.parse_args()))
