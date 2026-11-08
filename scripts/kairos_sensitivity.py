#!/usr/bin/env python3
"""Illustrative sensitivity analysis, NOT measured capacity or KAIROS uplift."""
import argparse,csv,math
p=argparse.ArgumentParser()
p.add_argument("--rtf",type=float,default=0.16505)
p.add_argument("--baseline-permits",type=int,default=8)
p.add_argument("--memory-sessions",type=int,default=160)
p.add_argument("--usd-per-hour",type=float,default=0.15)
p.add_argument("--output",default="out/sensitivity.csv")
args=p.parse_args()
assert args.rtf>0 and args.baseline_permits>0 and args.memory_sessions>0
from pathlib import Path
out=Path(args.output);out.parent.mkdir(parents=True,exist_ok=True)
with out.open("w",newline="") as f:
 w=csv.writer(f)
 w.writerow(["activity","rtf_measured_single_stream","ideal_active_stream_capacity",
             "memory_session_cap_assumed","ideal_users_capped",
             "baseline_connection_permits","illustrative_capacity_ratio",
             "baseline_instances_per_1000","ideal_instances_per_1000",
             "usd_per_min_audio_at_full_single_stream_utilization"])
 for a in [.05,.10,.25,.38,.50,.76,1.0]:
  capacity=1/args.rtf
  users=min(args.memory_sessions,capacity/a)
  ratio=users/args.baseline_permits
  w.writerow([a,args.rtf,round(capacity,4),args.memory_sessions,
              round(users,4),args.baseline_permits,round(ratio,4),
              math.ceil(1000/args.baseline_permits),math.ceil(1000/users),
              round(args.usd_per_hour*args.rtf/60,8)])
  print(f"a={a:.2f} users_ideal={users:.2f} ratio={ratio:.2f}x "
        f"instances_B={math.ceil(1000/args.baseline_permits)} "
        f"instances_ideal={math.ceil(1000/users)}")
print("CAVEAT: ideal CPU/memory admission arithmetic only; not demonstrated KAIROS or measured costs.")
print("Cost/min uses single-stream measured RTF at 100% sustained engine use, not arbitrary k.")
