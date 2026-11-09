#!/usr/bin/env python3
"""Compare raw PCM payload through proxy and direct backend using deterministic mock.
Real Phonon equivalence and overhead still require a matched real-server run.
"""
import asyncio,base64,json,statistics,time,unittest
from websockets.asyncio.client import connect
from websockets.asyncio.server import serve
from kairos_fifo_proxy import Proxy

class NonInterference(unittest.IsolatedAsyncioTestCase):
    async def test_byte_identical_and_measure_loopback(self):
        payload=bytes((i*37)%256 for i in range(3200))
        audio=base64.b64encode(payload).decode()
        async def backend(ws):
            async for raw in ws:
                r=json.loads(raw)
                if r["type"]=="setup":
                    await ws.send(json.dumps({"type":"ready","sample_rate":24000}))
                if r["type"]=="flush":
                    await ws.send(json.dumps({"type":"audio","audio":audio,"start_s":0,"stop_s":.08,"stream_id":0}))
                    await ws.send(json.dumps({"type":"flushed","flush_id":r["flush_id"]}))
        async with serve(backend,"127.0.0.1",0) as s:
            port=s.sockets[0].getsockname()[1]
            upstream=f"ws://127.0.0.1:{port}"
            p=Proxy(upstream,3,.2,16)
            async with serve(p.handle,"127.0.0.1",0) as ps:
                proxy=f"ws://127.0.0.1:{ps.sockets[0].getsockname()[1]}"
                async def sample(url):
                    async with connect(url) as ws:
                        await ws.send(json.dumps({"type":"setup"}))
                        self.assertEqual(json.loads(await ws.recv())["type"],"ready")
                        await ws.send(json.dumps({"type":"flush","flush_id":1}))
                        t0=time.perf_counter()
                        msg=json.loads(await ws.recv())
                        latency=(time.perf_counter()-t0)*1000
                        self.assertEqual(json.loads(await ws.recv())["type"],"flushed")
                        return base64.b64decode(msg["audio"]),latency
                direct=[];relayed=[]
                for _ in range(20):
                    d=await sample(upstream);r=await sample(proxy)
                    self.assertEqual(d[0],payload)
                    self.assertEqual(r[0],payload)
                    direct.append(d[1]);relayed.append(r[1])
                overhead=statistics.median(relayed)-statistics.median(direct)
                print(f"MOCK_PCM_BYTES={len(payload)} MOCK_MEDIAN_TTFA_DIRECT_MS={statistics.median(direct):.3f} MOCK_MEDIAN_TTFA_PROXY_MS={statistics.median(relayed):.3f} MOCK_OVERHEAD_MS={overhead:.3f}",flush=True)
                # Mock-only diagnostic; no 2ms production claim from fake backend.
if __name__=="__main__":unittest.main()
