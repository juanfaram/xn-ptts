#!/usr/bin/env python3
"""Paired provisional FIFO/EDF commercial smoke with real Phonon.
Not a production SLA claim; all offered requests included in denominators.
"""
import argparse,asyncio,base64,hashlib,json,math,random,statistics,time
from array import array
from pathlib import Path
from websockets.asyncio.client import connect
from kairos_playback_v2 import simulate

TEXT="Hello."
def pct(xs,p):
    return sorted(xs)[min(len(xs)-1,max(0,math.ceil(len(xs)*p)-1))] if xs else None
def lsb(a,b):
    if len(a)!=len(b):return None
    x=array("h");y=array("h");x.frombytes(a);y.frombytes(b)
    return max((abs(v-w) for v,w in zip(x,y)),default=0)
def m1(frags):
    if len(frags)<2:return {"episode_count":0,"total_stall_ms":0}
    times=[f["ts_recv_monotonic_s"]*1000 for f in frags]
    durations=[f["frag_ms"] for f in frags]
    buffer=durations[0]+durations[1];episodes=[]
    for i in range(2,len(frags)):
        gap=times[i]-times[i-1]
        if gap>buffer:episodes.append({"idx":i,"duration_ms":gap-buffer})
        buffer=max(0,buffer-gap)+durations[i]
    return {"episode_count":len(episodes),"total_stall_ms":sum(e["duration_ms"] for e in episodes),"episodes":episodes}
async def one(ws,session_id,deadline_ms,reference,timeout):
    start=time.perf_counter()
    try:
        async with asyncio.timeout(timeout):
            if True:
                await ws.send(json.dumps({"type":"text","text":TEXT}))
                t0=time.perf_counter()
                await ws.send(json.dumps({"type":"flush","flush_id":session_id+1,"deadline_ms":deadline_ms}))
                raw=bytearray();frags=[];first=None
                while True:
                    msg=json.loads(await ws.recv())
                    if msg["type"]=="error":
                        return {"session":session_id,"deadline_ms":deadline_ms,"status":"rejected","code":msg.get("code"),"error":msg.get("message"),"retry_after_seconds":msg.get("retry_after_seconds"),"elapsed_ms":(time.perf_counter()-t0)*1000,"valid":False}
                    if msg["type"]=="audio":
                        now=time.perf_counter()
                        if first is None:first=now
                        pcm=base64.b64decode(msg["audio"],validate=True)
                        raw.extend(pcm)
                        frags.append({"idx":len(frags),"ts_recv_monotonic_s":now,"frag_ms":(float(msg["stop_s"])-float(msg["start_s"]))*1000})
                    if msg["type"]=="flushed" and msg.get("flush_id")==session_id+1:break
                elapsed=(time.perf_counter()-t0)*1000
                if not frags:raise RuntimeError("empty audio")
                m0=simulate(frags);m1r=m1(frags)
                difference=lsb(reference,bytes(raw))
                return {"session":session_id,"deadline_ms":deadline_ms,"status":"completed","elapsed_ms":elapsed,"ttfa_ms":(first-t0)*1000,"chunks":len(frags),"pcm_sha256":hashlib.sha256(raw).hexdigest(),"max_abs_lsb":difference,"M0_episodes":m0["episode_count"],"M1_episodes":m1r["episode_count"],"M1_stall_ms":m1r["total_stall_ms"],"valid":(first-t0)*1000<=deadline_ms and difference is not None and difference<=1 and m0["episode_count"]==0}
    except Exception as exc:
        return {"session":session_id,"deadline_ms":deadline_ms,"status":"error","error":repr(exc),"elapsed_ms":(time.perf_counter()-start)*1000,"valid":False}
