#!/usr/bin/env python3
"""Phonon WS connection-admission control (arm B). No KAIROS engine modifications.
Requires: python -m pip install websockets
Uses /speech/tts protocol from pinned Gradium commit.
Records client-side timestamps and HTTP 429; does not conflate handshake with generation.
"""
import argparse,asyncio,base64,csv,hashlib,json,time
from pathlib import Path
from urllib.parse import urlparse

def event_gap_ratios(events):
    ratios=[]
    for prev,cur in zip(events,events[1:]):
        duration=1000*(prev["stop_s"]-prev["start_s"])
        if duration>0:
            ratios.append((cur["arrival_ns"]-prev["arrival_ns"])/1e6/duration)
    return ratios

async def one(url,idx,text,hold_idle,barrier,timeout):
    import websockets
    t0=time.perf_counter_ns()
    result={"flow":idx,"connect_start_ns":t0,"http_status":None,"error":None,
            "connected_ns":None,"ready_ns":None,"request_ns":None,
            "first_audio_ns":None,"flushed_ns":None,"audio":[]}
    try:
        async with websockets.connect(url,open_timeout=timeout,max_size=16*1024*1024) as ws:
            result["connected_ns"]=time.perf_counter_ns()
            await ws.send(json.dumps({"type":"setup","json_config":"","model_name":"",
                    "output_format":"pcm","voice":None,"voice_id":None,"voice_emb":None}))
            while True:
                reply=json.loads(await asyncio.wait_for(ws.recv(),timeout))
                if reply.get("type")=="ready":
                    result["ready_ns"]=time.perf_counter_ns()
                    result["sample_rate"]=reply["sample_rate"]
                    result["frame_size"]=reply["frame_size"]
                    break
                if reply.get("type")=="error":
                    raise RuntimeError(f"setup error: {reply}")
            if hold_idle:
                await asyncio.sleep(hold_idle)
            await barrier.wait()
            result["request_ns"]=time.perf_counter_ns()
            await ws.send(json.dumps({"type":"text","text":text}))
            await ws.send(json.dumps({"type":"flush","flush_id":idx+1}))
            while True:
                reply=json.loads(await asyncio.wait_for(ws.recv(),timeout))
                now=time.perf_counter_ns()
                typ=reply.get("type")
                if typ=="audio":
                    audio=base64.b64decode(reply["audio"],validate=True)
                    if reply["stop_s"]>reply["start_s"]:
                        if result["first_audio_ns"] is None:
                            result["first_audio_ns"]=now
                        result["audio"].append({"arrival_ns":now,
                            "start_s":reply["start_s"],"stop_s":reply["stop_s"],
                            "bytes":len(audio),"sha256":hashlib.sha256(audio).hexdigest()})
                elif typ=="flushed" and reply.get("flush_id")==idx+1:
                    result["flushed_ns"]=now
                    break
                elif typ=="error":
                    raise RuntimeError(f"generation error: {reply}")
            result["gap_ratios"]=event_gap_ratios(result["audio"])
            result["ttfa_request_ms"]=(result["first_audio_ns"]-result["request_ns"])/1e6 if result["first_audio_ns"] else None
            result["ttfa_connected_ms"]=(result["first_audio_ns"]-result["connected_ns"])/1e6 if result["first_audio_ns"] else None
            result["ttfa_ready_ms"]=(result["first_audio_ns"]-result["ready_ns"])/1e6 if result["first_audio_ns"] else None
    except Exception as exc:
        result["error"]=str(exc)
        result["http_status"]=getattr(exc,"status_code",None)
        if result["http_status"] is None:
            response=getattr(exc,"response",None)
            result["http_status"]=getattr(response,"status_code",None)
        # Never conceal a rejection as an audio success.
    return result

