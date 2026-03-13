#!/usr/bin/env python3
"""
Scaphandre Energy Measurement Library

A reusable library for Scaphandre-based energy measurements.
Provides consistent JSON output and reduces code repetition across experiments.

Units:
- Energy: Joules (J)
- Power: Watts (W) - averaged over measurement period
- Raw Scaphandre output: microwatts (µW) - power, not energy
"""

from __future__ import annotations

import json
import os
import subprocess
import statistics as stats
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Callable, Optional, Any


@dataclass
class ScaphandreConfig:
    """Configuration for Scaphandre energy measurement."""
    
    process_regex: str
    """Regex to filter processes to measure."""
    
    scaphandre_path: str = "/home/username/scaphandre/target/release/scaphandre"
    """Path to scaphandre binary."""
    
    step_sec: int = 0
    """Sampling step in seconds."""
    
    step_nano: int = 500_000
    """Additional sampling step in nanoseconds (added to step_sec)."""
    
    output_file: str = "scaphandre_temp.json"
    """Temporary output file for Scaphandre JSON data."""


@dataclass
class EnergyMeasurement:
    """Energy and power measurement results.
    
    Energy (Joules) and average power (Watts) are calculated consistently
    using sampling-based timing (N samples × step_duration).
    """
    
    # Per-process energy in Joules
    proc_J: float = 0.0
    """Process energy consumption (Joules)."""
    
    pkg_J: float = 0.0
    """CPU package energy attributed to process (Joules)."""
    
    dram_J: float = 0.0
    """DRAM energy attributed to process (Joules)."""
    
    # Per-process average power in Watts
    proc_W: float = 0.0
    """Process average power (Watts)."""
    
    pkg_W: float = 0.0
    """CPU package power attributed to process (Watts)."""
    
    dram_W: float = 0.0
    """DRAM power attributed to process (Watts)."""
    
    # System-wide energy in Joules
    sys_host_J: float = 0.0
    """System-wide total host energy (Joules)."""
    
    sys_pkg_J: float = 0.0
    """System-wide CPU package energy (Joules)."""
    
    sys_dram_J: float = 0.0
    """System-wide DRAM energy (Joules)."""
    
    # System-wide average power in Watts
    sys_host_W: float = 0.0
    """System-wide total host power (Watts)."""
    
    sys_pkg_W: float = 0.0
    """System-wide CPU package power (Watts)."""
    
    sys_dram_W: float = 0.0
    """System-wide DRAM power (Watts)."""
    
    # Sampling metadata
    num_samples: int = 0
    """Number of Scaphandre samples."""
    
    sampling_duration_sec: float = 60.0
    """Total sampling duration (num_samples × step_duration)."""


@dataclass 
class TrialResult:
    """Result of a single measurement trial."""
    
    trial: int
    """Trial index (1-based)."""
    
    duration_sec: float
    """Duration of the trial in seconds."""
    
    measure_runs: int
    """Number of workload runs in this trial."""
    
    # Total per-process energy (Joules)
    total_proc_J: float
    total_pkg_J: float
    total_dram_J: float
    
    # Energy per run (Joules)
    proc_energy_per_run_J: float
    pkg_energy_per_run_J: float
    dram_energy_per_run_J: float
    
    # Per-process average power (Watts)
    avg_proc_power_W: float
    avg_pkg_power_W: float
    avg_dram_power_W: float
    
    # System-wide total energy (Joules)
    sys_total_host_J: float = 0.0
    sys_total_pkg_J: float = 0.0
    sys_total_dram_J: float = 0.0
    
    # System-wide average power (Watts)
    avg_sys_host_power_W: float = 0.0
    avg_sys_pkg_power_W: float = 0.0
    avg_sys_dram_power_W: float = 0.0
    
    # Net energy above idle baseline (Joules) - only set if baseline measured
    net_sys_host_J: Optional[float] = None
    net_sys_pkg_J: Optional[float] = None
    net_sys_dram_J: Optional[float] = None
    
    # Net energy per run above baseline (Joules)
    net_sys_host_per_run_J: Optional[float] = None
    net_sys_pkg_per_run_J: Optional[float] = None
    net_sys_dram_per_run_J: Optional[float] = None
    
    # Optional per-step samples
    samples: Optional[list[dict]] = None


