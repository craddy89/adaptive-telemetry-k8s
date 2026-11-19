"""
Unit tests for the Adaptive Telemetry Monitoring and Reliability Assessment Module.
"""
import math
import os
import sys
import time
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from adaptive_monitor import AdaptiveTelemetryAgent

class TestAdaptiveTelemetry(unittest.TestCase):
    def setUp(self):
        self.agent = AdaptiveTelemetryAgent(m_limit=950.0, tau_lead=60.0, dt_min=1.0, dt_max=15.0, r_safe=0.85, r_crit=0.70)
    def test_standard_normal_cdf(self):
        self.assertAlmostEqual(self.agent.std_normal_cdf(0.0), 0.5, places=5)
        self.assertAlmostEqual(self.agent.std_normal_cdf(-10.0), 0.0, places=5)
        self.assertAlmostEqual(self.agent.std_normal_cdf(10.0), 1.0, places=5)
    def test_sampling_interval_bounds(self):
        dt_high_r = self.agent.compute_sampling_interval(1.0)
        self.assertTrue(14.0 <= dt_high_r <= 15.0)
        dt_low_r = self.agent.compute_sampling_interval(0.2)
        self.assertTrue(1.0 <= dt_low_r <= 1.5)
    def test_reliability_decay_monotonicity(self):
        r_history = []
        for sec in range(1, 20):
            res = self.agent.update(m_curr=700.0 + sec * 15.0, nr_throttled=8, nr_periods=10, t_99=350.0, dt_elapsed=1.0)
            r_history.append(res["reliability_r"])
        for i in range(1, len(r_history)):
            self.assertLessEqual(r_history[i], r_history[i - 1] + 1e-9)
    def test_asymptotic_constant_time(self):
        start = time.perf_counter()
        for i in range(1000):
            self.agent.update(m_curr=550.0, nr_throttled=1, nr_periods=10, t_99=120.0, dt_elapsed=1.0)
        elapsed = time.perf_counter() - start
        self.assertLess(elapsed / 1000.0 * 1e6, 50.0)

if __name__ == "__main__":
    unittest.main()
