#!/usr/bin/env python3
"""KAIROS strict smoke validator. Raw PCM is f32 little-endian; tolerance <=1e-6.
Self-test uses the exact deadline validator used for real stream events.
Consumer interval / previous emitted chunk duration is a deadline PROXY,
not a full audio-buffer underrun detector.
"""
import csv
import hashlib
import math
import struct
import sys
from pathlib import Path

TOL_F32 = 1e-6
MAX_INTERVAL_RATIO = 0.8

def events(folder):
    with (Path(folder) / "flows.csv").open(newline="") as f:
        rows = [r for r in csv.DictReader(f) if r["phase"] == "measured"]
    assert rows, f"no measured events: {folder}"
    return rows

def flows(rows):
    out = {}
    for row in rows:
        out.setdefault(int(row["flow"]), []).append(row)
    return out

def check_deadline(rows):
    assert len(rows) >= 2, "insufficient chunks to evaluate delivery"
    ratios = []
    for previous, current in zip(rows, rows[1:]):
        interval_ms = float(current["interval_ns"]) / 1e6
        previous_duration_ms = float(previous["chunk_dur_ms"])
        assert previous_duration_ms > 0, "invalid chunk duration"
        ratios.append(interval_ms / previous_duration_ms)
    assert all(r <= MAX_INTERVAL_RATIO for r in ratios), (
        f"delivery deadline proxy failed: worst ratio {max(ratios):.3f}"
    )
    return max(ratios)

def self_test():
    import io
    header = "phase,flow,interval_ns,chunk_dur_ms\\n"
    bad = header + "measured,0,,20\\nmeasured,0,30000000,20\\n"
    rows = list(csv.DictReader(io.StringIO(bad)))
    try:
        check_deadline(rows)
    except AssertionError as exc:
        assert "delivery deadline proxy failed" in str(exc), str(exc)
        print("SELFTEST_PASS: injected 30ms interval after 20ms chunk rejected")
        return
    raise AssertionError("SELFTEST_FAIL: injected deadline violation was accepted")

def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def pcm_float(path):
    raw = Path(path).read_bytes()
    assert len(raw) % 4 == 0, f"invalid f32le byte length: {path}"
    return struct.unpack("<" + "f" * (len(raw)//4), raw)

def compare_pcm(ref, candidate):
    a, b = pcm_float(ref), pcm_float(candidate)
    assert len(a) == len(b), "PCM sample count differs"
    assert a, "empty PCM"
    delta = max(abs(x-y) for x, y in zip(a, b))
    assert math.isfinite(delta), "nonfinite PCM difference"
    print("MAX_ABS_F32_DIFFERENCE", delta)
    assert delta <= TOL_F32, f"f32 PCM difference {delta} > {TOL_F32}"

def validate():
    a, b, c = events("out/k1a"), events("out/k1b"), events("out/k2")
    ref_a, ref_b = "out/k1a/audio_w1_f0.f32le", "out/k1b/audio_w1_f0.f32le"
    hash_a, hash_b = sha(ref_a), sha(ref_b)
    print("K1_HASH_A", hash_a)
    print("K1_HASH_B", hash_b)
    deterministic = hash_a == hash_b
    print("K1_DETERMINISTIC", deterministic)
    if not deterministic:
        compare_pcm(ref_a, ref_b)

    # One measured wave per k1 repetition: not a statistically stable p99.
    base_ttfa = max(float(a[0]["ttfa_ns"]), float(b[0]["ttfa_ns"]))
    print("K1_WORST_TTFA_MS", base_ttfa/1e6)

    f = flows(c)
    assert set(f) == {0, 1}, f"expected two flows, got {sorted(f)}"
    for flow, rows in sorted(f.items()):
        path = f"out/k2/audio_w1_f{flow}.f32le"
        actual_hash = sha(path)
        print("K2_FLOW", flow, "CHUNKS", len(rows), "SHA256", actual_hash)
        if deterministic:
            assert actual_hash == hash_a, f"flow {flow} differs from deterministic k1"
        else:
            compare_pcm(ref_a, path)
        ttfa = float(rows[0]["ttfa_ns"])
        print("K2_FLOW", flow, "TTFA_MS", ttfa/1e6)
        assert ttfa <= 1.5*base_ttfa, f"flow {flow} TTFA regression >1.5x"
        worst_ratio = check_deadline(rows)
        print("K2_FLOW", flow, "WORST_DELIVERY_RATIO", worst_ratio)
    print("K2_SMOKE_PASS")

if __name__ == "__main__":
    if len(sys.argv) == 2 and sys.argv[1] == "--self-test":
        self_test()
    elif len(sys.argv) == 1:
        validate()
    else:
        raise SystemExit("Usage: kairos_validate_k2.py [--self-test]")