async def run(args):
    import websockets
    class Gate:
        def __init__(self,count):
            self.n=count
            self.event=asyncio.Event()
            self.arrived=0
        async def wait(self):
            self.arrived+=1
            if self.arrived>=self.n:self.event.set()
            await self.event.wait()
    # Barrier covers only admitted connections; avoid deadlock when HTTP 429 rejects.
    # First phase deliberately measures connection admission, then releases successful sessions.
    async def client(idx):
        t0=time.perf_counter_ns()
        result={"flow":idx,"connect_start_ns":t0,"error":None,"http_status":None,
                "connected_ns":None,"ready_ns":None,"request_ns":None,
                "first_audio_ns":None,"flushed_ns":None,"audio":[]}
        try:
            async with websockets.connect(args.url,open_timeout=args.timeout,max_size=16*1024*1024) as ws:
                result["connected_ns"]=time.perf_counter_ns()
                await ws.send(json.dumps({"type":"setup","json_config":"","model_name":"",
                    "output_format":"pcm","voice":None,"voice_id":None,"voice_emb":None}))
                while True:
                    r=json.loads(await asyncio.wait_for(ws.recv(),args.timeout))
                    if r["type"]=="ready":
                        result["ready_ns"]=time.perf_counter_ns()
                        result["sample_rate"]=r["sample_rate"]
                        result["frame_size"]=r["frame_size"]
                        break
                    if r["type"]=="error":raise RuntimeError(str(r))
                # Each admitted connection remains open during the idle window.
                await asyncio.sleep(args.idle_seconds)
                result["request_ns"]=time.perf_counter_ns()
                await ws.send(json.dumps({"type":"text","text":args.text}))
                await ws.send(json.dumps({"type":"flush","flush_id":idx+1}))
                while True:
                    r=json.loads(await asyncio.wait_for(ws.recv(),args.timeout))
                    now=time.perf_counter_ns()
                    if r["type"]=="audio":
                        raw=base64.b64decode(r["audio"],validate=True)
                        if r["stop_s"]>r["start_s"]:
                            if result["first_audio_ns"] is None:result["first_audio_ns"]=now
                            result["audio"].append({"arrival_ns":now,"start_s":r["start_s"],
                                "stop_s":r["stop_s"],"bytes":len(raw),
                                "sha256":hashlib.sha256(raw).hexdigest()})
                    elif r["type"]=="flushed" and r["flush_id"]==idx+1:
                        result["flushed_ns"]=now
                        break
                    elif r["type"]=="error":raise RuntimeError(str(r))
                result["gap_ratios"]=event_gap_ratios(result["audio"])
                if result["first_audio_ns"] is not None:
                    result["ttfa_request_ms"]=(result["first_audio_ns"]-result["request_ns"])/1e6
                    result["ttfa_connected_ms"]=(result["first_audio_ns"]-result["connected_ns"])/1e6
                    result["ttfa_ready_ms"]=(result["first_audio_ns"]-result["ready_ns"])/1e6
        except Exception as e:
            result["error"]=str(e)
            result["http_status"]=getattr(e,"status_code",None) or getattr(getattr(e,"response",None),"status_code",None)
        return result
    return await asyncio.gather(*(client(i) for i in range(args.clients)))

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--url",default="ws://127.0.0.1:8080/speech/tts")
    p.add_argument("--clients",type=int,default=8)
    p.add_argument("--idle-seconds",type=float,default=2.0)
    p.add_argument("--timeout",type=float,default=90.0)
    p.add_argument("--text",default="The quick brown fox jumps over the lazy dog.")
    p.add_argument("--output",default="out/ws-b.json")
    args=p.parse_args()
    assert args.clients>0 and args.idle_seconds>=0
    results=asyncio.run(run(args))
    dest=Path(args.output);dest.parent.mkdir(parents=True,exist_ok=True)
    dest.write_text(json.dumps({"schema":"kairos_ws_b_v1","url":args.url,
        "clients":args.clients,"idle_seconds":args.idle_seconds,
        "results":results},indent=2)+"\n")
    print(json.dumps({"clients":len(results),
        "connected":sum(x["connected_ns"] is not None for x in results),
        "http_429":sum(x["http_status"]==429 for x in results),
        "audio_flows":sum(bool(x["audio"]) for x in results),
        "errors":[{"flow":x["flow"],"error":x["error"]} for x in results if x["error"]]},indent=2))
    if any(x["error"] and x["http_status"]!=429 for x in results):
        raise SystemExit(2)

if __name__=="__main__":main()
