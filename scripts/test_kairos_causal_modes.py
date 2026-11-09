import asyncio,unittest
from kairos_fifo_proxy import FIFO,FIFOExpire,EDF,QueueFull
class TestPolicyCausality(unittest.IsolatedAsyncioTestCase):
    async def test_order(self):
        for typ,expected in [(FIFO,["long","short"]),(FIFOExpire,["long","short"]),(EDF,["short","long"])]:
            q=typ(1,1,64);await q.acquire()
            got=[]
            async def worker(label,deadline):
                await q.acquire(deadline)
                got.append(label)
                await q.release()
            a=asyncio.create_task(worker("long",900))
            await asyncio.sleep(.01)
            b=asyncio.create_task(worker("short",500))
            await asyncio.sleep(.01)
            await q.release()
            await asyncio.gather(a,b)
            self.assertEqual(got,expected)
            self.assertEqual(q.active,0)
    async def test_expiry_not_admitted(self):
        for typ in (FIFO,FIFOExpire,EDF):
            q=typ(1,.5,64);await q.acquire()
            t=asyncio.create_task(q.acquire(10))
            await asyncio.sleep(.04)
            await q.release()
            with self.assertRaises(asyncio.TimeoutError):await t
            self.assertEqual(q.active,0)
    async def test_full_queue(self):
        for typ in (FIFO,FIFOExpire,EDF):
            q=typ(1,1,2);await q.acquire()
            t1=asyncio.create_task(q.acquire());await asyncio.sleep(0)
            t2=asyncio.create_task(q.acquire());await asyncio.sleep(0)
            with self.assertRaises(QueueFull):await q.acquire()
            t1.cancel();t2.cancel()
            await asyncio.gather(t1,t2,return_exceptions=True)
            await q.release()
            self.assertEqual(q.active,0)
if __name__=="__main__":unittest.main()
