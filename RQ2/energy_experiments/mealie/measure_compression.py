#!/usr/bin/env python3
"""
Compression Encoding - Energy Measurement

Measures energy consumption of different HTTP compression encodings
(identity, gzip, brotli) when serving large text responses.
"""

import os
import sys
import requests
from tqdm.auto import tqdm

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scaphandre_energy import (
    ScaphandreConfig,
    run_experiment,
    save_results,
    print_summary,
)

# ------------------------------------------
# CONFIGURATION
# ------------------------------------------

SERVER_URL = "http://127.0.0.1:9001/energy-test/large-text"
ENCODING = "identity"  # "identity" | "gzip" | "br"

MEASURE_RUNS = 5000
NUM_TRIALS = 20
COOLDOWN_SEC = 120
BASELINE_DURATION_SEC = 30  # Measure idle baseline before trials

RESULTS_FILE = f"energy_results_{ENCODING}.json"

CONFIG = ScaphandreConfig(
    process_regex=r".*python3.*mealie/app\.py",
    step_sec=0,
    step_nano=500_000,
)

# ------------------------------------------
# WORKLOAD
# ------------------------------------------

session = requests.Session()
headers = {"Accept-Encoding": ENCODING}


def compression_workload():
    """Fetch large text with specified encoding."""
    r = session.get(SERVER_URL, headers=headers)
    r.raise_for_status()


# ------------------------------------------
# MAIN
# ------------------------------------------

if __name__ == "__main__":
    pbar = None
    runs_done = 0

    def workload_with_progress():
        global runs_done, pbar
        if pbar is None:
            pbar = tqdm(total=MEASURE_RUNS, desc=f"Encoding: {ENCODING}")
        compression_workload()
        runs_done += 1
        pbar.update(1)
        if runs_done >= MEASURE_RUNS:
            pbar.close()
            pbar = None
            runs_done = 0

    results = run_experiment(
        workload=workload_with_progress,
        config=CONFIG,
        measure_runs=MEASURE_RUNS,
        num_trials=NUM_TRIALS,
        cooldown_sec=COOLDOWN_SEC,
        baseline_duration_sec=BASELINE_DURATION_SEC,
        experiment_label=f"Compression Encoding: {ENCODING}",
        extra_config={
            "server_url": SERVER_URL,
            "encoding": ENCODING,
        },
    )

    save_results(results, RESULTS_FILE)
    print_summary(results)