@dataclass
class BaselineMeasurement:
    """Idle baseline power measurement results."""
    
    # Idle power (Watts)
    idle_host_power_W: float
    idle_pkg_power_W: float
    idle_dram_power_W: float
    
    # Measurement metadata
    duration_sec: float
    num_samples: int


@dataclass
class ExperimentSummary:
    """Statistical summary of experiment results."""
    
    # Mean total energy per trial (Joules)
    mean_total_proc_J: float
    mean_total_pkg_J: float
    mean_total_dram_J: float
    
    # Stdev total energy per trial (Joules)
    stdev_total_proc_J: float
    stdev_total_pkg_J: float
    stdev_total_dram_J: float
    
    # Mean energy per run (Joules)
    mean_proc_energy_per_run_J: float
    mean_pkg_energy_per_run_J: float
    mean_dram_energy_per_run_J: float
    
    # Stdev energy per run (Joules)
    stdev_proc_energy_per_run_J: float
    stdev_pkg_energy_per_run_J: float
    stdev_dram_energy_per_run_J: float
    
    # Mean power (Watts)
    mean_proc_power_W: float
    mean_pkg_power_W: float
    mean_dram_power_W: float
    
    # Stdev power (Watts)
    stdev_proc_power_W: float
    stdev_pkg_power_W: float
    stdev_dram_power_W: float
    
    # Mean system-wide total energy per trial (Joules)
    mean_sys_host_J: float = 0.0
    mean_sys_pkg_J: float = 0.0
    mean_sys_dram_J: float = 0.0
    
    # Stdev system-wide total energy per trial (Joules)
    stdev_sys_host_J: float = 0.0
    stdev_sys_pkg_J: float = 0.0
    stdev_sys_dram_J: float = 0.0
    
    # Mean system-wide power (Watts)
    mean_sys_host_power_W: float = 0.0
    mean_sys_pkg_power_W: float = 0.0
    mean_sys_dram_power_W: float = 0.0
    
    # Stdev system-wide power (Watts)
    stdev_sys_host_power_W: float = 0.0
    stdev_sys_pkg_power_W: float = 0.0
    stdev_sys_dram_power_W: float = 0.0
    
    # Net energy above baseline (Joules) - only present if baseline measured
    mean_net_sys_host_J: Optional[float] = None
    mean_net_sys_pkg_J: Optional[float] = None
    mean_net_sys_dram_J: Optional[float] = None
    stdev_net_sys_host_J: Optional[float] = None
    stdev_net_sys_pkg_J: Optional[float] = None
    stdev_net_sys_dram_J: Optional[float] = None
    
    # Net energy per run above baseline (Joules)
    mean_net_sys_host_per_run_J: Optional[float] = None
    mean_net_sys_pkg_per_run_J: Optional[float] = None
    mean_net_sys_dram_per_run_J: Optional[float] = None
    stdev_net_sys_host_per_run_J: Optional[float] = None
    stdev_net_sys_pkg_per_run_J: Optional[float] = None
    stdev_net_sys_dram_per_run_J: Optional[float] = None


@dataclass
class ExperimentResults:
    """Complete experiment results with config, trials, and summary."""
    
    config: dict[str, Any]
    """Experiment configuration."""
    
    trials: list[TrialResult]
    """List of trial results."""
    
    summary: ExperimentSummary
    """Aggregated statistics."""
    
    baseline: Optional[BaselineMeasurement] = None
    """Idle baseline measurement (if measured)."""


def parse_scaphandre_json(content: str) -> list[dict]:
    """
    Parse Scaphandre JSON output.
    
    Handles both:
    - Concatenated JSON objects: {}{}{} (from streaming output)
    - JSON array: [...] (from standard output)
    
    Args:
        content: Raw JSON content from Scaphandre output file
        
    Returns:
        List of Scaphandre report entries
    """
    content = content.strip()
    if not content:
        return []
    
    # Try parsing as JSON array first
    if content.startswith('['):
        try:
            data = json.loads(content)
            return data if isinstance(data, list) else [data]
        except json.JSONDecodeError:
            # If standard parsing fails (e.g. truncated), fall back to robust parsing
            # We strip the starting bracket to help the streaming parser
            pass
    
    # Parse concatenated JSON objects or inside an array
    entries = []
    decoder = json.JSONDecoder()
    
    # If it looked like an array, skip the opening bracket
    idx = 1 if content.startswith('[') else 0
    
    while idx < len(content):
        remaining = content[idx:].lstrip()
        if not remaining:
            break
            
        # Skip commas between array elements
        if remaining.startswith(','):
            idx += len(content[idx:]) - len(remaining) + 1
            continue
            
        # Skip closing bracket
        if remaining.startswith(']'):
            idx += len(content[idx:]) - len(remaining) + 1
            break
            
        try:
            obj, end_idx = decoder.raw_decode(remaining)
            entries.append(obj)
            idx += len(content[idx:]) - len(remaining) + end_idx
        except json.JSONDecodeError:
            # If we can't parse the next object, we stop (handling truncation)
            break
    
    return entries


