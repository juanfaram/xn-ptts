#!/usr/bin/env python3
"""KAIROS arm B: pinned Phonon WebSocket admission/load probe. Local-only by default."""
import argparse, asyncio, csv, json, math, time
from pathlib import Path
from websockets.asyncio.client import connect
from websockets.exceptions import InvalidStatus

FIELDS=["arm","limit","session","status","http_status","upgrade_ms","setup_ms","ttfa_request_ms","ttfa_admitted_ms","audio_chunks","audio_seconds","delivery_gaps","worst_gap_ratio","error"]
async def session(args,i,barrier):
    row={k:"" for k in FIELDS}
    row.update(arm=args.arm,limit=args.limit,session=i,status="error",delivery_gaps=0)
    await barrier.wait()
    start=time.perf_counter()
    try:
        async with asyncio.timeout(args.timeout):
            async with connect(args.url,max_size=2**22,open_timeout=args.timeout,close_timeout=3) as ws:
                connected=time.perf_counter()
                row["upgrade_ms"]=round((connected-start)*1000,3)
                await asyncio.sleep(args.idle_seconds)
                await ws.send(json.dumps({"type":"setup","json_config":"","model_name":"","output_format":"pcm","voice":None,"voice_id":None,"voice_emb":None}))
                setup=time.perf_counter()
                while True:
                    m=json.loads(await ws.recv())
                    if m.get("type")=="error":raise RuntimeError("setup: "+str(m))
                    if m.get("type")=="ready":break
                row["setup_ms"]=round((time.perf_counter()-setup)*1000,3)
                await ws.send(json.dumps({"type":"text","text":args.text}))
                requested=time.perf_counter()
                await ws.send(json.dumps({"type":"flush","flush_id":i+1}))
                chunks=[]
                last_stop=0
                while True:
                    m=json.loads(await ws.recv())
                    if m.get("type")=="error":raise RuntimeError("stream: "+str(m))
                    if m.get("type")=="audio":
                        a,b=float(m.get("start_s",0)),float(m.get("stop_s",0))
                        if b>a:
                            chunks.append((time.perf_counter(),b-a))
                            last_stop=b
                    if m.get("type")=="flushed" and m.get("flush_id")==i+1:break
                if not chunks:raise RuntimeError("no nonempty audio")
                ratios=[(chunks[j][0]-chunks[j-1][0])/chunks[j-1][1] for j in range(1,len(chunks))]
                row.update(status="ok",ttfa_request_ms=round((chunks[0][0]-requested)*1000,3),
                           ttfa_admitted_ms=round((chunks[0][0]-connected)*1000,3),
                           audio_chunks=len(chunks),audio_seconds=round(last_stop,3),
                           delivery_gaps=sum(r>1 for r in ratios),
                           worst_gap_ratio=round(max(ratios),4) if ratios else "")
    except InvalidStatus as exc:
        row.update(status="rejected",http_status=getattr(getattr(exc,"response",None),"status_code",""),error=str(exc)[:200])
    except Exception as exc:row["error"]=repr(exc)[:200]
    return row

async def run(args):
    if not args.url.startswith(("ws://127.0.0.1:","ws://localhost:")) and not args.allow_remote:
        raise SystemExit("Remote load tests require --allow-remote and authorization")
    barrier=asyncio.Barrier(args.sessions)
    rows=await asyncio.gather(*(session(args,i,barrier) for i in range(args.sessions)))
    path=Path(args.output);path.parent.mkdir(parents=True,exist_ok=True)
    with path.open("w",newline="") as f:
        w=csv.DictWriter(f,fieldnames=FIELDS);w.writeheader();w.writerows(rows)
    good=[r for r in rows if r["status"]=="ok"]
    ttfa=sorted(r["ttfa_request_ms"] for r in good)
    summary={"arm":args.arm,"labelled_limit":args.limit,"sessions":args.sessions,
             "accepted":len(good),"rejected_429":sum(r["http_status"]==429 for r in rows),
             "other_errors":sum(r["status"]=="error" for r in rows),
             "sample_ttfa_request_p99_ms":ttfa[min(len(ttfa)-1,math.ceil(.99*len(ttfa))-1)] if ttfa else None,
             "delivery_gaps":sum(int(r["delivery_gaps"]) for r in good),
             "caution":"Small sample p99 is not stable; ttfa_admitted includes deliberate idle time; limit is a label only."}
    path.with_suffix(".json").write_text(json.dumps(summary,indent=2)+"\n")
    print(json.dumps(summary,indent=2))
    if summary["other_errors"]:raise SystemExit(2)

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--url",default="ws://127.0.0.1:8080/speech/tts")
    p.add_argument("--arm",default="B-connection-permit")
    p.add_argument("--limit",type=int,default=8)
    p.add_argument("--sessions",type=int,default=10)
    p.add_argument("--idle-seconds",type=float,default=2)
    p.add_argument("--timeout",type=float,default=60)
    p.add_argument("--text",default="Hello, this is a test of the Phonon TTS system.")
    p.add_argument("--output",default="out/ws-B.csv")
    p.add_argument("--allow-remote",action="store_true")
    args=p.parse_args()
    if not 1<=args.sessions<=32 or args.idle_seconds<0:p.error("invalid sessions/idle")
    asyncio.run(run(args))
