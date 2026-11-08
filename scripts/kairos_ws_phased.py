#!/usr/bin/env python3
"""Real 16+1-client phased WebSocket admission test for pinned Phonon.
Warmup -> 8 idle connections -> 8 incoming -> 8 simultaneous generators -> late.
One process; monotonic consumer timestamps. No changes to Gradium code.
"""
import argparse,asyncio,base64,json,time,hashlib,statistics
from pathlib import Path
import websockets

def cpu_ticks():
    with open("/proc/stat") as f:
        a=list(map(int,f.readline().split()[1:]))
    idle=a[3]+a[4]
    return sum(a),idle

def cpu_fraction(start,end):
    total=end[0]-start[0]
    return (total-(end[1]-start[1]))/total if total else None

def now():return time.perf_counter_ns()

class Client:
    def __init__(self,i,url):
        self.i=i;self.url=url;self.ws=None
        self.d={"id":i,"accepted":False,"http_status":None,"error":None,"chunks":[],
                "connected_ns":None,"ready_ns":None,"request_ns":None,
                "first_audio_ns":None,"complete_ns":None}
    async def connect(self,timeout):
        try:
            self.ws=await websockets.connect(self.url,open_timeout=timeout,max_size=16*1024*1024)
            self.d["accepted"]=True
            self.d["connected_ns"]=now()
            await self.ws.send(json.dumps({"type":"setup","json_config":"","model_name":"",
               "output_format":"pcm","voice":None,"voice_id":None,"voice_emb":None}))
            while True:
                r=json.loads(await asyncio.wait_for(self.ws.recv(),timeout))
                if r["type"]=="ready":
                    self.d["ready_ns"]=now()
                    self.d["sample_rate"]=r["sample_rate"]
                    return
                if r["type"]=="error":raise RuntimeError("setup: "+str(r))
        except Exception as e:
            self.d["error"]=str(e)
            self.d["http_status"]=getattr(e,"status_code",None) or getattr(getattr(e,"response",None),"status_code",None)
            if self.ws:
                await self.ws.close();self.ws=None
    async def generate(self,text,timeout):
        if not self.ws:return
        try:
            self.d["request_ns"]=now()
            await self.ws.send(json.dumps({"type":"text","text":text}))
            await self.ws.send(json.dumps({"type":"flush","flush_id":self.i+1}))
            while True:
                r=json.loads(await asyncio.wait_for(self.ws.recv(),timeout))
                t=now()
                if r["type"]=="audio" and r["stop_s"]>r["start_s"]:
                    if self.d["first_audio_ns"] is None:self.d["first_audio_ns"]=t
                    raw=base64.b64decode(r["audio"],validate=True)
                    self.d["chunks"].append({"arrival_ns":t,"start_s":r["start_s"],
                       "stop_s":r["stop_s"],"bytes":len(raw),
                       "sha256":hashlib.sha256(raw).hexdigest()})
                elif r["type"]=="flushed" and r["flush_id"]==self.i+1:
                    self.d["complete_ns"]=t;break
                elif r["type"]=="error":raise RuntimeError("generation: "+str(r))
        except Exception as e:self.d["error"]=str(e)
        ch=self.d["chunks"]
        ratios=[]
        for a,b in zip(ch,ch[1:]):
            duration_ms=1000*(a["stop_s"]-a["start_s"])
            if duration_ms>0:ratios.append((b["arrival_ns"]-a["arrival_ns"])/1e6/duration_ms)
        self.d["delivery_ratios"]=ratios
        self.d["delivery_gap_count"]=sum(r>1 for r in ratios)
        self.d["deadline_80_count"]=sum(r>0.8 for r in ratios)
        if self.d["first_audio_ns"] is not None:
            self.d["ttfa_request_ms"]=(self.d["first_audio_ns"]-self.d["request_ns"])/1e6
    async def close(self):
        if self.ws:
            await self.ws.close();self.ws=None

