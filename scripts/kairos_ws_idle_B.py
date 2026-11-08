#!/usr/bin/env python3
"""Three-phase, local-only WS B test: eight idle holders, eight late probes,
then exactly the same eight holders generate. Admission and generation are
separate phases; no C advantage is claimed."""
import argparse, asyncio, csv, json, math, time
from pathlib import Path
from websockets.asyncio.client import connect
from websockets.exceptions import InvalidStatus

def cpu_snapshot():
    with open("/proc/stat") as f:
        fields=list(map(int,f.readline().split()[1:]))
    return sum(fields), fields[3]+(fields[4] if len(fields)>4 else 0)

async def sample_cpu(stop,output):
    rows=[];prev=cpu_snapshot()
    while not stop.is_set():
        await asyncio.sleep(.25)
        now=cpu_snapshot();dt=now[0]-prev[0];di=now[1]-prev[1]
        rows.append({"time_s":time.monotonic(),"cpu_busy_pct":round(100*(1-di/dt),3) if dt else ""})
        prev=now
    with open(output,"w",newline="") as f:
        w=csv.DictWriter(f,fieldnames=["time_s","cpu_busy_pct"]);w.writeheader();w.writerows(rows)
    return rows

async def probe(url,i,timeout):
    """Use a raw *valid* WS upgrade to preserve HTTP status/body even if the
    WebSocket library classifies non-101 replies as handshake errors."""
    from urllib.parse import urlsplit
    import base64,os
    u=urlsplit(url)
    start=time.perf_counter()
    writer=None
    try:
        async with asyncio.timeout(timeout):
            reader,writer=await asyncio.open_connection(u.hostname,u.port or 80)
            key=base64.b64encode(os.urandom(16)).decode()
            path=u.path or "/"
            if u.query:path+="?"+u.query
            req=(f"GET {path} HTTP/1.1\\r\\n"
                 f"Host: {u.hostname}:{u.port or 80}\\r\\n"
                 "Upgrade: websocket\\r\\nConnection: Upgrade\\r\\n"
                 f"Sec-WebSocket-Key: {key}\\r\\nSec-WebSocket-Version: 13\\r\\n\\r\\n")
            writer.write(req.encode("ascii"));await writer.drain()
            head=await reader.readuntil(b"\\r\\n\\r\\n")
            lines=head.decode("iso-8859-1").split("\\r\\n")
            status=int(lines[0].split()[1])
            headers={}
            for line in lines[1:]:
                if ":" in line:
                    k,v=line.split(":",1);headers[k.strip().lower()]=v.strip()
            body=b""
            if status!=101:
                n=int(headers.get("content-length","0"))
                if n:body=await reader.readexactly(min(n,4096))
            return {"client":i,"status":"rejected" if status!=101 else "admitted",
                    "http_status":status,"elapsed_ms":round((time.perf_counter()-start)*1000,3),
                    "body":body.decode("utf-8","replace"),"headers":headers}
    except Exception as exc:
        return {"client":i,"status":"error","http_status":None,
                "elapsed_ms":round((time.perf_counter()-start)*1000,3),"error":repr(exc)}
    finally:
        if writer is not None:
            writer.close()
            try:await writer.wait_closed()
            except Exception:pass

