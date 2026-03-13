#!/usr/bin/env python3
"""
Bulk Import Energy Measurement

Measures energy consumption of bulk URL imports in Mealie.
This script manages the server lifecycle (start/stop) and database restoration.

Note: This script uses a different measurement approach since the workload
is a single long-running operation rather than repeated short operations.
"""

import os
import sys
import json
import time
import shutil
import subprocess
from datetime import datetime, timezone
from typing import Optional
import requests
import psutil

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scaphandre_energy import (
    ScaphandreConfig,
    parse_scaphandre_json,
    aggregate_energy,
    measure_baseline,
    compute_summary,
    save_results,
    print_summary,
    ExperimentResults,
    TrialResult,
    BaselineMeasurement,
)

# ------------------------------------------
# CONFIGURATION
# ------------------------------------------

MEALIE_ROOT = "/home/username/mealie/mealie"
VENV_ACTIVATE = "/home/username/mealie/bin/activate"
DB_DIR = "/home/username/mealie/mealie/dev/data"
DB_BASE = f"{DB_DIR}/mealie_base.db"
DB_ACTIVE = f"{DB_DIR}/mealie.db"
IMPORTS_FILE = "/home/username/mealie/mealie/dev/energy/imports_100.json"

API_URL = "http://127.0.0.1:9001/api/recipes/create/url/bulk"
HEALTH_URL = "http://127.0.0.1:9001/api/app/about"

MEALIE_API_TOKEN = os.environ.get("MEALIE_API_TOKEN")
if not MEALIE_API_TOKEN:
    raise RuntimeError("MEALIE_API_TOKEN not set")

NUM_TRIALS = 20
POST_IMPORT_WAIT_SEC = 90
IDLE_SETTLE_SEC = 10
COOLDOWN_SEC = 120
BASELINE_DURATION_SEC = 30  # Idle baseline measurement duration

RESULTS_FILE = "energy_results_bulk_import.json"

CONFIG = ScaphandreConfig(
    process_regex=r".*python3.*mealie/app\.py",
    step_sec=0,
    step_nano=100_000_000,  # 100ms sampling for long operations
)

# ------------------------------------------
# SERVER MANAGEMENT
# ------------------------------------------

def kill_process_tree(pid):
    """Kill a process and all its children."""
    try:
        parent = psutil.Process(pid)
        for child in parent.children(recursive=True):
            child.kill()
        parent.kill()
    except psutil.NoSuchProcess:
        pass


def stop_mealie(process=None):
    """Stop the Mealie server."""
    print("Stopping Mealie...")
    if process:
        kill_process_tree(process.pid)
        process.wait()
    else:
        subprocess.run(["pkill", "-f", "task py"], stderr=subprocess.DEVNULL)
    time.sleep(2)


def start_mealie():
    """Start Mealie pinned to Core 2."""
    cmd = (
        f"cd {MEALIE_ROOT} && "
        f"source {VENV_ACTIVATE} && "
        f"taskset -c 2 task py > server.log 2>&1"
    )
    process = subprocess.Popen(
        cmd, shell=True, executable="/bin/bash", preexec_fn=os.setsid
    )
    return process


def wait_for_server_ready(timeout=60):
    """Wait for the server to be ready."""
    start = time.time()
    while time.time() - start < timeout:
        try:
            r = requests.get(HEALTH_URL, timeout=1)
            if r.status_code == 200:
                return True
        except requests.RequestException:
            pass
        time.sleep(1)
    raise RuntimeError("Server failed to start")


def restore_database():
    """Restore database to baseline state."""
    if not os.path.exists(DB_BASE):
        raise RuntimeError(f"Missing base DB: {DB_BASE}")
    shutil.copyfile(DB_BASE, DB_ACTIVE)


# ------------------------------------------
# SINGLE TRIAL
# ------------------------------------------