async def main(args):
    results={"schema":"kairos_phased_ws_v1","arm":args.arm,"permits":args.permits,
             "idle_seconds":args.idle_seconds,"text":args.text,"active_generators":args.active_generators,"phases":{}}
    all_clients=[]
    async def connect(i):
        c=Client(i,args.url);all_clients.append(c)
        await c.connect(args.timeout)
        return c
    try:
        warm=await connect(-1)
        if not warm.d["accepted"]:raise RuntimeError("warmup not admitted: "+str(warm.d))
        await warm.generate(args.text,args.timeout)
        if not warm.d["chunks"]:raise RuntimeError("warmup produced no audio")
        results["phases"]["warmup"]=warm.d
        await warm.close()
        # Server releases the warmup session slot asynchronously after socket close.
        # Wait for its teardown before starting the exact 8-session occupancy phase.
        await asyncio.sleep(1.0)
        first=await asyncio.gather(*(connect(i) for i in range(args.occupancy)))
        if sum(c.d["accepted"] for c in first)!=args.occupancy:
            print("PHASE_2_MOUNT_FAILURE",json.dumps([c.d for c in first]),flush=True)
            raise RuntimeError("phase 2 failed to admit all initial connections")
        print("PHASE_2_IDLE_CONNECTED",args.occupancy,flush=True)
        await asyncio.sleep(args.idle_seconds)
        second=await asyncio.gather(*(connect(i) for i in range(args.occupancy,16)))
        results["phases"]["wave"]={"accepted":sum(c.d["accepted"] for c in second),
             "http_429":sum(c.d["http_status"]==429 for c in second),
             "clients":[c.d.copy() for c in second]}
        print("PHASE_3",json.dumps({"accepted":results["phases"]["wave"]["accepted"],
             "http_429":results["phases"]["wave"]["http_429"]}),flush=True)
        # First N accepted sessions generate; other admitted sessions stay idle.
        cpu_start=cpu_ticks()
        generators=[asyncio.create_task(c.generate(args.text,args.timeout)) for c in first[:args.active_generators]]
        # Attempt the late client while original 8 are actively generating.
        await asyncio.sleep(args.late_delay)
        active_at_late=sum(not t.done() for t in generators)
        late=await connect(16)
        late_task=asyncio.create_task(late.generate(args.text,args.timeout)) if late.d["accepted"] else None
        await asyncio.gather(*generators)
        cpu_end=cpu_ticks()
        if late_task is not None:await late_task
        results["phases"]["load"]={"machine_cpu_busy_fraction_including_harness":cpu_fraction(cpu_start,cpu_end),
            "cpu_window_end_ns":now(),"flows":[c.d for c in first]}
        results["phases"]["late"]={"active_generators_when_attempted":active_at_late,
            "client":late.d}
        results["phases"]["wave"]["clients"]=[c.d for c in second]
        print("PHASE_4_CPU_BUSY",results["phases"]["load"]["machine_cpu_busy_fraction_including_harness"],flush=True)
        print("PHASE_5_LATE",json.dumps({"accepted":late.d["accepted"],
            "active_at_attempt":active_at_late,
            "ttfa_request_ms":late.d.get("ttfa_request_ms"),
            "http_status":late.d["http_status"]}),flush=True)
        if args.arm=="B":
            expected=16-args.occupancy
            if results["phases"]["wave"]["http_429"]!=expected:
                raise RuntimeError(f"INVALID_B_MOUNT: expected {expected} HTTP429 in phase 3")
        if active_at_late==0:
            results["phases"]["late"]["valid_active_overlap"]=False
            print("WARNING: late arrived after generation ended; late measurement invalid",flush=True)
        else:
            results["phases"]["late"]["valid_active_overlap"]=True
    finally:
        for c in all_clients:
            try:await c.close()
            except Exception:pass
        dest=Path(args.output);dest.parent.mkdir(parents=True,exist_ok=True)
        dest.write_text(json.dumps(results,indent=2)+"\n")
        print("EVIDENCE_WRITTEN",dest,flush=True)

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--url",default="ws://127.0.0.1:8080/speech/tts")
    p.add_argument("--arm",choices=["B","C"],default="B")
    p.add_argument("--permits",type=int,default=8)
    p.add_argument("--idle-seconds",type=float,default=30)
    p.add_argument("--occupancy",type=int,default=8)
    p.add_argument("--active-generators",type=int,default=4)
    p.add_argument("--late-delay",type=float,default=0.05)
    p.add_argument("--timeout",type=float,default=180)
    p.add_argument("--text",default="The quick brown fox jumps over the lazy dog.")
    p.add_argument("--output",default="out/ws-phased.json")
    args=p.parse_args()
    assert 1<=args.active_generators<=args.occupancy<=16
    asyncio.run(main(args))
