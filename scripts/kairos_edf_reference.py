#!/usr/bin/env python3
"""Deterministic deadline ordering for offline verification before Rust integration."""
import heapq
from dataclasses import dataclass, field

@dataclass(order=True)
class Request:
    deadline_ms: float
    sequence: int
    arrived_ms: float=field(compare=False)
    client_class: str=field(compare=False)

def sequence(seed=20261109, n=100):
    import random
    r=random.Random(seed)
    requests=[]
    for i in range(n):
        short=r.random()<.3
        requests.append(Request((i*5)+(150 if short else 1000),i,i*5,"short" if short else "long"))
    return requests

def serve(requests, start_ms=500, service_ms=80):
    queue=list(requests)
    heapq.heapify(queue)
    accepted=[];expired=[];max_long_wait=0
    now=start_ms
    while queue:
        item=heapq.heappop(queue)
        if now>item.deadline_ms:
            expired.append(item.sequence)
            continue
        accepted.append(item.sequence)
        if item.client_class=="long":
            max_long_wait=max(max_long_wait,now-item.arrived_ms)
        now+=service_ms
    return {"accepted":accepted,"expired":expired,"max_long_wait_ms":max_long_wait}

def test():
    items=sequence()
    assert len(items)==100 and len([x for x in items if x.client_class=="short"])>0
    assert [x.sequence for x in sorted(items)]==[x.sequence for x in sorted(items,key=lambda x:(x.deadline_ms,x.sequence))]
    r=serve(items)
    assert len(r["accepted"])+len(r["expired"])==100
    assert all(x in set(range(100)) for x in r["accepted"])
    assert sequence()==sequence()
    print("EDF ordering, deadline expiry, deterministic arrivals: OK")

if __name__=="__main__":test()
