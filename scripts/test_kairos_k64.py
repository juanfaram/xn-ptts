import asyncio,unittest
from kairos_fifo_proxy import FIFO,EDF,QueueFull,Proxy

class CommercialQueueTests(unittest.IsolatedAsyncioTestCase):
    async def test_k64_both_policies(self):
        for typ in (FIFO,EDF):
            q=typ(1,2,64)
            await q.acquire()
            tasks=[]
            for _ in range(64):
                tasks.append(asyncio.create_task(q.acquire(1500)))
                await asyncio.sleep(0)
            self.assertEqual(len(q.waiters),64)
            with self.assertRaises(QueueFull):
                await q.acquire(1500)
            for t in tasks:t.cancel()
            await asyncio.gather(*tasks,return_exceptions=True)
            await q.release()
            self.assertEqual(q.active,0)
            self.assertEqual(len(q.waiters),0)
    async def test_capacity_identical(self):
        b=Proxy("ws://127.0.0.1:8080",3,.2,100,"fifo",64)
        c=Proxy("ws://127.0.0.1:8080",3,.2,100,"edf",64)
        self.assertEqual(b.fifo.max_queue,c.fifo.max_queue)
        self.assertEqual(b.fifo.slots,c.fifo.slots)
        self.assertEqual(b.retry_after,c.retry_after)
if __name__=="__main__":unittest.main()
