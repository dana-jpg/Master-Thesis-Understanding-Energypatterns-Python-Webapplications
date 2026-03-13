#!/usr/bin/env python3
"""
Get Buying Amount - Energy Measurement

Measures energy consumption of GrossProfitGenerator.get_buying_amount function.
"""

import os
import sys
import subprocess
import time
import statistics as stats
from tqdm.auto import tqdm

import frappe
from setproctitle import setproctitle

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scaphandre_energy import (
    ScaphandreConfig,
    parse_scaphandre_json,
    aggregate_energy,
    save_results,
    print_summary,
    ExperimentResults,
    ExperimentSummary,
    TrialResult,
    measure_baseline,
    BaselineMeasurement,
)

# ------------------------------------------
# CONFIGURATION
# ------------------------------------------

SITE = "erpnext.localhost"
COMPANY = "UZH"
FROM_DATE = "2023-01-01"
TO_DATE = "2025-12-31"
GROUP_BY = "Item Code"
TEST_ITEM_CODE = "ENERGY-ITEM-1"
TEST_WAREHOUSE = "Energy Test Warehouse - U"

PROCESS_NAME = "erpnext_child_worker"
MEASURE_RUNS = 5000
NUM_TRIALS = 20
NUM_TRIALS = 20
COOLDOWN_SEC = 120
BASELINE_DURATION_SEC = 30

RESULTS_FILE = os.environ.get("ENERGY_RESULTS_FILE", "energy_results_get_buying_amount.json")

CONFIG = ScaphandreConfig(
    process_regex=f"^{PROCESS_NAME}$",
    step_sec=0,
    step_nano=500_000,
)

# ------------------------------------------
# Initialize ERPNext
# ------------------------------------------

os.environ["FRAPPE_BENCH_DIR"] = "/home/username/frappe"
os.environ["SITES_DIR"] = "/home/username/frappe/sites"
os.environ["PATH_TRANSLATED"] = "/home/username/frappe/sites"
sys.path.insert(0, "/home/username/frappe")
sys.path.insert(0, "/home/username/frappe/apps")
sys.path.insert(0, "/home/username/frappe/apps/frappe")

frappe.init(site=SITE, sites_path="/home/username/frappe/sites")
frappe.connect()

from erpnext.accounts.report.gross_profit.gross_profit import GrossProfitGenerator


# ------------------------------------------
# SINGLE TRIAL
# ------------------------------------------

from typing import Optional

