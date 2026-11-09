#!/usr/bin/env python3
"""Frozen paired offered-load schedule; independent of transport/policy."""
import argparse, hashlib, json, random
from pathlib import Path

SESSIONS=60
TURNS=3
SEED=20261109
ACTIVITY=(10,25,40)
SESSION_TIMEOUT_S=300
FRAGMENTS_EXPECTED=42

def schedule(activity, repeat):
    rng=random.Random(f"{SEED}:{activity}:{repeat}")
    events=[]
    # All 180 generations are offered; activity controls arrival density, not denominator.
    # This is a synthetic offered-load proxy, not a measured user activity percentage.
    deadlines=[150]*54+[1000]*126
    rng.shuffle(deadlines
    )
    spacing_ms=1000//activity
    for turn in range(TURNS):
        for session in range(SESSIONS):
            idx=turn*SESSIONS+session
            events.append({"session":session,"turn":turn,"offer_ms":idx*spacing_ms,
                           "active":True,"deadline_ms":deadlines[idx]})
    return events

def test():
    for a in ACTIVITY:
        for rep in range(1,6):
            x=schedule(a,rep)
            assert len(x)==180
            assert len({(e["session"],e["turn"]) for e in x})==180
            assert x==schedule(a,rep)
            assert all(e["deadline_ms"] in (150,1000) for e in x)
            assert sum(e["deadline_ms"]==150 for e in x)==54
    print("schedule tests OK")

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--output",default="out/kairos-offered-load.json")
    p.add_argument("--test",action="store_true")
    a=p.parse_args()
    if a.test: test()
    data={"schema":"kairos-paired-offered-v1","seed":SEED,"sessions":SESSIONS,
          "turns_per_session":TURNS,"activity_pct":list(ACTIVITY),
          "session_timeout_s":SESSION_TIMEOUT_S,"expected_fragments_per_generation":FRAGMENTS_EXPECTED,
          "repetitions":5,"offered_turns_per_repetition":SESSIONS*TURNS,
          "rejected_expired_timeout_count_as_failure":True,
          "schedules":{f"a{activity}-r{rep}":schedule(activity,rep)
                       for activity in ACTIVITY for rep in range(1,6)}}
    raw=json.dumps(data,sort_keys=True,separators=(",",":"))+"\n"
    dest=Path(a.output);dest.parent.mkdir(parents=True,exist_ok=True)
    dest.write_text(raw)
    print(json.dumps({"sha256":hashlib.sha256(raw.encode()).hexdigest(),
                      "schedules":15,"offered_turns":2700,
                      "note":"Schedule only; not Phonon execution"}))

if __name__=="__main__":main()
