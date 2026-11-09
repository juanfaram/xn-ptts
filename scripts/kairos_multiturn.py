#!/usr/bin/env python3
"""KAIROS 4-turn session benchmark. All four turns must pass.
20s idle between turns; 5 measured repeats plus excluded warmup.
M0 immediate virtual playback, PCM compared to stream-id-matched direct reference.
"""
import argparse,asyncio,base64,hashlib,json,math,random,time
from array import array
from contextlib import AsyncExitStack
from pathlib import Path
from websockets.asyncio.client import connect
from kairos_playback_v2 import simulate

TEXT="Hello."
SETUP={"type":"setup","json_config":"","model_name":"","output_format":"pcm","voice":None,"voice_id":None,"voice_emb":None}
def lsb(a,b):
    if len(a)!=len(b):return None
    x=array("h");y=array("h");x.frombytes(a);y.frombytes(b)
    return max((abs(u-v) for u,v in zip(x,y)),default=0)
async def setup(url):
    ws=await connect(url,open_timeout=10,max_size=2**23)
    await ws.send(json.dumps(SETUP))
    while True:
        m=json.loads(await ws.recv())
        if m["type"]=="error":raise RuntimeError(str(m))
        if m["type"]=="ready":return ws
async def generate(ws,turn,deadline_ms,reference=None,trace_id=None):
    await ws.send(json.dumps({"type":"text","text":TEXT}))
    t0=time.perf_counter()
    t_request_ns=time.monotonic_ns()
    request={"type":"flush","flush_id":turn+1,"deadline_ms":deadline_ms}
    if trace_id is not None:request["kairos_trace_id"]=trace_id
    await ws.send(json.dumps(request))
    raw=bytearray();frags=[];first=None
    while True:
        m=json.loads(await ws.recv())
        if m["type"]=="error":
            return {"status":"rejected","code":m.get("code"),"reason":m.get("message"),"valid":False}
        if m["type"]=="audio":
            now=time.perf_counter()
            if first is None:first=now
            raw.extend(base64.b64decode(m["audio"],validate=True))
            frags.append({"idx":len(frags),"ts_recv_monotonic_s":now,"frag_ms":(float(m["stop_s"])-float(m["start_s"]))*1000})
        if m["type"]=="flushed" and m.get("flush_id")==turn+1:break
    if not frags:return {"status":"empty","valid":False}
    ttfa=(first-t0)*1000
    episodes=simulate(frags)["episode_count"]
    difference=lsb(reference,bytes(raw)) if reference is not None else None
    return {"status":"completed","trace_id":trace_id,"t_request_ns":t_request_ns,"t_first_audio_ns":int(first*1e9),"ttfa_ms":round(ttfa,3),"m0_episodes":episodes,
            "max_abs_lsb":difference,"pcm_sha256":hashlib.sha256(raw).hexdigest(),
            "valid":ttfa<=deadline_ms and episodes==0 and difference is not None and difference<=1,
            "_pcm":bytes(raw)}
async def refs(url):
    ws=await setup(url)
    try:
        outputs=[]
        for turn in range(4):
            x=await generate(ws,turn,10000)
            if x["status"]!="completed":raise RuntimeError("reference failed")
            outputs.append(x.pop("_pcm"))
        return outputs
    finally:await ws.close()
async def wave(a,ref,activity,rep):
    n=round(a.sessions*activity)
    ids=list(range(a.sessions));random.Random(20261109+int(activity*1000)*100+rep).shuffle(ids)
    offered=ids[:n];deadlines={i:(a.short_ms if j%10<3 else a.long_ms) for j,i in enumerate(offered)}
    async with AsyncExitStack() as stack:
        clients={}
        for i in range(a.sessions):
            try:
                ws=await setup(a.url)
                clients[i]=ws
                stack.push_async_callback(ws.close)
            except Exception:
                if not a.allow_admission_rejects:raise
                clients[i]=None
        outcomes={i:[] for i in offered}
        start=time.perf_counter()
        for turn in range(4):
            async def one(i):
                if clients[i] is None:return {"status":"rejected","code":429,"valid":False}
                try:
                    return await asyncio.wait_for(generate(clients[i],turn,deadlines[i],ref[turn],f"{a.arm}:{activity}:{rep}:{i}:{turn}" if a.trace else None),timeout=25)
                except Exception as exc:return {"status":"error","error":repr(exc),"valid":False}
            batch=await asyncio.gather(*(one(i) for i in offered))
            for i,x in zip(offered,batch):
                x.pop("_pcm",None)
                outcomes[i].append(x)
            if turn<3:await asyncio.sleep(a.idle)
        elapsed=time.perf_counter()-start
    useful=sum(all(x["valid"] for x in outcomes[i]) for i in offered)
    return {"activity":activity,"repeat":rep,"warmup":rep==0 and a.repeats>1,"offered_sessions":n,
            "useful_sessions":useful,"invalid_sessions":n-useful,
            "rejected_turns":sum(x["status"]=="rejected" for v in outcomes.values() for x in v),
            "elapsed_s":elapsed,"turns":outcomes}
async def main(a):
    out=Path(a.output);out.mkdir(parents=True,exist_ok=True)
    ref=await refs(a.reference_url)
    (out/"reference-sha256.json").write_text(json.dumps([hashlib.sha256(v).hexdigest() for v in ref],indent=2)+"\n")
    rows=[]
    for activity in a.activities:
        for rep in range(a.repeats):
            row=await wave(a,ref,activity,rep)
            rows.append(row)
            (out/"runs.json").write_text(json.dumps(rows,indent=2)+"\n")
            print(json.dumps({k:v for k,v in row.items() if k!="turns"}),flush=True)
    measured=[r for r in rows if not r["warmup"]]
    (out/"summary.json").write_text(json.dumps({"arm":a.arm,"sessions":a.sessions,"turns_per_session":4,
        "idle_seconds_between_turns":a.idle,"warmup_excluded":True,
        "by_activity":[{"activity":act,"offered":sum(r["offered_sessions"] for r in measured if r["activity"]==act),
          "useful":sum(r["useful_sessions"] for r in measured if r["activity"]==act),
          "rejected_turns":sum(r["rejected_turns"] for r in measured if r["activity"]==act)}
          for act in a.activities],
        "warning":"Four-turn pilot, virtual M0, no device playback; no economic SES/eur without verified tariff and sustained throughput."},indent=2)+"\n")
if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--url",required=True)
    p.add_argument("--reference-url",default="ws://127.0.0.1:8080/speech/tts")
    p.add_argument("--output",required=True)
    p.add_argument("--arm",required=True)
    p.add_argument("--sessions",type=int,default=20)
    p.add_argument("--idle",type=float,default=20)
    p.add_argument("--trace",action="store_true")
    p.add_argument("--activities",type=float,nargs="+",default=[.10,.25,.50])
    p.add_argument("--repeats",type=int,default=6)
    p.add_argument("--short-ms",type=int,default=240)
    p.add_argument("--long-ms",type=int,default=1000)
    p.add_argument("--allow-admission-rejects",action="store_true")
    asyncio.run(main(p.parse_args()))
