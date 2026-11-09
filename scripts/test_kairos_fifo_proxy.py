#!/usr/bin/env python3
"""Unit and protocol integration tests; fake backend, no model download."""
import asyncio,json,unittest
from websockets.asyncio.client import connect
from websockets.asyncio.server import serve
from kairos_fifo_proxy import FIFO,Proxy

class Tests(unittest.IsolatedAsyncioTestCase):
    async def test_fifo_limit_order_and_timeout(self):
        q=FIFO(1,.03)
        await q.acquire()
        with self.assertRaises(asyncio.TimeoutError):await q.acquire()
        self.assertEqual(q.active,1)
        await q.release()
        self.assertEqual(q.active,0)
        await q.acquire();await q.release()
    async def test_fifo_cancellation_no_leak(self):
        q=FIFO(1,1)
        await q.acquire()
        t=asyncio.create_task(q.acquire());await asyncio.sleep(.01);t.cancel()
        with self.assertRaises(asyncio.CancelledError):await t
        await q.release()
        self.assertEqual(q.active,0)
    async def test_fifo_strict_order(self):
        q=FIFO(1,1)
        await q.acquire()
        order=[]
        async def waiter(i):
            await q.acquire()
            order.append(i)
            await q.release()
        tasks=[]
        for i in range(4):
            tasks.append(asyncio.create_task(waiter(i)))
            await asyncio.sleep(.002)
        await q.release()
        await asyncio.gather(*tasks)
        self.assertEqual(order,[0,1,2,3])
        self.assertEqual(q.active,0)

    async def test_timeout_does_not_release_others_permit(self):
        q=FIFO(3,.01)
        for _ in range(3):await q.acquire()
        with self.assertRaises(asyncio.TimeoutError):await q.acquire()
        self.assertEqual(q.active,3)
        for _ in range(3):await q.release()
        self.assertEqual(q.active,0)

    async def test_proxy_queues_flush_and_preserves_audio(self):
        concurrent=0;maximum=0
        async def backend(ws):
            nonlocal concurrent,maximum
            async for raw in ws:
                req=json.loads(raw);typ=req["type"]
                if typ=="setup":await ws.send(json.dumps({"type":"ready","sample_rate":24000}))
                elif typ=="flush":
                    concurrent+=1;maximum=max(maximum,concurrent)
                    await asyncio.sleep(.04)
                    await ws.send(json.dumps({"type":"audio","audio":"AA==","start_s":0,"stop_s":.08,"stream_id":0}))
                    await ws.send(json.dumps({"type":"flushed","flush_id":req["flush_id"]}))
                    concurrent-=1
        async with serve(backend,"127.0.0.1",0) as s:
            port=s.sockets[0].getsockname()[1]
            p=Proxy(f"ws://127.0.0.1:{port}",1,.5,8)
            async with serve(p.handle,"127.0.0.1",0) as ps:
                pp=ps.sockets[0].getsockname()[1]
                async def client(i):
                    async with connect(f"ws://127.0.0.1:{pp}") as ws:
                        await ws.send(json.dumps({"type":"setup"}));assert json.loads(await ws.recv())["type"]=="ready"
                        await ws.send(json.dumps({"type":"flush","flush_id":i}))
                        return [json.loads(await ws.recv())["type"] for _ in range(2)]
                got=await asyncio.gather(*(client(i) for i in range(3)))
                self.assertEqual(got,[["audio","flushed"]]*3)
                self.assertEqual(maximum,1)
                self.assertEqual(p.fifo.max_active,1)
                self.assertEqual(p.fifo.active,0)
    async def test_queue_timeout_structured(self):
        async def backend(ws):
            async for raw in ws:
                r=json.loads(raw)
                if r["type"]=="flush":
                    await asyncio.sleep(.1)
                    await ws.send(json.dumps({"type":"flushed","flush_id":r["flush_id"]}))
        async with serve(backend,"127.0.0.1",0) as s:
            port=s.sockets[0].getsockname()[1];p=Proxy(f"ws://127.0.0.1:{port}",1,.02,4)
            async with serve(p.handle,"127.0.0.1",0) as ps:
                pp=ps.sockets[0].getsockname()[1]
                async def client(i):
                    async with connect(f"ws://127.0.0.1:{pp}") as ws:
                        await ws.send(json.dumps({"type":"flush","flush_id":i}))
                        return json.loads(await ws.recv())
                a,b=await asyncio.gather(client(1),client(2))
                self.assertEqual(sorted([a["type"],b["type"]]),["error","flushed"])
                self.assertIn("retry_after_seconds",a if a["type"]=="error" else b)
                self.assertEqual(p.fifo.active,0)
if __name__=="__main__":unittest.main()