def aggregate_energy(
    entries: list[dict], 
    step_duration_sec: float,
    target_pid: Optional[int] = None,
) -> EnergyMeasurement:
    """
    Aggregate energy from Scaphandre entries.
    
    IMPORTANT: Scaphandre outputs POWER in microwatts (µW), not energy.
    Each power reading P_i is computed as ΔE/Δt using actual timestamps,
    representing average power during the interval since the previous reading.
    
    Scientifically correct calculation:
    - Energy = Σ(P_i × Δt_i) where Δt_i is the interval for each power reading
    - For entry i, Δt_i = timestamp[i] - timestamp[i-1] (from consecutive entries)
    - For entry 0, we use step_duration_sec as the interval estimate
    - Average power = total_energy / total_duration
    
    Args:
        entries: List of Scaphandre report entries
        step_duration_sec: Configured step duration (used for first interval)
        target_pid: If specified, only aggregate for this PID
        
    Returns:
        EnergyMeasurement with totals in Joules and power in Watts
    """
    if not entries:
        return EnergyMeasurement()
    
    # Collect power readings and timestamps per entry
    # Per-process power (attributed based on CPU usage)
    proc_power_uW: list[float] = []
    pkg_power_uW: list[float] = []
    dram_power_uW: list[float] = []
    
    # System-wide power (total from host and sockets)
    sys_host_power_uW: list[float] = []
    sys_pkg_power_uW: list[float] = []
    sys_dram_power_uW: list[float] = []
    
    timestamps: list[float] = []
    
    for entry in entries:
        entry_proc_uW = 0.0
        entry_pkg_uW = 0.0
        entry_dram_uW = 0.0
        
        for consumer in entry.get("consumers", []):
            # If target_pid specified, filter by it
            if target_pid is not None and consumer.get("pid") != target_pid:
                continue
                
            entry_proc_uW += consumer.get("consumption") or 0.0
            
            # Fork format: per-consumer pkg/dram
            if "consumption_pkg" in consumer:
                entry_pkg_uW += consumer.get("consumption_pkg") or 0.0
            if "consumption_dram" in consumer:
                entry_dram_uW += consumer.get("consumption_dram") or 0.0
        
        proc_power_uW.append(entry_proc_uW)
        pkg_power_uW.append(entry_pkg_uW)
        dram_power_uW.append(entry_dram_uW)
        
        # System-wide: host consumption (total system power)
        host_data = entry.get("host", {})
        sys_host_power_uW.append(host_data.get("consumption") or 0.0)
        
        # System-wide: sum of all socket PKG consumption
        entry_sys_pkg_uW = 0.0
        entry_sys_dram_uW = 0.0
        for socket in entry.get("sockets", []):
            entry_sys_pkg_uW += socket.get("consumption") or 0.0
            for domain in socket.get("domains", []):
                if domain.get("name") == "dram":
                    entry_sys_dram_uW += domain.get("consumption") or 0.0
        sys_pkg_power_uW.append(entry_sys_pkg_uW)
        sys_dram_power_uW.append(entry_sys_dram_uW)
        
        # Extract timestamp
        ts = entry.get("timestamp") or host_data.get("timestamp")
        timestamps.append(ts)
    
    num_samples = len(entries)
    
    # Calculate energy using per-interval integration: E = Σ(P_i × Δt_i)
    # Each P_i represents power during interval Δt_i = t_i - t_{i-1}
    # For i=0, we estimate Δt_0 ≈ step_duration_sec
    total_proc_J = 0.0
    total_pkg_J = 0.0
    total_dram_J = 0.0
    total_sys_host_J = 0.0
    total_sys_pkg_J = 0.0
    total_sys_dram_J = 0.0
    total_duration_sec = 0.0
    
    for i in range(num_samples):
        # Determine interval duration for this sample
        if i == 0 or timestamps[i] is None or timestamps[i-1] is None:
            # First sample or missing timestamps: use configured step as estimate
            dt = step_duration_sec
        else:
            # Use actual time difference between consecutive samples
            dt = timestamps[i] - timestamps[i-1]
            # Guard against negative or zero intervals (data issues)
            if dt <= 0:
                dt = step_duration_sec
        
        total_duration_sec += dt
        
        # Energy for this interval: E_i = P_i × Δt_i
        # Convert µW to W (÷1e6), multiply by seconds = Joules
        total_proc_J += (proc_power_uW[i] / 1_000_000.0) * dt
        total_pkg_J += (pkg_power_uW[i] / 1_000_000.0) * dt
        total_dram_J += (dram_power_uW[i] / 1_000_000.0) * dt
        total_sys_host_J += (sys_host_power_uW[i] / 1_000_000.0) * dt
        total_sys_pkg_J += (sys_pkg_power_uW[i] / 1_000_000.0) * dt
        total_sys_dram_J += (sys_dram_power_uW[i] / 1_000_000.0) * dt
    
    # Average power = total energy / total duration
    if total_duration_sec > 0:
        avg_proc_W = total_proc_J / total_duration_sec
        avg_pkg_W = total_pkg_J / total_duration_sec
        avg_dram_W = total_dram_J / total_duration_sec
        avg_sys_host_W = total_sys_host_J / total_duration_sec
        avg_sys_pkg_W = total_sys_pkg_J / total_duration_sec
        avg_sys_dram_W = total_sys_dram_J / total_duration_sec
    else:
        avg_proc_W = avg_pkg_W = avg_dram_W = 0.0
        avg_sys_host_W = avg_sys_pkg_W = avg_sys_dram_W = 0.0
    
    return EnergyMeasurement(
        proc_J=total_proc_J,
        pkg_J=total_pkg_J,
        dram_J=total_dram_J,
        proc_W=avg_proc_W,
        pkg_W=avg_pkg_W,
        dram_W=avg_dram_W,
        sys_host_J=total_sys_host_J,
        sys_pkg_J=total_sys_pkg_J,
        sys_dram_J=total_sys_dram_J,
        sys_host_W=avg_sys_host_W,
        sys_pkg_W=avg_sys_pkg_W,
        sys_dram_W=avg_sys_dram_W,
        num_samples=num_samples,
        sampling_duration_sec=total_duration_sec,
    )