async def speak(ws,i,text,timeout):
    started=time.perf_counter()
    await ws.send(json.dumps({"type":"setup","json_config":"","model_name":"","output_format":"pcm","voice":None,"voice_id":None,"voice_emb":None}))
    sample_rate=None
    async with asyncio.timeout(timeout):
        while True:
            msg=json.loads(await ws.recv())
            if msg.get("type")=="error":raise RuntimeError(f"setup {i}: {msg}")
            if msg.get("type")=="ready":
                sample_rate=msg.get("sample_rate");break
        await ws.send(json.dumps({"type":"text","text":text}))
        request_at=time.perf_counter()
        await ws.send(json.dumps({"type":"flush","flush_id":i+1}))
        chunks=[]
        while True:
            msg=json.loads(await ws.recv())
            if msg.get("type")=="error":raise RuntimeError(f"generate {i}: {msg}")
            if msg.get("type")=="audio":
                duration=float(msg.get("stop_s",0))-float(msg.get("start_s",0))
                if duration>0:chunks.append((time.perf_counter(),duration))
            if msg.get("type")=="flushed" and msg.get("flush_id")==i+1:break
    if not chunks:raise RuntimeError(f"empty audio {i}")
    ratios=[(chunks[j][0]-chunks[j-1][0])/chunks[j-1][1] for j in range(1,len(chunks))]
    return {"client":i,"status":"ok","sample_rate":sample_rate,"ttfa_request_ms":round(1000*(chunks[0][0]-request_at),3),
            "audio_chunks":len(chunks),"audio_seconds":round(sum(d for _,d in chunks),3),
            "delivery_gap_count":sum(r>1 for r in ratios),
            "median_gap_ratio":round(sorted(ratios)[len(ratios)//2],4) if ratios else None,
            "max_gap_ratio":round(max(ratios),4) if ratios else None,
            "elapsed_ms":round(1000*(time.perf_counter()-started),3)}

async def main(args):
    if not args.url.startswith(("ws://127.0.0.1:","ws://localhost:")):
        raise SystemExit("This probe is intentionally restricted to local loopback")
    out=Path(args.output);out.parent.mkdir(parents=True,exist_ok=True)
    holders=[]
    try:
        for i in range(8):
            ws=await connect(args.url,open_timeout=10)
            holders.append(ws)
        print("B: eight idle WS permits acquired",flush=True)
        await asyncio.sleep(args.idle_seconds)
        late=await asyncio.gather(*(probe(args.url,i+8,args.timeout) for i in range(8)))
        (out.parent/"ws-B-idle-probes.json").write_text(json.dumps(late,indent=2)+"\n")
        print("B: late admission evidence",json.dumps(late,indent=2),flush=True)
        if any(p["http_status"]!=429 for p in late):
            raise RuntimeError("Expected eight HTTP 429 while eight idle connections hold permits")
        stop=asyncio.Event();cpu_task=asyncio.create_task(sample_cpu(stop,out.parent/"ws-B-cpu.csv"))
        try:
            results=await asyncio.gather(*(speak(ws,i,args.text,args.timeout) for i,ws in enumerate(holders)),return_exceptions=True)
        finally:
            stop.set();samples=await cpu_task
        normalized=[dict(client=i,status="error",error=repr(r)) if isinstance(r,BaseException) else r for i,r in enumerate(results)]
        (out.parent/"ws-B-generation.json").write_text(json.dumps(normalized,indent=2)+"\n")
        cpu_values=[float(x["cpu_busy_pct"]) for x in samples if x["cpu_busy_pct"]!=""]
        summary={"arm":"B original connection permit","limit":8,"idle_s":args.idle_seconds,
                 "holders":8,"late_probes":8,"late_429":sum(p["http_status"]==429 for p in late),
                 "generators":8,"generators_ok":sum(r["status"]=="ok" for r in normalized),
                 "cpu_busy_mean_pct":round(sum(cpu_values)/len(cpu_values),2) if cpu_values else None,
                 "warning":"CPU from /proc/stat is runner-wide and not process-isolated; compare C only with matched load and environment"}
        out.write_text(json.dumps(summary,indent=2)+"\n")
        print(json.dumps(summary,indent=2),flush=True)
        if summary["generators_ok"]!=8:raise RuntimeError("one or more generators failed")
    finally:
        await asyncio.gather(*(ws.close() for ws in holders),return_exceptions=True)

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--url",default="ws://127.0.0.1:8080/speech/tts")
    p.add_argument("--idle-seconds",type=float,default=30)
    p.add_argument("--timeout",type=float,default=120)
    p.add_argument("--text",default="Hello, this is a test of the Phonon TTS system.")
    p.add_argument("--output",default="out/ws-B-summary.json")
    args=p.parse_args()
    asyncio.run(main(args))
