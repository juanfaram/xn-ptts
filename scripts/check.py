#!/usr/bin/env python3
"""Fail closed on late audio chunks. Inter-arrival gaps are compared to the
PREVIOUS fragment's playback duration (not the current fragment).
This is a strict gap proxy, not a simulated playout-buffer delivery_gap."""
import argparse
import csv
import glob
import sys
from collections import defaultdict

def check(paths):
    count = 0
    violations = []
    for path in paths:
        with open(path, newline="") as f:
            rows = list(csv.DictReader(f))
        required = {"wave","phase","k","flow","chunk","arrival_ns","interval_ns",
                    "frag_samples","frag_ms","ttfa_request_ms","ttfa_admitted_ms","sha256"}
        if not rows or not required.issubset(rows[0]):
            raise ValueError(f"{path}: empty CSV or missing columns: {sorted(required - set(rows[0] if rows else []))}")
        groups = defaultdict(list)
        for row in rows:
            groups[(row["wave"],row["flow"])].append(row)
        for key, chunks in groups.items():
            chunks.sort(key=lambda r:int(r["chunk"]))
            if int(chunks[0]["chunk"]) != 0:
                raise ValueError(f"{path} {key}: first chunk not zero")
            for idx, row in enumerate(chunks):
                if int(row["chunk"]) != idx:
                    raise ValueError(f"{path} {key}: missing/duplicate chunk")
                if float(row["frag_ms"]) <= 0 or int(row["frag_samples"]) <= 0:
                    raise ValueError(f"{path} {key}: nonpositive fragment")
                if not row["sha256"] or len(row["sha256"]) != 64:
                    raise ValueError(f"{path} {key}: missing/invalid hash")
                if idx:
                    gap_ms = int(row["interval_ns"]) / 1e6
                    deadline_ms = float(chunks[idx-1]["frag_ms"])
                    count += 1
                    if gap_ms > deadline_ms:
                        violations.append((path,key,idx,gap_ms,deadline_ms))
    for path,key,idx,gap,deadline in violations:
        print(f"DELIVERY_GAP {path} wave/flow={key} chunk={idx} gap={gap:.3f}ms previous_frag={deadline:.3f}ms",file=sys.stderr)
    print(f"Checked {count} inter-fragment gaps; violations={len(violations)}")
    return 1 if violations else 0

def mutation_test():
    import tempfile
    from pathlib import Path
    with tempfile.TemporaryDirectory() as tmp:
        p=Path(tmp)/"mutation.csv"
        columns=["wave","phase","k","flow","chunk","arrival_ns","interval_ns","frag_samples","frag_ms","ttfa_request_ms","ttfa_admitted_ms","sha256"]
        def write(gap):
            with p.open("w",newline="") as f:
                w=csv.DictWriter(f,fieldnames=columns);w.writeheader()
                for i in range(2):
                    w.writerow(dict(wave=0,phase="measured",k=1,flow=0,chunk=i,
                      arrival_ns=0 if i==0 else gap,interval_ns="" if i==0 else gap,
                      frag_samples=2400,frag_ms="100.0",ttfa_request_ms=1,
                      ttfa_admitted_ms=1,sha256="a"*64))
        write(50_000_000)
        assert check([str(p)])==0,"false positive on healthy fixture"
        write(150_000_000)
        assert check([str(p)])==1,"MUTATION TEST FAILED: injected 150ms gap escaped 100ms deadline"
    print("MUTATION TEST PASSED: injected late chunk detected")

if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("files",nargs="*")
    parser.add_argument("--self-test",action="store_true")
    args=parser.parse_args()
    if args.self_test:
        mutation_test()
    else:
        paths=[p for pattern in args.files for p in glob.glob(pattern)]
        if not paths:
            parser.error("no CSV files found")
        sys.exit(check(paths))