def measure_baseline(
    config: ScaphandreConfig,
    duration_sec: float = 30.0,
    startup_delay_sec: float = 0.2,
    verbose: bool = True,
    pre_wait_sec: float = 10.0,
) -> BaselineMeasurement:
    """
    Measure idle baseline system power.
    
    Runs Scaphandre for the specified duration with no workload to capture
    the system's idle power consumption. This can be subtracted from workload
    measurements to get net energy above baseline.
    
    Args:
        config: Scaphandre configuration
        duration_sec: How long to measure idle power
        startup_delay_sec: Delay after starting Scaphandre
        verbose: Print progress messages
        pre_wait_sec: Seconds to wait before starting measurement (to let system settle)
        
    Returns:
        BaselineMeasurement with idle power values
    """
    if pre_wait_sec > 0:
        if verbose:
            print(f"\n... waiting {pre_wait_sec}s for system to settle ...")
        time.sleep(pre_wait_sec)

    if verbose:
        print(f"\n=== Measuring idle baseline for {duration_sec}s ===")
    
    # Clean previous output
    if os.path.exists(config.output_file):
        os.remove(config.output_file)
    
    # Start Scaphandre (no process filtering for baseline - we want system-wide only)
    scaph = subprocess.Popen([
        config.scaphandre_path, "json",
        "--process-regex", config.process_regex,
        "--step", str(config.step_sec),
        "--step-nano", str(config.step_nano),
        "--file", config.output_file,
    ])
    
    time.sleep(startup_delay_sec)
    
    # Wait for the baseline duration (no workload)
    time.sleep(duration_sec)
    
    # Stop Scaphandre
    scaph.terminate()
    scaph.wait()
    
    # Parse output
    with open(config.output_file) as f:
        content = f.read()
    
    entries = parse_scaphandre_json(content)
    
    # Calculate step duration from config
    step_duration_sec = config.step_sec + (config.step_nano / 1_000_000_000.0)
    energy = aggregate_energy(entries, step_duration_sec, target_pid=None)
    
    if verbose:
        print(f"  Samples: {energy.num_samples}")
        print(f"  Idle host power: {energy.sys_host_W:.2f} W")
        print(f"  Idle PKG power: {energy.sys_pkg_W:.2f} W")
        print(f"  Idle DRAM power: {energy.sys_dram_W:.2f} W")
    
    return BaselineMeasurement(
        idle_host_power_W=energy.sys_host_W,
        idle_pkg_power_W=energy.sys_pkg_W,
        idle_dram_power_W=energy.sys_dram_W,
        duration_sec=energy.sampling_duration_sec,
        num_samples=energy.num_samples,
    )


