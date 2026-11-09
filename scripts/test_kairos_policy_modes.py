import asyncio,unittest
from kairos_fifo_proxy import EDF,Proxy

class PolicyTests(unittest.IsolatedAsyncioTestCase):
    async def test_edf_shorter_deadline_goes_first(self):
        q=EDF(1,1);await q.acquire()
        order=[]
        async def waiter(i,ms):
            await q.acquire(ms)
            order.append(i)
            await q.release()
        a=asyncio.create_task(waiter("late",800))
        await asyncio.sleep(.01)
        b=asyncio.create_task(waiter("early",300))
        await asyncio.sleep(.01)
        await q.release()
        await asyncio.gather(a,b)
        self.assertEqual(order,["early","late"])
        self.assertEqual(q.active,0)
    async def test_expired_waiter_not_admitted(self):
        q=EDF(1,.2);await q.acquire()
        t=asyncio.create_task(q.acquire(15))
        await asyncio.sleep(.03)
        await q.release()
        with self.assertRaises(asyncio.TimeoutError):await t
        self.assertEqual(q.active,0)
    async def test_same_transport_modes(self):
        a=Proxy("ws://127.0.0.1:8080",3,.2,8,"fifo")
        b=Proxy("ws://127.0.0.1:8080",3,.2,8,"edf")
        self.assertIs(type(a).relay,type(b).relay)
        self.assertEqual(a.fifo.slots,b.fifo.slots)
if __name__=="__main__":unittest.main()