async def reference(url):
    # Deterministic reference using same Phonon, single request.
    async with connect(url,max_size=2**23) as ws:
        await ws.send(json.dumps({"type":"setup","json_config":"","model_name":"","output_format":"pcm","voice":None,"voice_id":None,"voice_emb":None}))
        while json.loads(await ws.recv())["type"]!="ready":pass
        await ws.send(json.dumps({"type":"text","text":TEXT}))
        await ws.send(json.dumps({"type":"flush","flush_id":1}))
        pcm=bytearray()
        while True:
            m=json.loads(await ws.recv())
            if m["type"]=="audio":pcm.extend(base64.b64decode(m["audio"]))
            if m["type"]=="flushed":break
        return bytes(pcm)
async def main(a):
    out=Path(a.output);out.mkdir(parents=True,exist_ok=True)
    ref=await reference(a.url)
    ref2=await reference(a.url)
    direct_lsb=lsb(ref,ref2)
    (out/"direct-determinism.json").write_text(json.dumps({"direct_pair_max_abs_lsb":direct_lsb,"reference_bytes":len(ref),"reference2_bytes":len(ref2),"sha1":hashlib.sha256(ref).hexdigest(),"sha2":hashlib.sha256(ref2).hexdigest()},indent=2)+"\n")
    (out/"reference.sha256").write_text(hashlib.sha256(ref).hexdigest()+"\n")
    rows=[]
    from contextlib import AsyncExitStack
    async with AsyncExitStack() as stack:
      clients=[]
      for i in range(a.sessions):
        ws=await stack.enter_async_context(connect(a.url,open_timeout=10,max_size=2**23))
        await ws.send(json.dumps({"type":"setup","json_config":"","model_name":"","output_format":"pcm","voice":None,"voice_id":None,"voice_emb":None}))
        while True:
          msg=json.loads(await ws.recv())
          if msg["type"]=="error":raise RuntimeError("setup failed "+str(msg))
          if msg["type"]=="ready":break
        clients.append(ws)
      for activity in (.10,.25,.50):
        # Persistent idle sessions; activity selects generators within the same connected population.
        # 20 sessions, one generation each; activity 10/25/50 -> 2/5/10 active per wave.
        concurrency=round(a.sessions*activity)
        for rep in range(0,6):
            rng=random.Random(20261109+int(activity*1000)*100+rep)
            ids=list(range(a.sessions));rng.shuffle(ids)
            offered=ids[:concurrency]
            deadlines={i:(150 if j%10<3 else 1000) for j,i in enumerate(offered)}
            t=time.perf_counter()
            tasks=[one(clients[i],i,deadlines[i],ref,a.timeout) for i in offered]
            results=await asyncio.gather(*tasks)
            row={"activity":activity,"repeat":rep,"warmup":rep==0,"offered":len(offered),"valid":sum(r["valid"] for r in results),"rejected":sum(r["status"]=="rejected" for r in results),"failed":sum(not r["valid"] for r in results),"elapsed_s":time.perf_counter()-t,"ttfa_p99_ms":pct([r["ttfa_ms"] for r in results if "ttfa_ms" in r],.99),"requests":results}
            rows.append(row)
            (out/"runs.json").write_text(json.dumps(rows,indent=2)+"\n")
            print(json.dumps({k:v for k,v in row.items() if k!="requests"}),flush=True)
    measured=[r for r in rows if not r["warmup"]]
    summary={"direct_pair_max_abs_lsb":direct_lsb,"model":"provisional real Phonon FIFO/EDF; M0 virtual; one generation per offered session","rows":[{k:v for k,v in r.items() if k!="requests"} for r in measured],"offered":sum(r["offered"] for r in measured),"valid":sum(r["valid"] for r in measured),"rejected":sum(r["rejected"] for r in measured),"elapsed_s":sum(r["elapsed_s"] for r in measured),"warning":"No cost assigned, no multi-generation sessions, no sustained load; do not claim commercial SES/eur"}
    (out/"summary.json").write_text(json.dumps(summary,indent=2)+"\n")
if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--url",default="ws://127.0.0.1:8081/speech/tts")
    p.add_argument("--sessions",type=int,default=20)
    p.add_argument("--timeout",type=float,default=30)
    p.add_argument("--output",required=True)
    asyncio.run(main(p.parse_args()))
