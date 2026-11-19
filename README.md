<div align="center">

# Adaptive Telemetry Monitoring in Cloud Microservices

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python: 3.10+](https://img.shields.io/badge/Python-3.10%2B-3776AB.svg?logo=python&logoColor=white)](https://www.python.org/)
[![Kubernetes](https://img.shields.io/badge/Kubernetes-v1.30-326CE5.svg?logo=kubernetes&logoColor=white)](https://kubernetes.io/)
[![Linux Kernel eBPF](https://img.shields.io/badge/Linux_Kernel-eBPF_%2B_cgroups_v2-black.svg?logo=linux&logoColor=white)](https://ebpf.io/)
[![Unit Tests](https://img.shields.io/badge/Unit_Tests-6_Passing-brightgreen.svg?logo=checkmarx&logoColor=white)](tests/)
[![Availability](https://img.shields.io/badge/Availability-99.985%25-success.svg)](results/)

**Dual-loop adaptive telemetry and early reliability assessment for containerized microservices under severe workload surges.**

[Overview](#overview) • [Key Innovations](#key-innovations) • [Architecture](#architecture) • [Empirical Results](#empirical-results) • [Quick Start](#quick-start) • [Citation](#citation)

</div>

---

## Overview

Modern cloud microservices frequently experience sudden Out-of-Memory evictions (`OOMKilled`) and severe tail-latency spikes during abrupt traffic surges. Conventional telemetry stacks (such as Prometheus) employ static scraping intervals of 15 to 30 seconds. Under intense bursts, Java Virtual Machine (JVM) direct memory buffers and request backlogs accumulate in under 15 seconds, rendering static polling purely reactive.

This repository provides an open-science implementation of a **dual-loop adaptive telemetry technology**:
- **Low-Overhead Host Probes**: Linux kernel eBPF probes trace CFS quota exhaustion (`throttle_cfs_rq`) and cgroups v2 memory counters (`memory.current`) at zero context-switch penalty.
- **Continuous Reliability Integration**: A mathematical model calculates the instantaneous failure risk rate $\lambda(t)$ and cumulative reliability index $R(t)$.
- **Logistic Polling Regulation**: Sampling frequency automatically contracts from 15 s down to 1 s upon threat detection, providing a **52-second predictive lead time** before container eviction.

---

## Key Innovations

| Capability | Standard Monitoring (Prometheus 15 s) | Proposed Adaptive Telemetry | Real-World Advantage |
|:---|:---:|:---:|:---|
| **Incident Lead Time** | 0 s (post-mortem alert) | **52 s proactive warning** | Enables graceful traffic draining and new pod warmup |
| **Out-of-Memory Evictions** | 71 events / day | **1 event / day** | **98.6% reduction** in catastrophic outages |
| **CFS Quota Throttling** | 24.8% of runtime | **1.4% of runtime** | 17.7x decrease in CPU starvation |
| **P99 Tail Latency** | 482 ms | **186 ms** | **61.4% latency improvement** under peak traffic |
| **Service Availability** | 99.810% | **99.985%** | +0.175% availability SLA compliance |
| **Mean Time to Recovery** | 48.2 s | **4.1 s** | 11.7x faster automated recovery |
| **CPU Monitoring Cost** | 0.32% | **0.45%** | Under 0.5% CPU overhead during normal operations |

---

## Architecture

The system operates via two decoupled feedback loops:

```
+--------------------------------------------------------------------------+
|                         KUBERNETES CONTAINER NODE                        |
|                                                                          |
|   +-----------------------+              +---------------------------+   |
|   |  JVM Runtime (Spring) |              |  eBPF Kernel Probes       |   |
|   |  Heap / Metaspace     |              |  Linux cgroups v2 CFS     |   |
|   +-----------+-----------+              +-------------+-------------+   |
+---------------|----------------------------------------|-----------------+
                | JMX Telemetry                          | BPF Ring Buffer
                v                                        v
+--------------------------------------------------------------------------+
|                    LOOP 1: ADAPTIVE TELEMETRY AGENT                      |
|                                                                          |
|   - First-order derivative tracking: dM(t)/dt via EMA filter             |
|   - Partial risk decomposition: lambda_oom(t), lambda_cpu(t), lambda_lat |
|   - Verhulst logistic sampling law: Delta_t in [1 s, 15 s]               |
+--------------------------------------------------------------------------+
                |
                v
+--------------------------------------------------------------------------+
|                   LOOP 2: CLUSTER RELIABILITY ANALYZER                   |
|                                                                          |
|   - Integral reliability index: R(t) = exp(-integral lambda(tau) dtau)   |
|   - Predictive Horizon Check: tau_oom <= 60 s                            |
|   - Pre-emptive Scaling: Kubernetes API HPA / Pod Pre-warming            |
+--------------------------------------------------------------------------+
```

---

## Mathematical Foundation

### 1. Instantaneous Failure Risk Superposition

$$\lambda(t) = w_{\mathrm{oom}}\lambda_{\mathrm{oom}}(t) + w_{\mathrm{cpu}}\lambda_{\mathrm{cpu}}(t) + w_{\mathrm{lat}}\lambda_{\mathrm{lat}}(t)$$

where weights satisfy $w_{\mathrm{oom}} + w_{\mathrm{cpu}} + w_{\mathrm{lat}} = 1$. Priority weights are parameterized as $w_{\mathrm{oom}} = 0.50$, $w_{\mathrm{cpu}} = 0.25$, and $w_{\mathrm{lat}} = 0.25$ based on failure criticality.

### 2. Proactive Memory Breach Probability

$$\lambda_{\mathrm{oom}}(t) = \frac{1}{\tau_{\mathrm{lead}}} \cdot \Phi\left( \frac{M(t) + \frac{dM(t)}{dt}\tau_{\mathrm{lead}} - M_{\mathrm{limit}}}{\sigma_M} \right)$$

where $\Phi(\cdot)$ denotes the standard normal cumulative distribution function justified by the Palm-Khinchin Poisson arrival superposition theorem, and $\tau_{\mathrm{lead}} = 60\text{ s}$ represents target pod initialization latency.

### 3. Logistic Sampling Rate Adaptation

$$\Delta t(t) = \Delta t_{\min} + (\Delta t_{\max} - \Delta t_{\min}) \cdot \frac{1}{1 + \exp\left( -k_a (R(t) - R_{\mathrm{safe}}) \right)}$$

where $\Delta t_{\min} = 1\text{ s}$, $\Delta t_{\max} = 15\text{ s}$, safe threshold $R_{\mathrm{safe}} = 0.85$, and slope parameter $k_a = 18$.

---

## Repository Structure

```text
adaptive-telemetry-k8s/
├── adaptive_monitor.py       # Core telemetry engine and O(1) risk analyzer
├── workload_generator.py     # cgroups v2, CFS, and k6 traffic surge simulator
├── run_experiments.py        # End-to-end experiment replication suite
├── requirements.txt          # Python runtime dependencies
├── CITATION.cff              # Machine-readable academic citation metadata
├── LICENSE                   # MIT Open Source License
├── tests/
│   └── test_monitoring.py    # Unit tests for risk, bounds, and O(1) complexity
├── results/
│   └── telemetry_benchmark.csv # Full 24-hour empirical cluster dataset
└── figures/
    ├── fig1_architecture.png              # System block diagram
    ├── fig2_risk_reliability_dynamics.png # Traffic, risk, and R(t) dynamics
    ├── fig3_predictive_lead_time.png      # 52-second lead time benchmark
    └── fig4_polling_tradeoff_pareto.png   # Availability vs CPU overhead
```

---

## Quick Start

### 1. Environment Setup

```bash
# Clone the repository
git clone https://github.com/craddy89/adaptive-telemetry-k8s.git
cd adaptive-telemetry-k8s

# Install required dependencies
pip install -r requirements.txt
```

### 2. Run Automated Verification Tests

```bash
python -m unittest discover -s tests -p "test_*.py"
```
*All 6 unit tests validate numerical convergence, $O(1)$ constant execution time (< 25 $\mu$s per update), and boundary stability.*

### 3. Reproduce All Experimental Figures and Benchmarks

```bash
python run_experiments.py
```
This single command re-runs the full simulation trace, logs CSV results to `results/telemetry_benchmark.csv`, and renders publication-grade figures in `figures/`.

---

## Using the Telemetry Agent in Code

```python
from adaptive_monitor import AdaptiveTelemetryAgent

# Initialize agent with cluster memory limit and SLO target
agent = AdaptiveTelemetryAgent(
    m_limit=950.0,    # Container memory limit (MB)
    tau_lead=60.0,    # Desired proactive lead time (seconds)
    t_slo=200.0,      # Tail-latency objective P99 (ms)
    r_safe=0.85       # Safe threshold initiating sampling acceleration
)

# In your telemetry polling loop:
metrics = agent.update(
    m_curr=680.0,         # Current memory from cgroups v2 (MB)
    nr_throttled=4,       # CFS throttled periods from cpu.stat
    nr_periods=10,        # Total CFS periods in current interval
    t_99=145.0,           # Windowed P99 latency (ms)
    dt_elapsed=15.0       # Seconds elapsed since last sample
)

print(f"Reliability Index R(t): {metrics['reliability_r']:.4f}")
print(f"Next Polling Interval:  {metrics['next_dt']:.1f} seconds")

if metrics["critical_incident"]:
    print("Action Required: Triggering pre-emptive pod autoscaling!")
```

---

## Citation

If this research or open-source software assists your work, please cite it as:

```bibtex
@article{yaksun2026adaptive,
  author    = {Ivan Yu. Yaksun and V. M. Brodkevych},
  title     = {Information Technology for Adaptive Monitoring and Reliability Assessment of Microservices in Cloud Clusters},
  journal   = {Scientific and Technical Publications in Computer Science},
  year      = {2026},
  url       = {https://github.com/craddy89/adaptive-telemetry-k8s}
}
```

---

## License

This project is licensed under the [MIT License](LICENSE).
