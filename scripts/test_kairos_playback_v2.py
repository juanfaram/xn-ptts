import hashlib,json,tempfile,unittest,zipfile
from pathlib import Path
from kairos_playback_v2 import simulate,audit

def trace(n=42,step=20,duration=80,delay_at=None,delay=0):
    t=0;out=[]
    for i in range(n):
        if i:t+=step+(delay if i==delay_at else 0)
        out.append({"ts_recv_monotonic_s":t/1000,"frag_ms":duration})
    return out

class PlaybackTests(unittest.TestCase):
    def test_no_gap(self):self.assertEqual(simulate(trace())["episode_count"],0)
    def test_500ms_at_index_3(self):
        r=simulate(trace(delay_at=3,delay=500))
        self.assertGreater(r["episode_count"],0)
        self.assertGreater(r["total_stall_ms"],0)
    def test_500ms_at_index_35_buffer_sufficient(self):
        r=simulate(trace(delay_at=35,delay=500))
        self.assertEqual(r["episode_count"],0)
        self.assertGreater(r["long_intervals"],0)
    def test_500ms_at_index_35_buffer_insufficient(self):
        r=simulate(trace(step=80,delay_at=35,delay=500))
        self.assertGreater(r["episode_count"],0)
    def test_one_ms_below_threshold(self):
        f=trace(n=5)
        f[1]["ts_recv_monotonic_s"]=0.079
        for i in range(2,5):f[i]["ts_recv_monotonic_s"]=0.079+(i-1)*.02
        self.assertEqual(simulate(f)["episode_count"],0)
    def test_strict_manifest_and_explicit_legacy(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/"test.zip";data=b"[]"
            m=json.dumps({"sha256_files":{"k1-r1-ratios.json":hashlib.sha256(data).hexdigest()}}).encode()
            def make(raw):
                with zipfile.ZipFile(p,"w") as z:
                    z.writestr("manifest.json",raw)
                    z.writestr("k1-r1-ratios.json",data)
            make(m+b"\n")
            self.assertFalse(audit(p)["legacy_manifest"])
            make(m+b"\\n")
            with self.assertRaises(json.JSONDecodeError):audit(p)
            self.assertTrue(audit(p,allow_legacy=True)["legacy_manifest"])
            make(m+b"BROKEN")
            with self.assertRaises(json.JSONDecodeError):audit(p,allow_legacy=True)

if __name__=="__main__":unittest.main()