def run_trial(
    trial_idx: int, 
    payload: dict, 
    baseline: Optional[BaselineMeasurement] = None,
) -> TrialResult:
    """Run a single measurement trial."""
    prefix = f"[Trial {trial_idx}]"
    print(f"\n{prefix} Setting up environment...")

    # Reset environment
    stop_mealie()
    restore_database()
    
    # Start server
    app_proc = start_mealie()

    try:
        wait_for_server_ready()
        print(f"{prefix} Server up. Settling for {IDLE_SETTLE_SEC}s...")
        time.sleep(IDLE_SETTLE_SEC)

        # Start Scaphandre
        if os.path.exists(CONFIG.output_file):
            os.remove(CONFIG.output_file)

        scaph = subprocess.Popen([
            CONFIG.scaphandre_path, "json",
            "--process-regex", CONFIG.process_regex,
            "--step", str(CONFIG.step_sec),
            "--step-nano", str(CONFIG.step_nano),
            "--file", CONFIG.output_file,
        ])
        time.sleep(1.0)

        # Trigger workload
        print(f"{prefix} Triggering import...")
        start_time = time.perf_counter()
        
        headers = {"Authorization": f"Bearer {MEALIE_API_TOKEN}"}
        r = requests.post(API_URL, headers=headers, json=payload)
        r.raise_for_status()

        print(f"{prefix} HTTP {r.status_code}. Recording for {POST_IMPORT_WAIT_SEC}s...")
        time.sleep(POST_IMPORT_WAIT_SEC)
        
        duration_sec = time.perf_counter() - start_time

        # Stop measurement
        scaph.terminate()
        scaph.wait()

        # Parse results
        with open(CONFIG.output_file) as f:
            content = f.read()

        entries = parse_scaphandre_json(content)
        step_duration = CONFIG.step_sec + (CONFIG.step_nano / 1_000_000_000.0)
        energy = aggregate_energy(entries, step_duration)

        print(f"{prefix} Duration: {duration_sec:.2f}s")
        print(f"{prefix} Process: proc={energy.proc_J:.4f}J, pkg={energy.pkg_J:.4f}J")
        print(f"{prefix} System:  host={energy.sys_host_J:.2f}J, pkg={energy.sys_pkg_J:.2f}J")
        
        # Calculate net energy above baseline if available
        net_host_J: Optional[float] = None
        net_pkg_J: Optional[float] = None
        net_dram_J: Optional[float] = None
        net_host_per_run_J: Optional[float] = None
        net_pkg_per_run_J: Optional[float] = None
        net_dram_per_run_J: Optional[float] = None
        
        if baseline is not None:
            idle_host_energy = baseline.idle_host_power_W * energy.sampling_duration_sec
            idle_pkg_energy = baseline.idle_pkg_power_W * energy.sampling_duration_sec
            idle_dram_energy = baseline.idle_dram_power_W * energy.sampling_duration_sec
            
            net_host_J = max(0.0, energy.sys_host_J - idle_host_energy)
            net_pkg_J = max(0.0, energy.sys_pkg_J - idle_pkg_energy)
            net_dram_J = max(0.0, energy.sys_dram_J - idle_dram_energy)
            
            # For bulk import, measure_runs=1
            net_host_per_run_J = net_host_J
            net_pkg_per_run_J = net_pkg_J
            net_dram_per_run_J = net_dram_J
            
            print(f"{prefix} Net above idle: host={net_host_J:.2f}J, pkg={net_pkg_J:.2f}J")

        return TrialResult(
            trial=trial_idx,
            duration_sec=duration_sec,
            measure_runs=1,  # Single import operation
            total_proc_J=energy.proc_J,
            total_pkg_J=energy.pkg_J,
            total_dram_J=energy.dram_J,
            proc_energy_per_run_J=energy.proc_J,
            pkg_energy_per_run_J=energy.pkg_J,
            dram_energy_per_run_J=energy.dram_J,
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
        )

    finally:
        stop_mealie(app_proc)


# ------------------------------------------
# MAIN
# ------------------------------------------

if __name__ == "__main__":
    if not os.path.exists(IMPORTS_FILE):
        print(f"Error: Import file not found at {IMPORTS_FILE}")
        sys.exit(1)

    with open(IMPORTS_FILE) as f:
        payload = json.load(f)

    print(f"\n{'=' * 50}")
    print(f" BULK IMPORT ENERGY MEASUREMENT")
    print(f"{'=' * 50}")
    print(f"Trials: {NUM_TRIALS}")
    print(f"Baseline measurement: {BASELINE_DURATION_SEC}s")
    
    # Measure idle baseline first
    baseline: Optional[BaselineMeasurement] = None
    if BASELINE_DURATION_SEC > 0:
        print("\n--- Measuring idle baseline ---")
        # Need server running for baseline
        stop_mealie()
        restore_database()
        app_proc = start_mealie()
        try:
            wait_for_server_ready()
            time.sleep(IDLE_SETTLE_SEC)
            baseline = measure_baseline(
                config=CONFIG,
                duration_sec=BASELINE_DURATION_SEC,
                verbose=True,
            )
        finally:
            stop_mealie(app_proc)
        print("  Cooling down after baseline...")
        time.sleep(5.0)
    
    print(f"\n=== Starting {NUM_TRIALS} Measurement Trials ===")
    trials = []

    for i in range(1, NUM_TRIALS + 1):
        trial = run_trial(i, payload, baseline=baseline)
        trials.append(trial)
        if i < NUM_TRIALS:
            print(f"Cooling down for {COOLDOWN_SEC}s...")
            time.sleep(COOLDOWN_SEC)

    # Compute summary using the library function
    summary = compute_summary(trials)

    results = ExperimentResults(
        config={
            "experiment_label": "Bulk Import",
            "num_trials": NUM_TRIALS,
            "measure_runs": 1,
            "post_import_wait_sec": POST_IMPORT_WAIT_SEC,
            "baseline_duration_sec": BASELINE_DURATION_SEC,
            "imports_file": IMPORTS_FILE,
            "scaphandre_step_sec": CONFIG.step_sec,
            "scaphandre_step_nano": CONFIG.step_nano,
            "process_regex": CONFIG.process_regex,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
        trials=trials,
        summary=summary,
        baseline=baseline,
    )

    save_results(results, RESULTS_FILE)
    print_summary(results)
