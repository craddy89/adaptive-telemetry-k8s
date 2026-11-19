"""
Container Workload and Cluster Telemetry Simulator.
Simulates Linux cgroups v2, CFS periodic quota scheduling, JVM memory dynamics,
and k6 request load bursts on a containerized microservice node.
"""

import math
import numpy as np
from typing import Dict, Any, List, Tuple


class ContainerNodeSimulation:
    """
    Simulates a containerized Spring Boot microservice running on a Kubernetes node
    with cgroups v2 resource controllers and Linux CFS quota limits.
    """

    def __init__(
        self,
        m_limit: float = 950.0,
        m_base: float = 510.0,
        cpu_quota_cores: float = 2.0,
        cfs_period_ms: float = 100.0,
        seed: int = 42
    ) -> None:
        """
        Initialize simulated container node environment.

        Args:
            m_limit: Container hard memory limit in MB.
            m_base: Baseline idle memory footprint (JVM heap + Metaspace) in MB.
            cpu_quota_cores: Allocated CPU cores quota via CFS.
            cfs_period_ms: CFS enforcement interval in ms.
            seed: Pseudo-random generator seed for deterministic reproducibility.
        """
        self.m_limit = m_limit
        self.m_base = m_base
        self.cpu_quota_cores = cpu_quota_cores
        self.cfs_period_ms = cfs_period_ms
        self.rng = np.random.RandomState(seed)

    def generate_traffic_profile(self, duration_s: int = 180) -> np.ndarray:
        """
        Generates realistic microservice request rate curve lambda_req(t).
        Simulates nominal traffic (300 req/s), a smooth surge to 2000-2500 req/s,
        and subsequent cooldown back to baseline.
        """
        t = np.arange(0, duration_s, 1.0)
        base_rate = 300.0 + 30.0 * self.rng.randn(len(t))

        # Gaussian / logistic surge centered at t = 95 s with sigma = 20 s
        surge_center = 95.0
        surge_width = 18.0
        surge_amplitude = 1750.0

        surge = surge_amplitude * np.exp(-0.5 * ((t - surge_center) / surge_width) ** 2)
        traffic = np.clip(base_rate + surge, 250.0, 2500.0)
        return traffic

    def simulate_telemetry_trace(
        self,
        duration_s: int = 180
    ) -> List[Dict[str, float]]:
        """
        Generates second-by-second ground truth system dynamics:
        memory consumption M(t), CPU throttling metrics, and P99 tail latency.
        """
        traffic = self.generate_traffic_profile(duration_s)
        trace: List[Dict[str, float]] = []

        current_memory = self.m_base
        cumulative_throttled = 0
        cumulative_periods = 0

        for sec, rps in enumerate(traffic):
            # 1. Memory dynamics:
            # Under elevated traffic, JVM direct buffers and queued requests accumulate.
            # Normal baseline memory drift + surge accumulation
            if sec < 38:
                # Idle / calm state: stationary fluctuation around 512 MB
                noise = self.rng.randn() * 2.5
                current_memory = self.m_base + noise
            elif sec < 110:
                # Surge phase: rapid accumulation of in-flight buffers
                excess_rps = max(0.0, rps - 280.0)
                growth_rate = 0.00042 * (excess_rps ** 1.35)
                noise = self.rng.randn() * 3.0
                current_memory = min(self.m_limit + 40.0, current_memory + growth_rate + noise)
            else:
                # Post-surge or clamped phase
                noise = self.rng.randn() * 4.0
                current_memory = max(self.m_base, current_memory - 4.5 + noise)

            # 2. CFS CPU Quota dynamics:
            # 10 periods per second (since cfs_period = 100 ms)
            periods_in_sec = 10
            # Capacity is 2.0 cores = ~800 req/s nominal processing capacity
            capacity_rps = self.cpu_quota_cores * 400.0
            if rps > capacity_rps:
                throttling_prob = min(0.95, (rps - capacity_rps) / 1200.0)
                throttled_in_sec = int(round(periods_in_sec * throttling_prob))
            else:
                throttled_in_sec = 0 if self.rng.rand() > 0.05 else 1

            cumulative_periods += periods_in_sec
            cumulative_throttled += throttled_in_sec

            # 3. P99 tail latency modeling (M/G/c queueing approximation):
            rho = min(0.98, rps / (capacity_rps + 1e-3))
            if rho < 0.70:
                p99_latency = 35.0 + 15.0 * rho + self.rng.randn() * 3.0
            else:
                p99_latency = 35.0 + 30.0 / (1.0 - rho) + self.rng.randn() * 15.0

            # Amplify latency if throttled
            if throttled_in_sec > 2:
                p99_latency += (throttled_in_sec / periods_in_sec) * 280.0

            trace.append({
                "time": float(sec),
                "rps": float(rps),
                "memory_mb": float(current_memory),
                "nr_throttled": throttled_in_sec,
                "nr_periods": periods_in_sec,
                "p99_latency_ms": float(p99_latency)
            })

        return trace