def run_experiment(
    workload: Callable[[], None],
    *,
    config: ScaphandreConfig,
    measure_runs: int,
    num_trials: int,
    cooldown_sec: float = 120.0,
    baseline_duration_sec: float = 0.0,
    experiment_label: str = "",
    extra_config: Optional[dict] = None,
    collect_samples: bool = False,
    startup_delay_sec: float = 0.2,
    target_pid: Optional[int] = None,
    verbose: bool = True,
) -> ExperimentResults:
    """
    Run an energy measurement experiment.
    
    Args:
        workload: Function to execute during measurement (called measure_runs times per trial)
        config: Scaphandre configuration
        measure_runs: Number of times to run workload per trial
        num_trials: Number of trials to run
        cooldown_sec: Seconds to wait between trials
        baseline_duration_sec: If > 0, measure idle baseline first (recommended: 30-60s)
        experiment_label: Label for the experiment
        extra_config: Additional config to include in results
        collect_samples: Whether to collect per-step samples
        startup_delay_sec: Delay after starting Scaphandre
        target_pid: If specified, only aggregate energy for this PID
        verbose: Print progress messages
        
    Returns:
        ExperimentResults with all trials and summary statistics
    """
    trials: list[TrialResult] = []
    baseline: Optional[BaselineMeasurement] = None
    
    # Measure idle baseline if requested
    if baseline_duration_sec > 0:
        baseline = measure_baseline(
            config=config,
            duration_sec=baseline_duration_sec,
            startup_delay_sec=startup_delay_sec,
            verbose=verbose,
        )
        # Small cooldown after baseline measurement
        if verbose:
            print("  Cooling down after baseline...")
        time.sleep(5.0)
    
    for trial_idx in range(1, num_trials + 1):
        if verbose:
            print(f"\n=== Trial {trial_idx}/{num_trials} ===")
        
        # Clean previous output
        if os.path.exists(config.output_file):
            os.remove(config.output_file)
        
        # Start Scaphandre
        scaph = subprocess.Popen([
            config.scaphandre_path, "json",
            "--process-regex", config.process_regex,
            "--step", str(config.step_sec),
            "--step-nano", str(config.step_nano),
            "--file", config.output_file,
        ])
        
        time.sleep(startup_delay_sec)
        
        # Run workload and measure time
        start_time = time.perf_counter()
        
        for _ in range(measure_runs):
            workload()
        
        duration_sec = time.perf_counter() - start_time
        
        # Stop Scaphandre
        scaph.terminate()
        scaph.wait()
        
        # Parse output
        with open(config.output_file) as f:
            content = f.read()
        
        entries = parse_scaphandre_json(content)
        
        # Calculate step duration from config
        step_duration_sec = config.step_sec + (config.step_nano / 1_000_000_000.0)
        energy = aggregate_energy(entries, step_duration_sec, target_pid=target_pid)
        
        # Calculate per-run energy
        proc_per_run = energy.proc_J / measure_runs
        pkg_per_run = energy.pkg_J / measure_runs
        dram_per_run = energy.dram_J / measure_runs
        
        # Calculate net energy above baseline (if baseline measured)
        net_host_J: Optional[float] = None
        net_pkg_J: Optional[float] = None
        net_dram_J: Optional[float] = None
        net_host_per_run_J: Optional[float] = None
        net_pkg_per_run_J: Optional[float] = None
        net_dram_per_run_J: Optional[float] = None
        
        if baseline is not None:
            # Net energy = Total - (idle_power × duration)
            idle_host_energy = baseline.idle_host_power_W * energy.sampling_duration_sec
            idle_pkg_energy = baseline.idle_pkg_power_W * energy.sampling_duration_sec
            idle_dram_energy = baseline.idle_dram_power_W * energy.sampling_duration_sec
            
            net_host_J = max(0.0, energy.sys_host_J - idle_host_energy)
            net_pkg_J = max(0.0, energy.sys_pkg_J - idle_pkg_energy)
            net_dram_J = max(0.0, energy.sys_dram_J - idle_dram_energy)
            
            net_host_per_run_J = net_host_J / measure_runs
            net_pkg_per_run_J = net_pkg_J / measure_runs
            net_dram_per_run_J = net_dram_J / measure_runs
        
        if verbose:
            print(f"  Wall-clock duration: {duration_sec:.2f}s")
            print(f"  Sampling duration: {energy.sampling_duration_sec:.4f}s ({energy.num_samples} samples)")
            print(f"  Total: proc={energy.proc_J:.4f}J, pkg={energy.pkg_J:.4f}J, dram={energy.dram_J:.4f}J")
            print(f"  Power: proc={energy.proc_W:.4f}W, pkg={energy.pkg_W:.4f}W, dram={energy.dram_W:.4f}W")
            print(f"  System: host={energy.sys_host_J:.4f}J ({energy.sys_host_W:.4f}W), pkg={energy.sys_pkg_J:.4f}J, dram={energy.sys_dram_J:.4f}J")
            if net_host_J is not None:
                print(f"  Net above idle: host={net_host_J:.4f}J, pkg={net_pkg_J:.4f}J, dram={net_dram_J:.4f}J")
        
        trial_result = TrialResult(
            trial=trial_idx,
            duration_sec=duration_sec,
            measure_runs=measure_runs,
            total_proc_J=energy.proc_J,
            total_pkg_J=energy.pkg_J,
            total_dram_J=energy.dram_J,
            proc_energy_per_run_J=proc_per_run,
            pkg_energy_per_run_J=pkg_per_run,
            dram_energy_per_run_J=dram_per_run,
            avg_proc_power_W=energy.proc_W,
            avg_pkg_power_W=energy.pkg_W,
            avg_dram_power_W=energy.dram_W,
            sys_total_host_J=energy.sys_host_J,
            sys_total_pkg_J=energy.sys_pkg_J,
            sys_total_dram_J=energy.sys_dram_J,
            avg_sys_host_power_W=energy.sys_host_W,
            avg_sys_pkg_power_W=energy.sys_pkg_W,
            avg_sys_dram_power_W=energy.sys_dram_W,
            net_sys_host_J=net_host_J,
            net_sys_pkg_J=net_pkg_J,
            net_sys_dram_J=net_dram_J,
            net_sys_host_per_run_J=net_host_per_run_J,
            net_sys_pkg_per_run_J=net_pkg_per_run_J,
            net_sys_dram_per_run_J=net_dram_per_run_J,
            samples=entries if collect_samples else None,
        )
        
        trials.append(trial_result)
        
        # Cooldown between trials (except last)
        if trial_idx < num_trials and cooldown_sec > 0:
            if verbose:
                print(f"  Cooling down for {cooldown_sec}s...")
            time.sleep(cooldown_sec)
    
    # Compute summary statistics
    summary = compute_summary(trials)
    
    # Build config dict
    result_config = {
        "experiment_label": experiment_label,
        "measure_runs": measure_runs,
        "num_trials": num_trials,
        "scaphandre_step_sec": config.step_sec,
        "scaphandre_step_nano": config.step_nano,
        "process_regex": config.process_regex,
        "cooldown_sec": cooldown_sec,
        "baseline_duration_sec": baseline_duration_sec,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    if extra_config:
        result_config.update(extra_config)
    
    return ExperimentResults(config=result_config, trials=trials, summary=summary, baseline=baseline)


def compute_summary(trials: list[TrialResult]) -> ExperimentSummary:
    """Compute summary statistics from trial results."""
    
    # Total energy per trial
    total_proc = [t.total_proc_J for t in trials]
    total_pkg = [t.total_pkg_J for t in trials]
    total_dram = [t.total_dram_J for t in trials]
    
    # Energy per run
    proc_per_run = [t.proc_energy_per_run_J for t in trials]
    pkg_per_run = [t.pkg_energy_per_run_J for t in trials]
    dram_per_run = [t.dram_energy_per_run_J for t in trials]
    
    # Power
    proc_power = [t.avg_proc_power_W for t in trials]
    pkg_power = [t.avg_pkg_power_W for t in trials]
    dram_power = [t.avg_dram_power_W for t in trials]
    
    # System-wide totals
    sys_host = [t.sys_total_host_J for t in trials]
    sys_pkg = [t.sys_total_pkg_J for t in trials]
    sys_dram = [t.sys_total_dram_J for t in trials]
    
    # System-wide power
    sys_host_power = [t.avg_sys_host_power_W for t in trials]
    sys_pkg_power = [t.avg_sys_pkg_power_W for t in trials]
    sys_dram_power = [t.avg_sys_dram_power_W for t in trials]
    
    # Net energy (if baseline was measured)
    has_net = trials[0].net_sys_host_J is not None if trials else False
    net_host = [t.net_sys_host_J for t in trials if t.net_sys_host_J is not None]
    net_pkg = [t.net_sys_pkg_J for t in trials if t.net_sys_pkg_J is not None]
    net_dram = [t.net_sys_dram_J for t in trials if t.net_sys_dram_J is not None]
    net_host_per_run = [t.net_sys_host_per_run_J for t in trials if t.net_sys_host_per_run_J is not None]
    net_pkg_per_run = [t.net_sys_pkg_per_run_J for t in trials if t.net_sys_pkg_per_run_J is not None]
    net_dram_per_run = [t.net_sys_dram_per_run_J for t in trials if t.net_sys_dram_per_run_J is not None]
    
    def safe_stdev(values: list[float]) -> float:
        return stats.pstdev(values) if len(values) > 1 else 0.0
    
    def safe_mean_opt(values: list[float]) -> Optional[float]:
        return stats.mean(values) if values else None
    
    def safe_stdev_opt(values: list[float]) -> Optional[float]:
        return safe_stdev(values) if values else None
    
    return ExperimentSummary(
        mean_total_proc_J=stats.mean(total_proc),
        mean_total_pkg_J=stats.mean(total_pkg),
        mean_total_dram_J=stats.mean(total_dram),
        stdev_total_proc_J=safe_stdev(total_proc),
        stdev_total_pkg_J=safe_stdev(total_pkg),
        stdev_total_dram_J=safe_stdev(total_dram),
        mean_proc_energy_per_run_J=stats.mean(proc_per_run),
        mean_pkg_energy_per_run_J=stats.mean(pkg_per_run),
        mean_dram_energy_per_run_J=stats.mean(dram_per_run),
        stdev_proc_energy_per_run_J=safe_stdev(proc_per_run),
        stdev_pkg_energy_per_run_J=safe_stdev(pkg_per_run),
        stdev_dram_energy_per_run_J=safe_stdev(dram_per_run),
        mean_proc_power_W=stats.mean(proc_power),
        mean_pkg_power_W=stats.mean(pkg_power),
        mean_dram_power_W=stats.mean(dram_power),
        stdev_proc_power_W=safe_stdev(proc_power),
        stdev_pkg_power_W=safe_stdev(pkg_power),
        stdev_dram_power_W=safe_stdev(dram_power),
        mean_sys_host_J=stats.mean(sys_host),
        mean_sys_pkg_J=stats.mean(sys_pkg),
        mean_sys_dram_J=stats.mean(sys_dram),
        stdev_sys_host_J=safe_stdev(sys_host),
        stdev_sys_pkg_J=safe_stdev(sys_pkg),
        stdev_sys_dram_J=safe_stdev(sys_dram),
        mean_sys_host_power_W=stats.mean(sys_host_power),
        mean_sys_pkg_power_W=stats.mean(sys_pkg_power),
        mean_sys_dram_power_W=stats.mean(sys_dram_power),
        stdev_sys_host_power_W=safe_stdev(sys_host_power),
        stdev_sys_pkg_power_W=safe_stdev(sys_pkg_power),
        stdev_sys_dram_power_W=safe_stdev(sys_dram_power),
        mean_net_sys_host_J=safe_mean_opt(net_host),
        mean_net_sys_pkg_J=safe_mean_opt(net_pkg),
        mean_net_sys_dram_J=safe_mean_opt(net_dram),
        stdev_net_sys_host_J=safe_stdev_opt(net_host),
        stdev_net_sys_pkg_J=safe_stdev_opt(net_pkg),
        stdev_net_sys_dram_J=safe_stdev_opt(net_dram),
        mean_net_sys_host_per_run_J=safe_mean_opt(net_host_per_run),
        mean_net_sys_pkg_per_run_J=safe_mean_opt(net_pkg_per_run),
        mean_net_sys_dram_per_run_J=safe_mean_opt(net_dram_per_run),
        stdev_net_sys_host_per_run_J=safe_stdev_opt(net_host_per_run),
        stdev_net_sys_pkg_per_run_J=safe_stdev_opt(net_pkg_per_run),
        stdev_net_sys_dram_per_run_J=safe_stdev_opt(net_dram_per_run),
    )


def save_results(results: ExperimentResults, filepath: str, include_samples: bool = False) -> None:
    """
    Save experiment results to JSON file.
    
    Args:
        results: ExperimentResults to save
        filepath: Output file path
        include_samples: Whether to include per-step samples (can be large)
    """
    data = {
        "config": results.config,
        "baseline": asdict(results.baseline) if results.baseline else None,
        "trials": [],
        "summary": asdict(results.summary),
    }
    
    for trial in results.trials:
        trial_dict = asdict(trial)
        if not include_samples:
            trial_dict.pop("samples", None)
        data["trials"].append(trial_dict)
    
    with open(filepath, "w") as f:
        json.dump(data, f, indent=2)


def print_summary(results: ExperimentResults) -> None:
    """Print a human-readable summary of results."""
    s = results.summary
    cfg = results.config
    
    print("\n" + "=" * 50)
    print(f" ENERGY BENCHMARK: {cfg.get('experiment_label', 'Unnamed')}")
    print("=" * 50)
    print(f"Trials: {cfg['num_trials']} | Runs/trial: {cfg['measure_runs']}")
    
    # Show baseline if measured
    if results.baseline is not None:
        b = results.baseline
        print(f"\nIdle baseline (measured for {b.duration_sec:.1f}s):")
        print(f"  HOST: {b.idle_host_power_W:.2f} W | PKG: {b.idle_pkg_power_W:.2f} W | DRAM: {b.idle_dram_power_W:.2f} W")
    
    print()
    print("Energy per run (Joules):  [Process-attributed]")
    print(f"  PROC:  {s.mean_proc_energy_per_run_J:.9f} ± {s.stdev_proc_energy_per_run_J:.9f}")
    print(f"  PKG:   {s.mean_pkg_energy_per_run_J:.9f} ± {s.stdev_pkg_energy_per_run_J:.9f}")
    print(f"  DRAM:  {s.mean_dram_energy_per_run_J:.9f} ± {s.stdev_dram_energy_per_run_J:.9f}")
    print()
    print("Average power (Watts):")
    print(f"  PROC:  {s.mean_proc_power_W:.6f} ± {s.stdev_proc_power_W:.6f}")
    print(f"  PKG:   {s.mean_pkg_power_W:.6f} ± {s.stdev_pkg_power_W:.6f}")
    print(f"  DRAM:  {s.mean_dram_power_W:.6f} ± {s.stdev_dram_power_W:.6f}")
    print()
    print("System-wide energy per trial (Joules):")
    print(f"  HOST:  {s.mean_sys_host_J:.4f} ± {s.stdev_sys_host_J:.4f}")
    print(f"  PKG:   {s.mean_sys_pkg_J:.4f} ± {s.stdev_sys_pkg_J:.4f}")
    print(f"  DRAM:  {s.mean_sys_dram_J:.4f} ± {s.stdev_sys_dram_J:.4f}")
    print()
    print("System-wide average power (Watts):")
    print(f"  HOST:  {s.mean_sys_host_power_W:.4f} ± {s.stdev_sys_host_power_W:.4f}")
    print(f"  PKG:   {s.mean_sys_pkg_power_W:.4f} ± {s.stdev_sys_pkg_power_W:.4f}")
    print(f"  DRAM:  {s.mean_sys_dram_power_W:.4f} ± {s.stdev_sys_dram_power_W:.4f}")
    
    # Show net energy if baseline was measured
    if s.mean_net_sys_host_per_run_J is not None:
        print()
        print("NET energy above idle per run (Joules):  [System-wide]")
        print(f"  HOST:  {s.mean_net_sys_host_per_run_J:.9f} ± {s.stdev_net_sys_host_per_run_J:.9f}")
        print(f"  PKG:   {s.mean_net_sys_pkg_per_run_J:.9f} ± {s.stdev_net_sys_pkg_per_run_J:.9f}")
        print(f"  DRAM:  {s.mean_net_sys_dram_per_run_J:.9f} ± {s.stdev_net_sys_dram_per_run_J:.9f}")
    
    print("=" * 50)
