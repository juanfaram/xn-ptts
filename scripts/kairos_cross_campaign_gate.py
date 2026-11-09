#!/usr/bin/env python3
"""Read-only cross-campaign evidence gate; refuses non-equivalent SES comparisons."""
import argparse, json
from pathlib import Path

CAMPAIGNS={
 "rust_three_turn":{
  "branch":"run/kairos-policy-isolation-k23",
  "session_turns":3,"implementation":"patched Rust server",
  "activities":"synthetic arrival spacing 10/25/40",
  "short_deadline_ms":150,"long_deadline_ms":1000,
  "audio_gate":"42 chunks per turn; v3 continuity not certified",
  "primary_control":"D-3 FIFO+deadline"},
 "proxy_four_turn":{
  "branch":"run/kairos-economic-verdict",
  "session_turns":4,"implementation":"Python WS proxy over original Rust server",
  "activities":"20 sessions; active fractions 10/25/50, four simultaneous turns per wave",
  "short_deadline_ms":240,"long_deadline_ms":1000,
  "audio_gate":"virtual M0 and PCM reference <=1 LSB",
  "primary_control":"fifo_expire"}
}
COMPARABILITY_FIELDS=("session_turns","implementation","activities","short_deadline_ms","long_deadline_ms","audio_gate")

def verdict(a,b):
    differences={k:{"a":a[k],"b":b[k]} for k in COMPARABILITY_FIELDS if a[k]!=b[k]}
    return {"directly_poolable":not differences,"differences":differences,
            "rule":"Never pool SES, TTFA, cost or confidence intervals across non-equivalent workloads."}

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--output",type=Path)
    a=p.parse_args()
    v=verdict(*CAMPAIGNS.values())
    report={"schema":"kairos-cross-campaign-gate-v1","campaigns":CAMPAIGNS,
            "comparability":v,
            "shared_evidence":"Admission/permit occupancy, queue diagnostics, code identity and CPU metadata may inform design but not pooled SES effect sizes.",
            "commercial_decision":"C vs D within the SAME frozen 4-turn campaign, same hardware and actual offers, 95% paired CI; zero crossing means no proven EDF benefit.",
            "unverified":"No final economic run metrics or certified sustained SES/euro inferred from workflow success."}
    raw=json.dumps(report,indent=2)+"\n"
    if a.output:
        a.output.parent.mkdir(parents=True,exist_ok=True)
        a.output.write_text(raw)
    print(raw,end="")
    if v["directly_poolable"]:raise SystemExit("Unexpectedly equivalent; audit inputs")

if __name__=="__main__":main()
