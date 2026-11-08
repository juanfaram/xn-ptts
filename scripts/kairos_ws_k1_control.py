#!/usr/bin/env python3
"""KAIROS: original server-only capacity sweep. Three waves per k.
Transport delivery_gap proxy, not audible underrun. Do not call a sample p99
a population tail. Save all failed waves and stop at 2/3 failures."""
import argparse, asyncio, base64, csv, hashlib, json, math, os, statistics, time
from array import array
from pathlib import Path
from websockets.asyncio.client import connect

TEXT="Hello, this is a test of the Phonon TTS system."
FIELDS=["k","repeat","flow","status","ttfa_ms","audio_seconds","chunks","gaps","worst_ratio","median_ratio","p95_ratio","p99_sample_ratio","pcm16_sha256","samples","max_abs_lsb","memory_rss_mib","cpu_busy_pct","error"]

def percentile(xs,p):
    if not xs:return None
    xs=sorted(xs)
    return xs[max(0,math.ceil(p*len(xs))-1)]

def read_cpu():
    with open("/proc/stat") as f:
        vals=list(map(int,f.readline().split()[1:]))
    return sum(vals), vals[3]+(vals[4] if len(vals)>4 else 0)

def read_rss(pid):
    try:
        for line in Path(f"/proc/{pid}/status").read_text().splitlines():
            if line.startswith("VmRSS:"):return round(int(line.split()[1])/1024,2)
    except (FileNotFoundError,PermissionError):pass
    return None

async def stream(url,flow,barrier,timeout):
    try:
        async with asyncio.timeout(timeout):
            async with connect(url,open_timeout=10,max_size=2**22) as ws:
                await ws.send(json.dumps({"type":"setup","json_config":"","model_name":"","output_format":"pcm","voice":None,"voice_id":None,"voice_emb":None}))
                while True:
                    m=json.loads(await ws.recv())
                    if m.get("type")=="error":raise RuntimeError("setup "+str(m))
                    if m.get("type")=="ready":break
                await barrier.wait()
                await ws.send(json.dumps({"type":"text","text":TEXT}))
                t0=time.perf_counter()
                await ws.send(json.dumps({"type":"flush","flush_id":flow+1}))
                chunks=[];raw=bytearray(); fragment_rows=[]
                while True:
                    m=json.loads(await ws.recv())
                    if m.get("type")=="error":raise RuntimeError("generate "+str(m))
                    if m.get("type")=="audio":
                        d=float(m.get("stop_s",0))-float(m.get("start_s",0))
                        if d>0:
                            pcm=base64.b64decode(m["audio"],validate=True)
                            if len(pcm)%2:raise ValueError("odd PCM16 byte count")
                            raw.extend(pcm);arrival=time.perf_counter();chunks.append((arrival,d));fragment_rows.append({"idx":len(chunks)-1,"ts_recv_monotonic_s":arrival,"frag_ms":round(d*1000,4),"pcm16_bytes":len(pcm)})
                    if m.get("type")=="flushed" and m.get("flush_id")==flow+1:break
                if not chunks:raise RuntimeError("empty audio")
                ratios=[(chunks[j][0]-chunks[j-1][0])/chunks[j-1][1] for j in range(1,len(chunks))]
                for j in range(1,len(fragment_rows)):
                    interval=(fragment_rows[j]["ts_recv_monotonic_s"]-fragment_rows[j-1]["ts_recv_monotonic_s"])*1000
                    fragment_rows[j]["inter_ms"]=round(interval,4)
                    fragment_rows[j]["margin_ratio"]=round(interval/fragment_rows[j-1]["frag_ms"],5)
                    fragment_rows[j]["gap"]=interval>fragment_rows[j-1]["frag_ms"]
                fragment_rows[0].update({"inter_ms":None,"margin_ratio":None,"gap":False})
                return {"flow":flow,"status":"ok","ttfa_ms":round((chunks[0][0]-t0)*1000,3),
                        "audio_seconds":round(sum(d for _,d in chunks),4),"chunks":len(chunks),
                        "gaps":sum(r>1 for r in ratios),
                        "worst_ratio":round(max(ratios),5) if ratios else 0,
                        "median_ratio":round(statistics.median(ratios),5) if ratios else 0,
                        "p95_ratio":round(percentile(ratios,.95),5) if ratios else 0,
                        "p99_sample_ratio":round(percentile(ratios,.99),5) if ratios else 0,
                        "pcm16_sha256":hashlib.sha256(raw).hexdigest(),"samples":len(raw)//2,
                        "_pcm":bytes(raw),"_ratios":ratios,"_fragments":fragment_rows}
    except Exception as exc:
        return {"flow":flow,"status":"error","error":repr(exc)}

def tolerance(a,b):
    if len(a)!=len(b):return None
    x=array("h");y=array("h");x.frombytes(a);y.frombytes(b)
    if os.sys.byteorder!="little":x.byteswap();y.byteswap()
    return max((abs(u-v) for u,v in zip(x,y)),default=None)

