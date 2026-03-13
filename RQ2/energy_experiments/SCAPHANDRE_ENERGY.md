# Scaphandre Energy Measurement Library

A Python library for scientifically accurate energy measurements using [Scaphandre](https://github.com/hubblo-org/scaphandre).

## Overview

This library wraps Scaphandre to measure energy consumption of processes during experiments. It correctly interprets Scaphandre's power output (microwatts) and integrates over time to compute energy (Joules).

---

## Quick Start

```python
from scaphandre_energy import ScaphandreConfig, run_experiment, save_results, print_summary

config = ScaphandreConfig(
    process_regex=r".*python3.*my_app\.py",
    step_sec=0,
    step_nano=500_000,  # 0.5ms sampling
)

def my_workload():
    # Your code to measure
    pass

results = run_experiment(
    workload=my_workload,
    config=config,
    measure_runs=1000,
    num_trials=10,
)

save_results(results, "results.json")
print_summary(results)
```

---

## Understanding Power vs Energy

| Concept | Unit | Meaning |
|---------|------|---------|
| **Power** | Watts (W) | Rate of energy use at an instant |
| **Energy** | Joules (J) | Total amount consumed over time |

**You cannot "consume" Watts** — Watts is a rate, like speed (km/h).  
**Energy = Power × Time** — Joules is an amount, like distance (km).

This library computes both:
- **Energy (J)**: Total consumption during measurement
- **Power (W)**: Average rate during measurement

---

## Configuration

### `ScaphandreConfig`

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `process_regex` | `str` | *required* | Regex to filter target processes |
| `scaphandre_path` | `str` | `/home/username/scaphandre/target/release/scaphandre` | Path to Scaphandre binary |
| `step_sec` | `int` | `0` | Sampling interval (seconds part) |
| `step_nano` | `int` | `500_000` | Sampling interval (nanoseconds part) |
| `output_file` | `str` | `scaphandre_temp.json` | Temporary output file |

**Effective sampling interval** = `step_sec + step_nano/1e9` seconds

---

## Output Fields Explained

### Per-Trial Results (`TrialResult`)

Each trial produces these metrics:

#### Timing

| Field | Unit | Description |
|-------|------|-------------|
| `duration_sec` | seconds | Wall-clock time for the trial |
| `measure_runs` | count | Number of workload executions |

#### Total Energy (for entire trial)

| Field | Unit | Description |
|-------|------|-------------|
| `total_proc_J` | Joules | **Process energy** — attributed to your target process based on CPU usage |
| `total_pkg_J` | Joules | **CPU package energy** — total CPU socket consumption (includes all processes) |
| `total_dram_J` | Joules | **DRAM energy** — memory subsystem consumption |

#### Energy Per Run

| Field | Unit | Description |
|-------|------|-------------|
| `proc_energy_per_run_J` | Joules | `total_proc_J / measure_runs` |
| `pkg_energy_per_run_J` | Joules | `total_pkg_J / measure_runs` |
| `dram_energy_per_run_J` | Joules | `total_dram_J / measure_runs` |

#### Average Power

| Field | Unit | Description |
|-------|------|-------------|
| `avg_proc_power_W` | Watts | Average power draw by process during trial |
| `avg_pkg_power_W` | Watts | Average CPU package power |
| `avg_dram_power_W` | Watts | Average DRAM power |

#### System-Wide Energy (for entire trial)

| Field | Unit | Description |
|-------|------|-------------|
| `sys_total_host_J` | Joules | **Total system host energy** — entire machine |
| `sys_total_pkg_J` | Joules | **Total CPU package energy** — all sockets |
| `sys_total_dram_J` | Joules | **Total DRAM energy** — all memory |
| `avg_sys_host_power_W` | Watts | Average total system power |
| `avg_sys_pkg_power_W` | Watts | Average total CPU package power |
| `avg_sys_dram_power_W` | Watts | Average total DRAM power |

### Summary Statistics (`ExperimentSummary`)

Aggregated across all trials:

#### Total Energy Per Trial

| Field | Description |
|-------|-------------|
| `mean_total_proc_J` | Mean total process energy per trial |
| `mean_total_pkg_J` | Mean total PKG energy per trial |
| `mean_total_dram_J` | Mean total DRAM energy per trial |
| `stdev_total_proc_J` | Stdev of total process energy per trial |
| `stdev_total_pkg_J` | Stdev of total PKG energy per trial |
| `stdev_total_dram_J` | Stdev of total DRAM energy per trial |

#### Energy Per Run

| Field | Description |
|-------|-------------|
| `mean_*_energy_per_run_J` | Mean energy per workload run |
| `stdev_*_energy_per_run_J` | Standard deviation of energy per run |

#### Power

| Field | Description |
|-------|-------------|
| `mean_*_power_W` | Mean power across trials |
| `stdev_*_power_W` | Standard deviation of power |

#### System-Wide Energy

| Field | Description |
|-------|-------------|
| `mean_sys_host_J` | Mean total system host energy per trial |
| `mean_sys_pkg_J` | Mean total CPU package energy per trial |
| `mean_sys_dram_J` | Mean total DRAM energy per trial |
| `stdev_sys_host_J` | Stdev of system host energy |
| `stdev_sys_pkg_J` | Stdev of system PKG energy |
| `stdev_sys_dram_J` | Stdev of system DRAM energy |

#### System-Wide Power

| Field | Description |
|-------|-------------|
| `mean_sys_host_power_W` | Mean total system host power |
| `mean_sys_pkg_power_W` | Mean total CPU package power |
| `mean_sys_dram_power_W` | Mean total DRAM power |
| `stdev_sys_host_power_W` | Stdev of system host power |
| `stdev_sys_pkg_power_W` | Stdev of system PKG power |
| `stdev_sys_dram_power_W` | Stdev of system DRAM power |

---

## Energy Types Explained

### `proc` — Process Energy

- Energy attributed to your **target process** specifically
- Calculated as: `CPU_package_power × (process_CPU% / 100)`
- This is an **estimate** based on CPU time share

### `pkg` — CPU Package Energy

- Total energy consumed by the **CPU socket** (all cores, L3 cache, integrated GPU)
- Measured directly via Intel RAPL
- Includes energy from ALL processes, not just yours

### `dram` — DRAM Energy

- Energy consumed by the **memory modules**
- Measured via RAPL (if available on your platform)
- System-wide, not per-process

---

## How Energy is Calculated

Scaphandre outputs **power readings** in microwatts (µW), not energy.

This library correctly integrates power over time:

```
Energy = Σ(P_i × Δt_i)

Where:
  P_i = power reading for sample i (converted from µW to W)
  Δt_i = time interval for sample i (from timestamps)
```

For each sample, the interval is computed from consecutive timestamps:
```
Δt_i = timestamp[i] - timestamp[i-1]
```

For the first sample, the configured step duration is used as an estimate.

---

## Example Output

```json
{
  "config": {
    "experiment_label": "Compression Encoding: identity",
    "measure_runs": 5000,
    "num_trials": 20
  },
  "trials": [{
    "trial": 1,
    "duration_sec": 34.03,
    "total_proc_J": 13.998,
    "total_pkg_J": 12.571,
    "total_dram_J": 1.428,
    "proc_energy_per_run_J": 0.0028,
    "avg_proc_power_W": 0.421
  }],
  "summary": {
    "mean_total_proc_J": 14.73,
    "mean_total_pkg_J": 13.35,
    "mean_total_dram_J": 1.40,
    "stdev_total_proc_J": 0.45,
    "stdev_total_pkg_J": 0.40,
    "stdev_total_dram_J": 0.05,
    "mean_proc_energy_per_run_J": 0.00296,
    "stdev_proc_energy_per_run_J": 0.00009,
    "mean_proc_power_W": 0.42,
    "stdev_proc_power_W": 0.006
  }
}
```

---

## API Reference

### `run_experiment()`

```python
run_experiment(
    workload: Callable[[], None],  # Function to measure
    config: ScaphandreConfig,
    measure_runs: int,             # Times to call workload per trial
    num_trials: int,               # Number of trials
    cooldown_sec: float = 120.0,   # Pause between trials
    experiment_label: str = "",
    extra_config: dict = None,
    collect_samples: bool = False, # Include raw samples in output
    startup_delay_sec: float = 0.2,
    target_pid: int = None,        # Filter to specific PID
    verbose: bool = True,
) -> ExperimentResults
```

### `save_results()`

```python
save_results(
    results: ExperimentResults,
    filepath: str,
    include_samples: bool = False,  # Include raw Scaphandre data
)
```

### `print_summary()`

Prints a human-readable summary to stdout.

---

## Best Practices

1. **Use multiple trials** (10-20) for statistical significance
2. **Cooldown between trials** (30s+) to avoid thermal throttling effects
3. **Match process_regex carefully** to avoid measuring wrong processes
4. **Use proc_J for comparisons** — it's specific to your process
5. **Report both mean and stdev** for reproducibility
