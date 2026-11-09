#!/usr/bin/env python3
"""B-high+Q: local WebSocket relay; FIFO admission at flush, not WS upgrade.
Upstream original server must have max_concurrent_requests >= max_clients.
No Phonon code changes. Admission queue includes full flush->flushed lifetime.
"""
import argparse,asyncio,json,logging,time,math
from collections import deque
from contextlib import suppress
from websockets.asyncio.client import connect
from websockets.asyncio.server import serve

class QueueFull(Exception):
    pass

class FIFO:
    def __init__(self,slots,timeout,max_queue=64):
        if slots<1 or timeout<=0 or max_queue<1:raise ValueError("invalid capacity/timeout/queue")
        self.max_queue=max_queue
        self.slots=slots;self.timeout=timeout;self.active=0;self.max_active=0
        self.waiters=deque();self.lock=asyncio.Lock()
    def pump(self):
        while self.active<self.slots and self.waiters:
            f=self.waiters.popleft()
            if not f.done():
                self.active+=1;self.max_active=max(self.max_active,self.active);f.set_result(True)
    async def acquire(self,deadline_ms=None):
        f=asyncio.get_running_loop().create_future()
        async with self.lock:
            if len(self.waiters)>=self.max_queue:raise QueueFull()
            self.waiters.append(f);self.pump()
        try:
            await asyncio.wait_for(asyncio.shield(f),self.timeout)
        except BaseException:
            async with self.lock:
                if f.done() and not f.cancelled():self.active-=1
                else:
                    with suppress(ValueError):self.waiters.remove(f)
                self.pump()
            raise
    async def release(self):
        async with self.lock:
            if self.active<1:raise RuntimeError("permit underflow")
            self.active-=1;self.pump()

class EDF(FIFO):
    def __init__(self,slots,timeout,max_queue=64):
        super().__init__(slots,timeout,max_queue)
        self.deadlines={}
    def pump(self):
        while self.waiters:
            now=time.monotonic()
            for f in list(self.waiters):
                if self.deadlines[f]<=now:
                    self.waiters.remove(f);self.deadlines.pop(f)
                    if not f.done():f.set_exception(asyncio.TimeoutError())
            if self.active>=self.slots or not self.waiters:break
            f=min(self.waiters,key=lambda x:self.deadlines[x])
            self.waiters.remove(f);self.deadlines.pop(f)
            if not f.done():
                self.active+=1;self.max_active=max(self.max_active,self.active)
                f.set_result(True)
    async def acquire(self,deadline_ms=None):
        budget=self.timeout if deadline_ms is None else min(self.timeout,max(0,float(deadline_ms)/1000))
        if budget<=0:raise asyncio.TimeoutError()
        f=asyncio.get_running_loop().create_future()
        async with self.lock:
            if len(self.waiters)>=self.max_queue:raise QueueFull()
            self.deadlines[f]=time.monotonic()+budget
            self.waiters.append(f);self.pump()
        try:await asyncio.wait_for(asyncio.shield(f),budget)
        except BaseException:
            async with self.lock:
                self.deadlines.pop(f,None)
                if f.done() and not f.cancelled() and f.exception() is None:self.active-=1
                else:
                    with suppress(ValueError):self.waiters.remove(f)
                self.pump()
            raise

class Proxy:
    def __init__(self,upstream,slots,timeout,max_clients,policy="fifo",max_queue=64):
        if policy not in ("fifo","edf"):raise ValueError("unknown policy")
        self.policy=policy
        self.upstream=upstream;self.fifo=(FIFO if policy=="fifo" else EDF)(slots,timeout,max_queue)
        self.clients=asyncio.Semaphore(max_clients);self.retry_after=max(1,math.ceil(timeout))
    async def handle(self,client):
        try:await asyncio.wait_for(self.clients.acquire(),.01)
        except asyncio.TimeoutError:
            await client.send(json.dumps({"type":"error","code":429,"message":"connection capacity exceeded","retry_after_seconds":self.retry_after}))
            await client.close(code=1013);return
        try:
            async with connect(self.upstream,open_timeout=10,max_size=2**23) as backend:
                await self.relay(client,backend)
        finally:self.clients.release()
    async def relay(self,client,backend):
        # Only one flush per session at a time, with concurrent reply forwarding.
        completion=asyncio.Event()
        active=False
        async def inbound():
            nonlocal active
            async for raw in client:
                req=json.loads(raw);typ=req.get("type")
                if typ in ("flush","end_of_stream"):
                    try:await self.fifo.acquire(req.get("deadline_ms"))
                    except QueueFull:
                        await client.send(json.dumps({"type":"error","code":429,"message":"generation queue full","retry_after_seconds":self.retry_after}))
                        continue
                    except asyncio.TimeoutError:
                        await client.send(json.dumps({"type":"error","code":408,"message":"generation queue deadline exceeded","retry_after_seconds":self.retry_after}))
                        continue
                    active=True;completion.clear()
                    try:
                        await backend.send(raw)
                        await completion.wait()
                    finally:
                        if active:
                            active=False;await self.fifo.release()
                else:await backend.send(raw)
        async def outbound():
            nonlocal active
            async for raw in backend:
                msg=json.loads(raw)
                await client.send(raw)
                if active and msg.get("type") in ("flushed","end_of_stream","error"):
                    active=False;await self.fifo.release();completion.set()
        tasks=[asyncio.create_task(inbound()),asyncio.create_task(outbound())]
        try:await asyncio.wait(tasks,return_when=asyncio.FIRST_COMPLETED)
        finally:
            for t in tasks:t.cancel()
            await asyncio.gather(*tasks,return_exceptions=True)
            if active:active=False;await self.fifo.release()

async def main(a):
    if not a.upstream.startswith(("ws://127.0.0.1:","ws://localhost:")):raise SystemExit("local-only upstream")
    proxy=Proxy(a.upstream,a.slots,a.timeout,a.max_clients,a.policy,a.max_queue)
    async with serve(proxy.handle,"127.0.0.1",a.port,max_size=2**23):
        print("B-high+Q ready",flush=True)
        await asyncio.Future()
if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--upstream",default="ws://127.0.0.1:8080/speech/tts")
    p.add_argument("--port",type=int,default=8081)
    p.add_argument("--policy",choices=["fifo","edf"],default="fifo")
    p.add_argument("--slots",type=int,default=3)
    p.add_argument("--timeout",type=float,default=.2)
    p.add_argument("--max-clients",type=int,default=32)
    p.add_argument("--max-queue",type=int,default=64)
    asyncio.run(main(p.parse_args()))
