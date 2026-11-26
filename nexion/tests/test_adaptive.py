import unittest
from nexion.adaptive import AdaptiveEngine, Policy, HealthMonitor
class AdaptiveTests(unittest.TestCase):
    def test_insufficient(self):
        self.assertEqual(AdaptiveEngine().assess()["proposal"],"retain_baseline")
    def test_improvement(self):
        e=AdaptiveEngine(Policy(window=4,min_samples=3))
        for i in range(3): e.observe(i,0.8,0.1)
        self.assertEqual(e.assess()["proposal"],"independent_review")
        self.assertFalse(e.assess()["automatic_activation"])
    def test_replay(self):
        e=AdaptiveEngine(); e.observe(1,0.1,0.2); e.reset()
        with self.assertRaises(ValueError): e.observe(1,0.1,0.2)
    def test_nan(self):
        e=AdaptiveEngine()
        with self.assertRaises(ValueError): e.observe(1,float("nan"),0)
        e.observe(1,0,0)
    def test_window(self):
        e=AdaptiveEngine(Policy(window=3,min_samples=2))
        for i in range(10): e.observe(i,0,1)
        self.assertEqual(e.assess()["samples"],3)
        self.assertEqual(e.assess()["proposal"],"retain_baseline")
    def test_breaker(self):
        h=HealthMonitor(2); h.record(False); h.record(False)
        self.assertTrue(h.record(True)["circuit_open"])
        h.reset_after_review(); self.assertFalse(h.status()["circuit_open"])
    def test_policy(self):
        with self.assertRaises(ValueError): Policy(window=2,min_samples=3)

    def test_integer_sample_bounds(self):
        for kwargs in ({"window":128.0}, {"min_samples":64.5},
                       {"window":True}, {"min_samples":"64"}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                Policy(**kwargs)

    def test_boundary_sample_bounds(self):
        for window in (2, 10000):
            self.assertEqual(AdaptiveEngine(Policy(window=window,min_samples=2)).assess()["samples"],0)

    def test_mixed_numeric_losses(self):
        from decimal import Decimal
        e=AdaptiveEngine(Policy(window=2,min_samples=2))
        e.observe(0,Decimal("0.8"),0.1)
        e.observe(1,0.8,Decimal("0.1"))
        self.assertAlmostEqual(e.assess()["mean_gain"],0.7)
        self.assertEqual(e.assess()["proposal"],"independent_review")

    def test_invalid_loss_is_atomic(self):
        e=AdaptiveEngine()
        e.observe(0,0.5,0.5)
        before=e.assess()
        for bad in (True,"0.5",None,10**1000,float("inf"),-0.1,1.1):
            with self.subTest(bad=type(bad).__name__), self.assertRaises(ValueError):
                e.observe(1,0.5,bad)
            self.assertEqual(e.assess(),before)
        e.observe(1,0.5,0.5)
        self.assertEqual(e.assess()["samples"],2)

    def test_policy_rejects_invalid_numeric_types(self):
        for field in ("min_gain", "max_loss"):
            for value in (True, False, "0.5", None, 10**1000, complex(1, 0)):
                with self.subTest(field=field, value_type=type(value).__name__), self.assertRaises(ValueError):
                    Policy(**{field: value})

    def test_policy_rejects_nonfinite_and_underflow(self):
        from decimal import Decimal
        for field in ("min_gain", "max_loss"):
            for value in (float("nan"), float("inf"), Decimal("sNaN"), Decimal("1e-1000"), 0, -1):
                with self.subTest(field=field, value=str(value)), self.assertRaises(ValueError):
                    Policy(**{field: value})

    def test_policy_canonical_float_values(self):
        from decimal import Decimal
        from fractions import Fraction
        p=Policy(window=2,min_samples=2,min_gain=Decimal("0.125"),max_loss=Fraction(1,2))
        self.assertIs(type(p.min_gain),float)
        self.assertIs(type(p.max_loss),float)
        e=AdaptiveEngine(p)
        e.observe(0,0.5,0.25)
        e.observe(1,0.5,0.25)
        self.assertEqual(e.assess()["proposal"],"independent_review")
        self.assertFalse(e.assess()["automatic_activation"])

    def test_policy_numeric_boundaries(self):
        self.assertEqual(Policy(max_loss=1e6,min_gain=1e6).min_gain,1e6)
        for kwargs in ({"max_loss":1e6+1}, {"max_loss":0.1,"min_gain":0.2}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                Policy(**kwargs)
