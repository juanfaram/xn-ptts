#!/usr/bin/env python3
"""Strict k2 smoke acceptance on consumer chunk events; not a perceptual audio test."""
import csv,hashlib,math
from pathlib import Path
def events(folder):
 with (Path(folder)/"flows.csv").open(newline="") as f:
  rows=[r for r in csv.DictReader(f) if r["phase"]=="measured"]
 assert rows, f"no measured events: {folder}"
 return rows
def flows(rows):
 out={}
 for r in rows:out.setdefault(int(r["flow"]),[]).append(r)
 return out
def percentile(xs,p):
 xs=sorted(xs)
 assert xs
 return xs[math.ceil(p*len(xs))-1]
a,b,c=events("out/k1a"),events("out/k1b"),events("out/k2")
def hashfile(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
ref1=hashfile("out/k1a/audio_w1_f0.f32le")
ref2=hashfile("out/k1b/audio_w1_f0.f32le")
print("k1 reference hashes",ref1,ref2,"deterministic",ref1==ref2)
if ref1!=ref2:
 print("INDETERMINISTIC: raw PCM tolerance must be checked (<=1 LSB of PCM16 equivalent)")
 import struct
 aa=Path("out/k1a/audio_w1_f0.f32le").read_bytes()
 bb=Path("out/k1b/audio_w1_f0.f32le").read_bytes()
 assert len(aa)==len(bb),"k1 PCM length differs"
 x=struct.unpack("<"+"f"*(len(aa)//4),aa)
 y=struct.unpack("<"+"f"*(len(bb)//4),bb)
 delta=max(abs(i-j) for i,j in zip(x,y))
 print("k1 max abs PCM float difference",delta)
 assert delta<=1/32768,"k1 exceeds predeclared 1-LSB tolerance"
else:
 delta=0
base=max(float(a[0]["ttfa_ns"]),float(b[0]["ttfa_ns"]))
print("k1 baseline worst TTFA ns",base)
f=flows(c)
assert set(f)=={0,1},f"expected two flows, got {list(f)}"
for flow,rows in sorted(f.items()):
 pcm=f"out/k2/audio_w1_f{flow}.f32le"
 sha=hashfile(pcm)
 print("flow",flow,"chunks",len(rows),"sha",sha)
 if ref1==ref2:
  assert sha==ref1,f"flow {flow} PCM differs from deterministic k1"
 else:
  import struct
  ref=Path("out/k1a/audio_w1_f0.f32le").read_bytes()
  dat=Path(pcm).read_bytes()
  assert len(ref)==len(dat),f"flow {flow} PCM length differs"
  x=struct.unpack("<"+"f"*(len(ref)//4),ref)
  y=struct.unpack("<"+"f"*(len(dat)//4),dat)
  assert max(abs(i-j) for i,j in zip(x,y))<=1/32768,f"flow {flow} >1 LSB"
 ttfa=float(rows[0]["ttfa_ns"])
 print("flow",flow,"ttfa_ms",ttfa/1e6)
 assert ttfa<=1.5*base,f"flow {flow} TTFA regression >1.5x"
 ratios=[]
 for prev,cur in zip(rows,rows[1:]):
  interval=float(cur["interval_ns"])/1e6
  prev_dur=float(prev["chunk_dur_ms"])
  assert prev_dur>0
  ratios.append(interval/prev_dur)
 print("flow",flow,"worst consumer interval / previous chunk duration",max(ratios) if ratios else None)
 assert all(v<=0.8 for v in ratios),f"flow {flow} delivery deadline proxy failed"
print("K2_SMOKE_PASS")
