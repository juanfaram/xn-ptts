#!/usr/bin/env python3
"""Recompute virtual M0 from stored fragments and report reproducible first-failure evidence."""
import argparse,json,math,statistics
from pathlib import Path
from kairos_playback_v2 import simulate
def q(v,p):
    if not v:return None
    v=sorted(v);return round(v[min(len(v)-1,math.ceil(p*len(v))-1)],3)
def main():
    p=argparse.ArgumentParser();p.add_argument("--root",type=Path,required=True);a=p.parse_args()
    result={"definition":"M0 immediate playback no prebuffer, virtual only","arms":{}}
    for arm in ("fifo_expire","direct32"):
        waves=json.loads((a.root/arm/"runs.json").read_text())
        turns=[t for w in waves if not w["warmup"] for seq in w["turns"].values() for t in seq]
        completed=[t for t in turns if t["status"]=="completed"]
        first=[];gaps=[];stalls=[];bad=0;pcm_bad=0;strict=0
        for t in completed:
            f=t.get("fragments")
            if not f:raise ValueError(f"{arm}: missing fragment trace")
            s=simulate(f)
            if s["episode_count"]!=t["m0_episodes"]:raise ValueError(f"{arm}: M0 mismatch")
            bad+=bool(s["episode_count"])
            stalls.append(s["total_stall_ms"])
            if s["episodes"]:first.append(s["episodes"][0]["idx"])
            for i in range(1,len(f)):
                gaps.append((f[i]["ts_recv_monotonic_s"]-f[i-1]["ts_recv_monotonic_s"])*1000-f[i-1]["frag_ms"])
            pcm_bad+=t["max_abs_lsb"] is None or t["max_abs_lsb"]>1
        offered=[seq for w in waves if not w["warmup"] for seq in w["turns"].values()]
        strict=sum(all(t.get("status")=="completed" and t.get("ttfa_ms",1e9)<=200 and t.get("m0_episodes",1)==0 and t.get("max_abs_lsb") is not None and t["max_abs_lsb"]<=1 for t in seq) for seq in offered)
        result["arms"][arm]={"offered_sessions":len(offered),"strict_complete_sessions":strict,
          "completed_turns":len(completed),"m0_affected_turns":bad,"m0_first_failure_fragment_indices":first,
          "total_virtual_stall_ms":round(sum(stalls),3),"virtual_stall_p95_ms":q(stalls,.95),
          "interfragment_gap_minus_previous_audio_p95_ms":q(gaps,.95),
          "pcm_fail_turns":pcm_bad,"ttfa_p99_completed_ms":q([t["ttfa_ms"] for t in completed],.99)}
    result["limits"]=["No physical audio output; virtual M0 not an audible underrun measurement",
      "This tests measurement integrity and a strong direct-connection control; not billed SES/euro",
      "Comparability requires identical offered sessions and host; direct32 is not a queued FIFO baseline"]
    (a.root/"m0-fragment-audit.json").write_text(json.dumps(result,indent=2)+"\n")
    print(json.dumps(result,indent=2))
if __name__=="__main__":main()
