#!/usr/bin/env python3
import os
import json
import time
import subprocess
import statistics as stats
import requests
from tqdm.auto import tqdm

# ------------------------------------------
# CONFIGURATION
# ------------------------------------------

BASE_URL = "http://127.0.0.1:9001"

MEASURE_RUNS = 100          # number of TIMELINE PAGE LOADS
NUM_TRIALS = 20

OUTPUT_FILE = "energy_scaphandre_timeline_single.json"
RESULTS_FILE = "energy_results_timeline_single.json"

SCAPHANDRE_STEP_SEC = 0
SCAPHANDRE_STEP_NANO = 500_000

PROCESS_REGEX = r".*python3.*mealie/app\.py"

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
# SCAPHANDRE PARSING
# ------------------------------------------

def parse_scaphandre(entries):
    total_proc_uJ = 0.0
    total_pkg_uJ = 0.0
    total_dram_uJ = 0.0

    for entry in entries:
        for consumer in entry.get("consumers", []):
            total_proc_uJ += consumer.get("consumption") or 0.0
            total_pkg_uJ += consumer.get("consumption_pkg") or 0.0
            total_dram_uJ += consumer.get("consumption_dram") or 0.0

    return total_proc_uJ / 1_000_000.0, total_pkg_uJ / 1_000_000.0, total_dram_uJ / 1_000_000.0

# ------------------------------------------
# SINGLE TRIAL
# ------------------------------------------

def run_single_trial(trial_idx: int):
    if os.path.exists(OUTPUT_FILE):
        os.remove(OUTPUT_FILE)

    scaph = subprocess.Popen([
        "/home/username/scaphandre/target/release/scaphandre", "json",
        "--process-regex", PROCESS_REGEX,
        "--step", str(SCAPHANDRE_STEP_SEC),
        "--step-nano", str(SCAPHANDRE_STEP_NANO),
        "--file", OUTPUT_FILE,
    ])

    time.sleep(0.2)

    session = requests.Session()
    session.headers.update(AUTH_HEADER)

    for _ in tqdm(range(MEASURE_RUNS), desc="Timeline page loads"):
        # 1️⃣ fetch timeline
        r = session.get(f"{BASE_URL}/api/recipes/timeline/events", params=TIMELINE_PARAMS)
        r.raise_for_status()

        events = r.json()["items"]
        recipe_ids = {e["recipeId"] for e in events if e.get("recipeId")}

        # 2️⃣ fetch each recipe individually (old behavior)
        for rid in recipe_ids:
            rr = session.get(f"{BASE_URL}/api/recipes/{rid}")
            rr.raise_for_status()

    scaph.terminate()
    scaph.wait()

    with open(OUTPUT_FILE) as f:
        content = f.read()
    
    # Parse concatenated JSON objects (scaphandre outputs {}{}{}, not [...])
    entries = []
    decoder = json.JSONDecoder()
    idx = 0
    while idx < len(content):
        remaining = content[idx:].lstrip()
        if not remaining:
            break
            obj, end_idx = decoder.raw_decode(remaining)
            entries.append(obj)
            idx += len(content[idx:]) - len(remaining) + end_idx
    
    total_proc_J, total_pkg_J, total_dram_J = parse_scaphandre(entries)

    return {
        "trial": trial_idx,
        "total_proc_J": total_proc_J,
        "total_pkg_J": total_pkg_J,
        "total_dram_J": total_dram_J,
        "proc_energy_per_page_J": total_proc_J / MEASURE_RUNS,
        "pkg_energy_per_page_J": total_pkg_J / MEASURE_RUNS,
        "dram_energy_per_page_J": total_dram_J / MEASURE_RUNS,
    }

# ------------------------------------------
# MAIN
# ------------------------------------------

if __name__ == "__main__":
    trials = []

    for i in range(1, NUM_TRIALS + 1):
        trials.append(run_single_trial(i))
        time.sleep(30)

    results = {
        "measure_runs": MEASURE_RUNS,
        "num_trials": NUM_TRIALS,
        "mean_proc_energy_per_page_J": stats.mean(t["proc_energy_per_page_J"] for t in trials),
        "mean_pkg_energy_per_page_J": stats.mean(t["pkg_energy_per_page_J"] for t in trials),
        "mean_dram_energy_per_page_J": stats.mean(t["dram_energy_per_page_J"] for t in trials),
        "trials": trials,
    }

    with open(RESULTS_FILE, "w") as f:
        json.dump(results, f, indent=2)
