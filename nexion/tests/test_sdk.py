import unittest
from nexion.sdk import select_model, Swarm, Unit, Task

class SDKTests(unittest.TestCase):
    def test_fallback(self):
        self.assertEqual(select_model([1]*100, {"worse":[2]*100})["selected"], "baseline")
    def test_screen(self):
        r=select_model([1]*100, {"better":[0.5]*100})
        self.assertEqual(r["selected"], "better")
        self.assertTrue(r["requires_independent_confirmation"])
    def test_short(self):
        self.assertEqual(select_model([1], {})["reason"], "insufficient_samples")
    def test_invalid_candidate(self):
        self.assertEqual(select_model([1]*100, {"bad":[float("nan")]*100})["selected"], "baseline")
    def test_failover(self):
        s=Swarm([Unit("a",{"x"},90),Unit("b",{"x"},80)],[Task("t","x")])
        s.dispatch(); s.fail_unit("a"); s.dispatch()
        self.assertEqual(s.tasks["t"].assigned_to,"b")
