#!/usr/bin/env python3
"""
Recipe Timeline Single - Energy Measurement

Measures energy consumption of timeline page loads where each recipe
is fetched individually (N+1 query pattern).
"""

import os
import sys
import requests
from tqdm.auto import tqdm

# Add parent dir to path for library import
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

BASE_URL = "http://127.0.0.1:9001"
MEASURE_RUNS = 100
NUM_TRIALS = 20

RESULTS_FILE = "energy_results_timeline_single.json"

AUTH_HEADER = {
    "Authorization": f"Bearer {os.environ['MEALIE_API_TOKEN']}"
}

TIMELINE_PARAMS = {
    "page": 1,
    "perPage": 32,
    "orderBy": "timestamp",
    "orderDirection": "asc",
    "queryFilter": '(recipe.group_id="258221ce-3911-477a-8e3e-c7f9215617e8") AND eventType IN ["info","system","comment"]',
}

# ------------------------------------------
# WORKLOAD
# ------------------------------------------

session = requests.Session()
session.headers.update(AUTH_HEADER)


def timeline_single_workload():
    """Single timeline page load with individual recipe fetches (N+1 pattern)."""
    # Fetch timeline
    r = session.get(f"{BASE_URL}/api/recipes/timeline/events", params=TIMELINE_PARAMS)
    r.raise_for_status()
    
    events = r.json()["items"]
    recipe_ids = {e["recipeId"] for e in events if e.get("recipeId")}
    
    # Fetch each recipe individually
    for rid in recipe_ids:
        rr = session.get(f"{BASE_URL}/api/recipes/{rid}")
        rr.raise_for_status()


# ------------------------------------------
# MAIN
# ------------------------------------------

if __name__ == "__main__":
    config = ScaphandreConfig(
        process_regex=r".*python3.*mealie/app\.py",
        step_sec=0,
        step_nano=500_000,
    )
    
    # Progress tracking
    pbar = None
    runs_done = 0
    
    def workload_with_progress():
        global runs_done, pbar
        if pbar is None:
            pbar = tqdm(total=MEASURE_RUNS, desc="Timeline loads (single)")
        timeline_single_workload()
        runs_done += 1
        pbar.update(1)
        if runs_done >= MEASURE_RUNS:
            pbar.close()
            pbar = None
            runs_done = 0
    
    results = run_experiment(
        workload=workload_with_progress,
        config=config,
        measure_runs=MEASURE_RUNS,
        num_trials=NUM_TRIALS,
        cooldown_sec=120.0,
        experiment_label="Timeline Single (individual recipe fetches)",
        extra_config={
            "base_url": BASE_URL,
            "timeline_params": TIMELINE_PARAMS,
        },
    )
    
    save_results(results, RESULTS_FILE)
    print_summary(results)