async def wave(args,k,rep,reference):
    barrier=asyncio.Barrier(k)
    cpu_before=read_cpu();rss_before=read_rss(args.pid)
    result=await asyncio.gather(*(stream(args.url,i,barrier,args.timeout) for i in range(k)))
    cpu_after=read_cpu();rss_after=read_rss(args.pid)
    delta=cpu_after[0]-cpu_before[0]
    cpu=round(100*(1-(cpu_after[1]-cpu_before[1])/delta),2) if delta else None
    rows=[];detail=[]
    for item in result:
        raw=item.pop("_pcm",None);ratios=item.pop("_ratios",[]);fragments=item.pop("_fragments",[])
        item.update(k=k,repeat=rep,memory_rss_mib=max(v for v in (rss_before,rss_after) if v is not None) if any(v is not None for v in (rss_before,rss_after)) else None,cpu_busy_pct=cpu)
        item["max_abs_lsb"]=tolerance(reference,raw) if reference is not None and raw is not None else None
        rows.append(item)
        detail.append({"flow":item["flow"],"ratios":ratios,"fragments":fragments,"gap_indices":[f["idx"] for f in fragments if f.get("gap")]})
    (args.output/f"k{k}-r{rep}-ratios.json").write_text(json.dumps(detail,indent=2)+"\n")
    return rows, (result[0].get("_pcm") if False else None)

async def main(args):
    if not args.url.startswith(("ws://127.0.0.1:","ws://localhost:")):
        raise SystemExit("Only local server tests permitted")
    args.output.mkdir(parents=True,exist_ok=True)
    # A separate sequential k1 reference is taken on the SAME server and same run.
    gate=asyncio.Barrier(1)
    ref=await stream(args.url,0,gate,args.timeout)
    reference=ref.pop("_pcm",None);ref.pop("_ratios",None);ref.pop("_fragments",None)
    (args.output/"reference.json").write_text(json.dumps(ref,indent=2)+"\n")
    if reference is None:raise RuntimeError("k1 reference failed")
    (args.output/"reference.pcm16.sha256").write_text(hashlib.sha256(reference).hexdigest()+"\n")
    summary=[];all_rows=[];last_clean=None;gap_map={}
    for k in range(args.start,args.end+1):
        failures=0
        for rep in range(1,6):
            rows,_=await wave(args,k,rep,reference)
            details=json.loads((args.output/f"k{k}-r{rep}-ratios.json").read_text())
            gap_map[f"k{k}-r{rep}"]=[d["gap_indices"] for d in details]
            all_rows.extend(rows)
            ok=(len(rows)==k and all(
                r["status"]=="ok" and r["gaps"]==0 and r["worst_ratio"]<=1
                and r["ttfa_ms"]<=200 and r["max_abs_lsb"] is not None
                and r["max_abs_lsb"]<=1 for r in rows))
            failures+=not ok
            print(f"k={k} repeat={rep} pass={ok} failures={failures} TTFA={[r.get('ttfa_ms') for r in rows]} gaps={[r.get('gaps') for r in rows]}",flush=True)
            with (args.output/"flows.csv").open("w",newline="") as f:
                w=csv.DictWriter(f,fieldnames=FIELDS,extrasaction="ignore");w.writeheader();w.writerows(all_rows)
        summary.append({"k":k,"passes":5-failures,"failures":failures,
                        "status":"PASS_5_OF_5" if failures==0 else "FAIL_2_OF_5" if failures>=2 else "INCONCLUSIVE",
                        "ttfa_sample_p99_ms":percentile([r["ttfa_ms"] for r in all_rows if r["k"]==k and r["status"]=="ok"],.99),
                        "max_delivery_gap_ratio":max((r["worst_ratio"] for r in all_rows if r["k"]==k and r["status"]=="ok"),default=None),
                        "max_rss_mib":max((r["memory_rss_mib"] for r in all_rows if r["k"]==k and r["memory_rss_mib"] is not None),default=None)})
        if failures==0:last_clean=k
        if failures>=2:
            print(f"STOP: first reproducible failure at k={k}; last clean={last_clean}",flush=True)
            break
    repetition_files = sorted(args.output.glob("k*-r*-ratios.json"))
    report = {"last_certified_k":last_clean,"levels":summary,
              "gap_positions_by_wave":gap_map,
              "repetition_files":[p.name for p in repetition_files],
              "repetition_file_count":len(repetition_files),
              "note":"Counted actual repetition files; sample p99 is unstable; gap proxy, not audible underrun; no admission queue measured"}
    dest = args.output/"summary.json"
    version = 1
    while dest.exists():
        dest = args.output/f"summary.{version}.json"
        version += 1
    dest.write_text(json.dumps(report,indent=2)+"\\n")

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--url",default="ws://127.0.0.1:8080/speech/tts")
    p.add_argument("--pid",type=int,required=True)
    p.add_argument("--start",type=int,default=2)
    p.add_argument("--end",type=int,default=6)
    p.add_argument("--timeout",type=float,default=120)
    p.add_argument("--output",type=Path,default=Path("out/sweep"))
    args=p.parse_args()
    if not 1<=args.start<=args.end<=8:p.error("k must be 1..8")
    asyncio.run(main(args))
