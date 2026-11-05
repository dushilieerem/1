"""V5 P0 statistics: K-corrected threshold and Newey-West t."""
import math
import unittest

import numpy as np

from services.quant_factor.metrics import default_lags, newey_west_t, significance, threshold


def independent_nw(values, lags):
    """Separate numpy implementation of the same Bartlett-kernel HAC mean t."""
    x = np.asarray(values, dtype=float)
    n = x.size
    errors = x - x.mean()
    long_run = float(errors @ errors) / n
    for lag in range(1, lags + 1):
        covariance = float(errors[lag:] @ errors[:-lag]) / n
        long_run += 2.0 * (1.0 - lag / (lags + 1.0)) * covariance
    return float(x.mean() / math.sqrt(long_run / n))


class ThresholdTest(unittest.TestCase):
    def test_bonferroni_values(self):
        expected = {1: 1.959964, 5: 2.575829, 10: 2.807034, 20: 3.023341}
        for k, value in expected.items():
            self.assertAlmostEqual(threshold(k), value, places=6)

    def test_threshold_grows_with_k(self):
        values = [threshold(k) for k in range(1, 30)]
        self.assertTrue(all(a <= b for a, b in zip(values, values[1:])))

    def test_invalid_k(self):
        for value in (0, -1, 1.5, True, "5"):
            with self.assertRaises(ValueError):
                threshold(value)


class NeweyWestTest(unittest.TestCase):
    def series(self, n=120):
        return [0.03 + 0.02 * math.sin(i / 3.0) + 0.004 * (((i * 37) % 11) - 5) / 5
                for i in range(n)]

    def test_matches_independent_implementation(self):
        values = self.series()
        for lags in (0, 1, 5, 12):
            result = newey_west_t(values, lags=lags)
            self.assertAlmostEqual(result["t"], independent_nw(values, lags), places=10)
            self.assertEqual(result["n"], len(values))
            self.assertEqual(result["lags"], lags)

    def test_default_lag_rule(self):
        self.assertEqual(default_lags(100), 4)
        self.assertEqual(default_lags(2), 1)
        self.assertEqual(newey_west_t(self.series(101))["lags"], default_lags(101))

    def test_missing_values_are_dropped(self):
        values = self.series(60)
        values[3] = None
        values[9] = float("nan")
        result = newey_west_t(values, lags=2)
        self.assertEqual(result["n"], 58)

    def test_constant_series_rejected(self):
        with self.assertRaisesRegex(ValueError, "方差"):
            newey_west_t([0.01] * 20)
        with self.assertRaisesRegex(ValueError, "少于 2"):
            newey_west_t([0.01])
        with self.assertRaises(ValueError):
            newey_west_t([0.01, 0.02], lags=5)


class SignificanceTest(unittest.TestCase):
    def test_direction_and_k(self):
        values = [0.05 + 0.003 * math.sin(i / 2.0) for i in range(80)]
        positive = significance(values, 1, direction="positive", min_ic=0.02, lags=3)
        negative = significance(values, 1, direction="negative", min_ic=0.02, lags=3)
        self.assertTrue(positive["passed"])
        self.assertFalse(negative["passed"])
        self.assertGreater(positive["signed_t"], 0)
        self.assertLess(negative["signed_t"], 0)
        self.assertAlmostEqual(positive["threshold"], threshold(1), places=12)

    def test_threshold_changes_verdict(self):
        # t ~= 2.62 with 4 lags: passes at K=5 (2.576), fails at K=12 (2.865).
        values = [0.03 + 0.12 * math.sin(i / 1.7) for i in range(120)]
        self.assertTrue(significance(values, 5, min_ic=0.02, lags=4)["passed"])
        self.assertFalse(significance(values, 12, min_ic=0.02, lags=4)["passed"])


if __name__ == "__main__":
    unittest.main()
