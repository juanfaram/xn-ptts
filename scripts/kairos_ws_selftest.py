#!/usr/bin/env python3
"""Protocol-level smoke test using a FAKE WS server. Does not benchmark Phonon."""
import asyncio,base64,json,tempfile
from pathlib import Path
import websockets
import kairos_ws_load as client

async def handler(ws):
    msg=json.loads(await ws.recv())
    assert msg["type"]=="setup"
    await ws.send(json.dumps({"type":"ready","model_name":"fixture",
      "sample_rate":24000,"frame_size":1920,"audio_stream_names":[],
      "text_stream_names":[],"request_id":"fixture"}))
    assert json.loads(await ws.recv())["type"]=="text"
    flush=json.loads(await ws.recv())
    assert flush["type"]=="flush"
    for i in range(2):
        await ws.send(json.dumps({"type":"audio","audio":base64.b64encode(b"test").decode(),
          "start_s":i*.08,"stop_s":(i+1)*.08,"stream_id":0}))
    await ws.send(json.dumps({"type":"flushed","flush_id":flush["flush_id"]}))

async def main():
    async with websockets.serve(handler,"127.0.0.1",0) as server:
        port=server.sockets[0].getsockname()[1]
        args=type("Args",(),{"url":f"ws://127.0.0.1:{port}/speech/tts",
          "clients":2,"idle_seconds":0,"timeout":10,
          "text":"The quick brown fox jumps over the lazy dog."})()
        results=await client.run(args)
        assert len(results)==2
        assert all(r["error"] is None and len(r["audio"])==2 for r in results),results
        assert all(r["ttfa_request_ms"]>=0 for r in results)
        assert all(r["gap_ratios"] for r in results)
        print("WS_CLIENT_PROTOCOL_SELFTEST_PASS (fixture only, no Phonon)")
asyncio.run(main())
