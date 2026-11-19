"""
Adaptive Telemetry Monitoring and Reliability Assessment Module.
Implements dual-loop telemetry, stochastic failure risk modeling,
integral reliability assessment, and logistic adaptive sampling.
"""

import math
from typing import Tuple, Dict, Any, List


class AdaptiveTelemetryAgent:
    """
    Adaptive telemetry agent computing instantaneous failure risk rate lambda(t),
    integral reliability index R(t), and dynamic polling interval Delta_t(t).
    Operates with O(1) time complexity and O(1) space complexity per telemetry cycle.
    """

    def __init__(
        self,
        m_limit: float = 950.0,
        tau_lead: float = 60.0,
        sigma_m: float = 25.0,
        t_slo: float = 200.0,
        theta_th: float = 0.05,
        w_oom: float = 0.50,
        w_cpu: float = 0.25,
        w_lat: float = 0.25,
        alpha_th: float = 0.15,
        gamma_lat: float = 0.10,
        dt_min: float = 1.0,
        dt_max: float = 15.0,
        r_safe: float = 0.85,
        r_crit: float = 0.70,
        k_a: float = 18.0,
        ema_alpha: float = 0.30
    ) -> None:
        """
        Initialize the adaptive telemetry agent with operational parameters.

        Args:
            m_limit: Memory constraint threshold in megabytes (MB).
            tau_lead: Desired proactive lead time target in seconds.
            sigma_m: Standard deviation of short-term memory fluctuations in MB.
            t_slo: Service Level Objective for 99th-percentile response time in ms.
            theta_th: Tolerable CPU quota throttling ratio threshold (default 5%).
            w_oom: Weight assigned to memory exhaustion risk.
            w_cpu: Weight assigned to CPU quota throttling risk.
            w_lat: Weight assigned to tail latency degradation risk.
            alpha_th: Scaling penalty coefficient for CPU throttling.
            gamma_lat: Scaling penalty coefficient for latency violations.
            dt_min: Minimum telemetry polling interval in seconds.
            dt_max: Maximum telemetry polling interval in seconds.
            r_safe: Safe reliability boundary initiating frequency adaptation.
            r_crit: Critical reliability boundary initiating container migration.
            k_a: Logistic slope sensitivity parameter.
            ema_alpha: Exponential moving average smoothing coefficient for dM/dt.
        """
        # Normalization verification
        weight_sum = w_oom + w_cpu + w_lat
        self.w_oom = w_oom / weight_sum
        self.w_cpu = w_cpu / weight_sum
        self.w_lat = w_lat / weight_sum

        self.m_limit = float(m_limit)
        self.tau_lead = float(tau_lead)
        self.sigma_m = float(sigma_m)
        self.t_slo = float(t_slo)
        self.theta_th = float(theta_th)
        self.alpha_th = float(alpha_th)
        self.gamma_lat = float(gamma_lat)

        self.dt_min = float(dt_min)
        self.dt_max = float(dt_max)
        self.r_safe = float(r_safe)
        self.r_crit = float(r_crit)
        self.k_a = float(k_a)
        self.ema_alpha = float(ema_alpha)

        # Internal state tracking
        self.current_r = 1.0
        self.prev_memory: float = 0.0
        self.d_memory_dt: float = 0.0
        self.has_prev_memory = False
        self.cumulative_hazard = 0.0
        self.incident_triggered = False

    @staticmethod
    def std_normal_cdf(x: float) -> float:
        """
        Computes the standard normal cumulative distribution function Phi(x).
        Uses the analytical error function erf(x / sqrt(2)).
        """
        return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))

    def compute_memory_risk(self, m_curr: float, dm_dt: float) -> float:
        """
        Computes partial memory exhaustion risk lambda_oom(t) via first-order
        Taylor projection over lead horizon tau_lead against threshold m_limit.
        Formula (2): lambda_oom = (1 / tau_lead) * Phi((M + (dM/dt)*tau - M_limit) / sigma_m)
        """
        projected_m = m_curr + dm_dt * self.tau_lead
        z = (projected_m - self.m_limit) / max(1e-3, self.sigma_m)
        phi_val = self.std_normal_cdf(z)
        return (1.0 / max(1e-3, self.tau_lead)) * phi_val

    def compute_cpu_risk(self, nr_throttled: int, nr_periods: int) -> float:
        """
        Computes partial CPU quota throttling risk lambda_cpu(t).
        Formula (3): lambda_cpu = alpha_th * max(0, (nr_throttled / nr_periods) - theta_th)
        """
        if nr_periods <= 0:
            return 0.0
        throttling_ratio = float(nr_throttled) / float(nr_periods)
        excess = max(0.0, throttling_ratio - self.theta_th)
        return self.alpha_th * excess

    def compute_latency_risk(self, t_99: float) -> float:
        """
        Computes partial tail-latency degradation risk lambda_lat(t).
        Formula (4): lambda_lat = gamma_lat * max(0, (T_99 - T_SLO) / T_SLO)
        """
        if self.t_slo <= 0:
            return 0.0
        relative_excess = max(0.0, (t_99 - self.t_slo) / self.t_slo)
        return self.gamma_lat * relative_excess

    def compute_sampling_interval(self, r_val: float) -> float:
        """
        Computes dynamic polling interval Delta_t(t) via Verhulst logistic curve.
        Formula (7): Delta_t = Delta_min + (Delta_max - Delta_min) / (1 + exp(-k_a * (R - R_safe)))
        """
        arg = -self.k_a * (r_val - self.r_safe)
        # Protect against float overflow in exp
        if arg > 60.0:
            logistic_sigmoid = 0.0
        elif arg < -60.0:
            logistic_sigmoid = 1.0
        else:
            logistic_sigmoid = 1.0 / (1.0 + math.exp(arg))

        return self.dt_min + (self.dt_max - self.dt_min) * logistic_sigmoid

    def update(
        self,
        m_curr: float,
        nr_throttled: int,
        nr_periods: int,
        t_99: float,
        dt_elapsed: float
    ) -> Dict[str, Any]:
        """
        Executes one iteration of the adaptive telemetry monitoring cycle.
        Runs in strictly O(1) time and updates reliability metrics.

        Returns dictionary with evaluated parameters, risk metrics, and control signals.
        """
        dt_safe = max(0.1, dt_elapsed)

        # 1. Update derivative of memory consumption using EMA filter
        if not self.has_prev_memory:
            raw_slope = 0.0
            self.d_memory_dt = 0.0
            self.has_prev_memory = True
        else:
            raw_slope = (m_curr - self.prev_memory) / dt_safe
            self.d_memory_dt = (
                self.ema_alpha * raw_slope + (1.0 - self.ema_alpha) * self.d_memory_dt
            )
        self.prev_memory = m_curr

        # 2. Compute partial risk components
        lambda_oom = self.compute_memory_risk(m_curr, self.d_memory_dt)
        lambda_cpu = self.compute_cpu_risk(nr_throttled, nr_periods)
        lambda_lat = self.compute_latency_risk(t_99)

        # 3. Aggregate total failure risk rate lambda(t) (Formula 1)
        lambda_total = (
            self.w_oom * lambda_oom +
            self.w_cpu * lambda_cpu +
            self.w_lat * lambda_lat
        )

        # 4. Integrate reliability index R(t) (Formula 5)
        # Discrete step: R(t) = R(t - dt) * exp(-lambda_total * dt)
        step_hazard = lambda_total * dt_safe
        self.cumulative_hazard += step_hazard
        self.current_r = math.exp(-self.cumulative_hazard)
        # Bound numerical stability
        self.current_r = max(0.0, min(1.0, self.current_r))

        # 5. Compute adaptive sampling interval Delta_t(t) (Formula 7)
        next_dt = self.compute_sampling_interval(self.current_r)

        # 6. Check alert boundaries
        adaptation_active = (self.current_r < self.r_safe)
        
        # Calculate projected time to OOM
        if self.d_memory_dt > 0.1:
            time_to_oom = (self.m_limit - m_curr) / self.d_memory_dt
        else:
            time_to_oom = float('inf')

        critical_incident = (
            (self.current_r < self.r_crit) or
            (0.0 < time_to_oom <= self.tau_lead)
        )
        if critical_incident and not self.incident_triggered:
            self.incident_triggered = True

        return {
            "m_curr": m_curr,
            "d_memory_dt": self.d_memory_dt,
            "lambda_oom": lambda_oom,
            "lambda_cpu": lambda_cpu,
            "lambda_lat": lambda_lat,
            "lambda_total": lambda_total,
            "reliability_r": self.current_r,
            "next_dt": next_dt,
            "adaptation_active": adaptation_active,
            "time_to_oom": time_to_oom,
            "critical_incident": critical_incident
        }

    def reset(self) -> None:
        """Reset internal trajectory state for fresh benchmark run."""
        self.current_r = 1.0
        self.prev_memory = 0.0
        self.d_memory_dt = 0.0
        self.has_prev_memory = False
        self.cumulative_hazard = 0.0
        self.incident_triggered = False