def run_single_trial(trial_idx: int, baseline: Optional[BaselineMeasurement] = None) -> TrialResult:
    if os.path.exists(CONFIG.output_file):
        os.remove(CONFIG.output_file)

    scaph = subprocess.Popen([
        CONFIG.scaphandre_path, "json",
        "--process-regex", CONFIG.process_regex,
        "--step", str(CONFIG.step_sec),
        "--step-nano", str(CONFIG.step_nano),
        "--file", CONFIG.output_file,
    ])

    r, w = os.pipe()
    pid = os.fork()

    if pid == 0:
        setproctitle(PROCESS_NAME)
        os.close(w)
        os.read(r, 1)
        os.close(r)

        for _ in tqdm(range(MEASURE_RUNS), desc=f"Trial {trial_idx}", disable=bool(os.environ.get("CI")), mininterval=2.0, file=sys.stderr):
            filters = frappe._dict({
                "company": COMPANY,
                "from_date": FROM_DATE,
                "to_date": TO_DATE,
                "group_by": GROUP_BY,
            })

            gpg = GrossProfitGenerator(filters)

            row = frappe._dict({
                "item_code": TEST_ITEM_CODE,
                "warehouse": TEST_WAREHOUSE,
                "qty": 1.0,
                "update_stock": 1,
                "dn_detail": None,
                "parenttype": "Sales Invoice",
                "parent": "ENERGY-TEST-SI",
                "invoice": "ENERGY-TEST-SI",
                "delivery_note": None,
                "item_row": "ENERGY-TEST-ROW",
                "sales_order": None,
                "so_detail": None,
                "project": None,
                "cost_center": None,
                "serial_and_batch_bundle": None,
            })

            _ = gpg.get_buying_amount(row, TEST_ITEM_CODE)

        os._exit(0)

    os.close(r)

    while not os.path.exists(CONFIG.output_file):
        time.sleep(0.01)

    start_time = time.perf_counter()
    os.write(w, b"1")
    os.close(w)

    os.waitpid(pid, 0)
    duration_sec = time.perf_counter() - start_time

    scaph.terminate()
    scaph.wait()

    with open(CONFIG.output_file) as f:
        content = f.read()

    entries = parse_scaphandre_json(content)
    step_duration = CONFIG.step_sec + (CONFIG.step_nano / 1_000_000_000.0)
    energy = aggregate_energy(entries, step_duration, target_pid=pid)

    # Calculate net energy above baseline if available
    net_host_J = None
    net_pkg_J = None
    net_dram_J = None
    net_host_per_run_J = None
    net_pkg_per_run_J = None
    net_dram_per_run_J = None

    if baseline is not None:
        idle_host_energy = baseline.idle_host_power_W * energy.sampling_duration_sec
        idle_pkg_energy = baseline.idle_pkg_power_W * energy.sampling_duration_sec
        idle_dram_energy = baseline.idle_dram_power_W * energy.sampling_duration_sec

        net_host_J = max(0.0, energy.sys_host_J - idle_host_energy)
        net_pkg_J = max(0.0, energy.sys_pkg_J - idle_pkg_energy)
        net_dram_J = max(0.0, energy.sys_dram_J - idle_dram_energy)

        net_host_per_run_J = net_host_J / MEASURE_RUNS
        net_pkg_per_run_J = net_pkg_J / MEASURE_RUNS
        net_dram_per_run_J = net_dram_J / MEASURE_RUNS

    print(f"[Trial {trial_idx}] proc={energy.proc_J:.4f}J, pkg={energy.pkg_J:.4f}J, dram={energy.dram_J:.4f}J")

    return TrialResult(
        trial=trial_idx,
        duration_sec=duration_sec,
        measure_runs=MEASURE_RUNS,
        total_proc_J=energy.proc_J,
        total_pkg_J=energy.pkg_J,
        total_dram_J=energy.dram_J,
        proc_energy_per_run_J=energy.proc_J / MEASURE_RUNS,
        pkg_energy_per_run_J=energy.pkg_J / MEASURE_RUNS,
        dram_energy_per_run_J=energy.dram_J / MEASURE_RUNS,
        avg_proc_power_W=energy.proc_J / duration_sec if duration_sec > 0 else 0,
        avg_pkg_power_W=energy.pkg_J / duration_sec if duration_sec > 0 else 0,
        avg_dram_power_W=energy.dram_J / duration_sec if duration_sec > 0 else 0,
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


# ------------------------------------------
# MAIN
# ------------------------------------------

if __name__ == "__main__":
    # Measure idle baseline first
    baseline = None
    if BASELINE_DURATION_SEC > 0:
        print("\n--- Measuring idle baseline ---")
        # Need server running for baseline (ensure init/setup is done - already done above)
        baseline = measure_baseline(
            config=CONFIG,
            duration_sec=BASELINE_DURATION_SEC,
            verbose=True,
        )
        print("  Cooling down after baseline...")
        time.sleep(5.0)

    trials = []

    for i in range(1, NUM_TRIALS + 1):
        trials.append(run_single_trial(i, baseline=baseline))
        if i < NUM_TRIALS:
            time.sleep(COOLDOWN_SEC)

    def safe_stdev(vals):
        return stats.pstdev(vals) if len(vals) > 1 else 0.0

    summary = ExperimentSummary(
        mean_total_proc_J=stats.mean([t.total_proc_J for t in trials]),
        mean_total_pkg_J=stats.mean([t.total_pkg_J for t in trials]),
        mean_total_dram_J=stats.mean([t.total_dram_J for t in trials]),
        stdev_total_proc_J=safe_stdev([t.total_proc_J for t in trials]),
        stdev_total_pkg_J=safe_stdev([t.total_pkg_J for t in trials]),
        stdev_total_dram_J=safe_stdev([t.total_dram_J for t in trials]),
        mean_sys_host_J=stats.mean([t.sys_total_host_J for t in trials]),
        mean_sys_pkg_J=stats.mean([t.sys_total_pkg_J for t in trials]),
        mean_sys_dram_J=stats.mean([t.sys_total_dram_J for t in trials]),
        stdev_sys_host_J=safe_stdev([t.sys_total_host_J for t in trials]),
        stdev_sys_pkg_J=safe_stdev([t.sys_total_pkg_J for t in trials]),
        stdev_sys_dram_J=safe_stdev([t.sys_total_dram_J for t in trials]),
        mean_proc_energy_per_run_J=stats.mean([t.proc_energy_per_run_J for t in trials]),
        mean_pkg_energy_per_run_J=stats.mean([t.pkg_energy_per_run_J for t in trials]),
        mean_dram_energy_per_run_J=stats.mean([t.dram_energy_per_run_J for t in trials]),
        stdev_proc_energy_per_run_J=safe_stdev([t.proc_energy_per_run_J for t in trials]),
        stdev_pkg_energy_per_run_J=safe_stdev([t.pkg_energy_per_run_J for t in trials]),
        stdev_dram_energy_per_run_J=safe_stdev([t.dram_energy_per_run_J for t in trials]),
        mean_proc_power_W=stats.mean([t.avg_proc_power_W for t in trials]),
        mean_pkg_power_W=stats.mean([t.avg_pkg_power_W for t in trials]),
        mean_dram_power_W=stats.mean([t.avg_dram_power_W for t in trials]),
        stdev_proc_power_W=safe_stdev([t.avg_proc_power_W for t in trials]),
        stdev_pkg_power_W=safe_stdev([t.avg_pkg_power_W for t in trials]),
        stdev_dram_power_W=safe_stdev([t.avg_dram_power_W for t in trials]),
        mean_sys_host_power_W=stats.mean([t.avg_sys_host_power_W for t in trials]),
        mean_sys_pkg_power_W=stats.mean([t.avg_sys_pkg_power_W for t in trials]),
        mean_sys_dram_power_W=stats.mean([t.avg_sys_dram_power_W for t in trials]),
        stdev_sys_host_power_W=safe_stdev([t.avg_sys_host_power_W for t in trials]),
        stdev_sys_pkg_power_W=safe_stdev([t.avg_sys_pkg_power_W for t in trials]),
        stdev_sys_dram_power_W=safe_stdev([t.avg_sys_dram_power_W for t in trials]),
        # Net energy stats
        mean_net_sys_host_J=stats.mean([t.net_sys_host_J for t in trials if t.net_sys_host_J is not None]) if baseline else None,
        mean_net_sys_pkg_J=stats.mean([t.net_sys_pkg_J for t in trials if t.net_sys_pkg_J is not None]) if baseline else None,
        mean_net_sys_dram_J=stats.mean([t.net_sys_dram_J for t in trials if t.net_sys_dram_J is not None]) if baseline else None,
        stdev_net_sys_host_J=safe_stdev([t.net_sys_host_J for t in trials if t.net_sys_host_J is not None]) if baseline else None,
        stdev_net_sys_pkg_J=safe_stdev([t.net_sys_pkg_J for t in trials if t.net_sys_pkg_J is not None]) if baseline else None,
        stdev_net_sys_dram_J=safe_stdev([t.net_sys_dram_J for t in trials if t.net_sys_dram_J is not None]) if baseline else None,
        # Net energy per run stats
        mean_net_sys_host_per_run_J=stats.mean([t.net_sys_host_per_run_J for t in trials if t.net_sys_host_per_run_J is not None]) if baseline else None,
        mean_net_sys_pkg_per_run_J=stats.mean([t.net_sys_pkg_per_run_J for t in trials if t.net_sys_pkg_per_run_J is not None]) if baseline else None,
        mean_net_sys_dram_per_run_J=stats.mean([t.net_sys_dram_per_run_J for t in trials if t.net_sys_dram_per_run_J is not None]) if baseline else None,
        stdev_net_sys_host_per_run_J=safe_stdev([t.net_sys_host_per_run_J for t in trials if t.net_sys_host_per_run_J is not None]) if baseline else None,
        stdev_net_sys_pkg_per_run_J=safe_stdev([t.net_sys_pkg_per_run_J for t in trials if t.net_sys_pkg_per_run_J is not None]) if baseline else None,
        stdev_net_sys_dram_per_run_J=safe_stdev([t.net_sys_dram_per_run_J for t in trials if t.net_sys_dram_per_run_J is not None]) if baseline else None,
    )

    results = ExperimentResults(
        config={
            "experiment_label": "GrossProfitGenerator.get_buying_amount",
            "site": SITE,
            "company": COMPANY,
            "test_item_code": TEST_ITEM_CODE,
            "test_warehouse": TEST_WAREHOUSE,
            "measure_runs": MEASURE_RUNS,
            "num_trials": NUM_TRIALS,
            "process_name": PROCESS_NAME,
            "scaphandre_step_sec": CONFIG.step_sec,
            "scaphandre_step_nano": CONFIG.step_nano,
            "baseline_duration_sec": BASELINE_DURATION_SEC,
        },
        trials=trials,
        summary=summary,
        baseline=baseline,
    )

    save_results(results, RESULTS_FILE)
    print_summary(results)
