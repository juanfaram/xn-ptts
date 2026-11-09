#!/usr/bin/env python3
"""Execute frozen paired load against real Phonon WS. All failures count."""
import argparse, asyncio, base64, hashlib, json, time
from pathlib import Path
import websockets
from kairos_paired_load import schedule, SESSIONS, TURNS, SESSION_TIMEOUT_S

SETUP={"type":"setup","json_config":"","model_name":"","output_format":"pcm","voice":None,"voice_id":None,"voice_emb":None}
TEXT="Hello, this is a test of the Phonon TTS system."

async def warmup(args):
    async with websockets.connect(args.url,open_timeout=10,max_size=2**22) as ws:
        await ws.send(json.dumps(SETUP))
        while True:
            r=json.loads(await asyncio.wait_for(ws.recv(),15))
            if r.get("type")=="ready":break
            if r.get("type")=="error":raise RuntimeError("warmup setup "+str(r))
        await ws.send(json.dumps({"type":"text","text":TEXT}))
        await ws.send(json.dumps({"type":"flush","flush_id":1}))
        chunks=0
        while True:
            r=json.loads(await asyncio.wait_for(ws.recv(),args.timeout))
            if r.get("type")=="audio":chunks+=1
            if r.get("type")=="flushed" and r.get("flush_id")==1:break
            if r.get("type")=="error":raise RuntimeError("warmup generation "+str(r))
        if chunks!=42:raise RuntimeError(f"warmup incomplete: {chunks} chunks; expected 42")
        print(json.dumps({"warmup_discarded":True,"chunks":chunks}),flush=True)

async def client(i,args,events,t0):
    out={"session":i,"connected":False,"turns":[]}
    ws=None
    try:
        ws=await asyncio.wait_for(websockets.connect(args.url,open_timeout=10,max_size=2**22),timeout=15)
        out["connected"]=True
        await ws.send(json.dumps(SETUP))
        while True:
            r=json.loads(await asyncio.wait_for(ws.recv(),15))
            if r.get("type")=="ready":break
            if r.get("type")=="error":raise RuntimeError(str(r))
        for ev in events:
            scheduled=t0+ev["offer_ms"]/1000
            await asyncio.sleep(max(0,scheduled-time.perf_counter()))
            start=time.perf_counter_ns()
            result={"turn":ev["turn"],"deadline_ms":ev["deadline_ms"],"request_ns":start,
                    "first_audio_ns":None,"chunks":[],"status":"error"}
            out["turns"].append(result)
            try:
                await ws.send(json.dumps({"type":"text","text":TEXT}))
                await ws.send(json.dumps({"type":"flush","flush_id":ev["turn"]+1,"deadline_ms":ev["deadline_ms"]}))
                while True:
                    r=json.loads(await asyncio.wait_for(ws.recv(),args.timeout))
                    stamp=time.perf_counter_ns()
                    if r.get("type")=="audio" and r.get("stop_s",0)>r.get("start_s",0):
                        raw=base64.b64decode(r["audio"],validate=True)
                        if result["first_audio_ns"] is None:result["first_audio_ns"]=stamp
                        result["chunks"].append({"arrival_ns":stamp,"frag_ms":1000*(r["stop_s"]-r["start_s"]),
                            "bytes":len(raw),"sha256":hashlib.sha256(raw).hexdigest()})
                    elif r.get("type")=="flushed" and r.get("flush_id")==ev["turn"]+1:
                        result["status"]="ok";break
                    elif r.get("type")=="error":
                        result["error"]=str(r);break
                if result["first_audio_ns"] is not None:
                    result["ttfa_request_ms"]=(result["first_audio_ns"]-start)/1e6
                    result["deadline_met"]=result["ttfa_request_ms"]<=ev["deadline_ms"]
                else:result["deadline_met"]=False
                result["fragments_complete"]=len(result["chunks"])==42
                if result["status"]!="ok":break
            except Exception as exc:
                result["error"]=repr(exc)
                break
    except Exception as exc:
        out["connection_error"]=repr(exc)
    finally:
        if ws is not None:
            try:await ws.close()
            except Exception:pass
    for ev in events[len(out["turns"]):]:
        out["turns"].append({"turn":ev["turn"],"deadline_ms":ev["deadline_ms"],
                             "status":"not_served","deadline_met":False,"chunks":[]})
    return out

async def run(args):
    events=schedule(args.activity,args.repeat)
    grouped={i:[] for i in range(SESSIONS)}
    for ev in events:grouped[ev["session"]].append(ev)
    started=time.perf_counter()
    async def bounded(i):
        try:
            return await asyncio.wait_for(client(i,args,grouped[i],started),timeout=SESSION_TIMEOUT_S)
        except Exception as exc:
            return {"session":i,"connected":False,"connection_error":"session_timeout: "+repr(exc),
                    "turns":[{"turn":ev["turn"],"deadline_ms":ev["deadline_ms"],
                              "status":"session_timeout","deadline_met":False,"chunks":[]}
                             for ev in grouped[i]]}
    results=await asyncio.gather(*(bounded(i) for i in range(SESSIONS)))
    duration=time.perf_counter()-started
    turns=[t for s in results for t in s["turns"]]
    assert len(turns)==SESSIONS*TURNS
    def valid_turn(t):
        return t.get("status")=="ok" and t.get("deadline_met") and t.get("fragments_complete")
    valid=sum(valid_turn(t) for t in turns)
    rejection_counts={"deadline_expired":0,"queue_full":0,"connection_limit":0,"other":0}
    for session in results:
        error=str(session.get("connection_error",""))
        if error and ("429" in error or "rejected" in error.lower()):
            rejection_counts["connection_limit"]+=1
        for turn in session["turns"]:
            message=str(turn.get("error",""))
            if "deadline_expired" in message:rejection_counts["deadline_expired"]+=1
            elif "queue_full" in message:rejection_counts["queue_full"]+=1
            elif "429" in message:rejection_counts["other"]+=1
    valid_sessions=sum(len(x["turns"])==TURNS and all(valid_turn(t) for t in x["turns"]) for x in results)
    return {"arm":args.arm,"activity_pct":args.activity,"repeat":args.repeat,"duration_s":duration,
            "offered":len(turns),"valid_preliminary":valid,"failed":len(turns)-valid,
            "offered_sessions":SESSIONS,"valid_sessions_preliminary":valid_sessions,\n            "rejection_counts":rejection_counts,
            "note":"Preliminary only: full C1-C4 SES certification requires frozen offline analyzer",
            "sessions":results}

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--url",default="ws://127.0.0.1:8080/speech/tts")
    p.add_argument("--arm",required=True)
    p.add_argument("--activity",type=int,choices=(10,25,40),required=True)
    p.add_argument("--repeat",type=int,choices=range(1,6),required=True)
    p.add_argument("--timeout",type=float,default=180)
    p.add_argument("--output")
    p.add_argument("--warmup",action="store_true")
    args=p.parse_args()
    if args.warmup:
        asyncio.run(warmup(args))
        return
    if not args.output:p.error("--output required for measured runs")
    out=asyncio.run(run(args))
    dest=Path(args.output);dest.parent.mkdir(parents=True,exist_ok=True)
    dest.write_text(json.dumps(out,indent=2)+"\n")
    print(json.dumps({k:out[k] for k in ("arm","activity_pct","repeat","duration_s","offered","valid_preliminary","failed","offered_sessions","valid_sessions_preliminary")}))
if __name__=="__main__":main()
