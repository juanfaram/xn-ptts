#!/usr/bin/env python3
"""Offline analysis of KAIROS capture ZIP. No network or server needed."""
import argparse, hashlib, json, zipfile
from pathlib import Path

def analyze(frags, preload):
    frags = sorted(frags, key=lambda f: f["idx"])
    if not frags or [f["idx"] for f in frags] != list(range(len(frags))):
        raise ValueError("missing/nonconsecutive fragments")
    t0 = frags[0]["ts_recv_monotonic_s"] * 1000
    p = preload * frags[0]["frag_ms"]
    cumulative = 0.0
    reserve = []
    for f in frags:
        reserve.append(t0 + p + cumulative - f["ts_recv_monotonic_s"] * 1000)
        cumulative += f["frag_ms"]
    episodes = []
    active = None
    for i, r in enumerate(reserve):
        if r < -1e-6:
            if active is None:
                active = {"start_idx": i, "end_idx": i, "max_deficit_ms": -r}
            else:
                active["end_idx"] = i
                active["max_deficit_ms"] = max(active["max_deficit_ms"], -r)
        elif active is not None:
            episodes.append(active)
            active = None
    if active is not None:
        episodes.append(active)
    for e in episodes:
        e["duration_ms"] = round(e["max_deficit_ms"], 5)
        e["max_deficit_ms"] = round(e["max_deficit_ms"], 5)
        e["depth_fragments"] = e["end_idx"] - e["start_idx"] + 1
    return {"minimum_reserve_ms": round(min(reserve), 5),
            "exhaustion_count": len(episodes), "episodes": episodes,
            "total_no_audio_ms": round(sum(e["duration_ms"] for e in episodes), 5),
            "max_depth_fragments": max((e["depth_fragments"] for e in episodes), default=0)}

def load(path):
    with zipfile.ZipFile(path) as z:
        manifest = json.loads(z.read("manifest.json"))
        for name, expected in manifest["sha256_files"].items():
            if hashlib.sha256(z.read(name)).hexdigest() != expected:
                raise ValueError("hash mismatch: " + name)
        out = {}
        for name in sorted(z.namelist()):
            if name.startswith("k") and name.endswith("-ratios.json"):
                out[name] = [{"flow": f["flow"], "M0": analyze(f["fragments"], 0),
                              "M1": analyze(f["fragments"], 2)}
                             for f in json.loads(z.read(name))]
        return out

def test():
    def trace(delays):
        return [{"idx": i, "ts_recv_monotonic_s": (1000+i*80+delays.get(i,0))/1000,
                 "frag_ms": 80.0} for i in range(42)]
    assert analyze(trace({}), 0)["exhaustion_count"] == 0
    assert analyze(trace({3:500}), 0)["exhaustion_count"] >= 1
    for model in (0, 2):
        x = analyze(trace({35:500}), model)
        assert x["exhaustion_count"] in (0,1)
    assert analyze(trace({1:1}), 0)["exhaustion_count"] == 1
    assert analyze(trace({1:1}), 2)["exhaustion_count"] == 0
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        p = Path(d)/"test.zip"
        with zipfile.ZipFile(p, "w") as z:
            z.writestr("manifest.json", "not json")
        try: load(p)
        except json.JSONDecodeError: pass
        else: raise AssertionError("corrupt manifest accepted")
        with zipfile.ZipFile(p, "w") as z:
            z.writestr("manifest.json", json.dumps({"sha256_files": {"a": hashlib.sha256(b"ok").hexdigest()}}))
            z.writestr("a", "ok")
        assert load(p) == {}
    print("tests passed")

if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("zip", nargs="?")
    p.add_argument("--test", action="store_true")
    p.add_argument("--output")
    a = p.parse_args()
    if a.test: test()
    if a.zip:
        result = {"zip_sha256": hashlib.sha256(Path(a.zip).read_bytes()).hexdigest(),
                  "flows": load(a.zip)}
        raw = json.dumps(result, indent=2) + "\n"
        if a.output: Path(a.output).write_text(raw)
        else: print(raw)
