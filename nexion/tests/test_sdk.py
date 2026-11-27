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

    def test_sample_policy_requires_integer(self):
        for bad in (True, 2.5, float("nan"), float("inf"), "2", None):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                select_model([1, 1], {"better": [0, 0]}, min_samples=bad)

    def test_gain_policy_rejects_bad_values(self):
        from decimal import Decimal
        for bad in (True, "0.1", None, 10**1000, Decimal("1e-1000"), float("nan")):
            with self.subTest(bad=type(bad).__name__), self.assertRaises(ValueError):
                select_model([1, 1], {"better": [0, 0]}, min_samples=2, min_gain=bad)

    def test_mixed_numeric_losses(self):
        from decimal import Decimal
        from fractions import Fraction
        r=select_model([Decimal("0.8"), Fraction(4,5)], {"better": [0.1, Decimal("0.1")]}, min_samples=2)
        self.assertEqual(r["selected"], "better")
        self.assertAlmostEqual(r["gain"], 0.7)

    def test_invalid_baseline_raises_value_error(self):
        for bad in (True, "1", None, 10**1000, float("inf")):
            with self.subTest(bad=type(bad).__name__), self.assertRaises(ValueError):
                select_model([1, bad], {}, min_samples=2)

    def test_bad_candidate_does_not_hide_valid_candidate(self):
        for bad in (False, "0", None, 10**1000, float("inf")):
            with self.subTest(bad=type(bad).__name__):
                r=select_model([1, 1], {"bad": [bad, 0], "good": [0.5, 0.5]}, min_samples=2)
                self.assertEqual(r["selected"], "good")

    def test_finite_mean_when_sum_overflows(self):
        from math import isfinite
        r=select_model([1e308, 1e308], {"better": [0, 0]}, min_samples=2)
        self.assertTrue(isfinite(r["gain"]))
        self.assertEqual(r["gain"], 1e308)

    def test_tie_break_and_confirmation(self):
        r=select_model([1, 1], {"z": [0, 0], "a": [0, 0]}, min_samples=2)
        self.assertEqual(r["selected"], "a")
        self.assertTrue(r["requires_independent_confirmation"])
