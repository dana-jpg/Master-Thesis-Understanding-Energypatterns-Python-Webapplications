# RQ2 — Energy Experiments

> [!CAUTION]
> **These experiments can only be executed when the applications (Frappe/ERPNext and Mealie) are fully deployed and running on the target server.** The measurement scripts connect to running application instances via internal APIs and Frappe's Python runtime. They cannot be run locally or without a deployed environment.

---

## Repository Structure

```
RQ2/
├── energy_experiments/
│   ├── scaphandre_energy.py          # Shared energy measurement library
│   ├── SCAPHANDRE_ENERGY.md          # Library documentation
│   ├── frappe/                       # Frappe/ERPNext experiments
│   │   ├── run_frappe_measurements.py    # Orchestrator — runs all frappe experiments
│   │   ├── measure_item_defaults.py
│   │   ├── measure_get_item_price.py
│   │   ├── measure_generate_report.py
│   │   ├── measure_get_buying_amount.py
│   │   ├── measure_reorder_item.py
│   │   ├── measure_validate_billing.py
│   │   └── assets/                   # Optimized & unoptimized source file pairs
│   └── mealie/                       # Mealie experiments
│       ├── run_all_mealie_measurements.py  # Orchestrator — runs all mealie experiments
│       ├── measure_compression.py
│       ├── recipe_timeline_batch.py
│       ├── recipe_timeline_single.py
│       ├── measure_bulk_import.py
│       └── run_bulk_import_only.py
├── data/
│   └── experiment_results_raw/       # Raw JSON result files
└── results_analysis/                 # Jupyter notebooks for statistical analysis
```

---

## Shared Scaphandre Energy Library

All experiments use the shared library **`scaphandre_energy.py`** located at the root of `energy_experiments/`. This library wraps [Scaphandre](https://github.com/hubblo-org/scaphandre), a power measurement tool that reads Intel RAPL counters.

### How It Works

1. **Scaphandre** is started as a subprocess that continuously writes power readings (in microwatts) to a JSON file at a configurable sampling interval (default: 0.5 ms).
2. The library **integrates power over time** to compute energy in Joules: `Energy = Σ(P_i × Δt_i)`.
3. It captures three energy domains via Intel RAPL:
   - **`proc`** — Process-level energy (estimated from CPU share)
   - **`pkg`** — CPU package energy (all cores, L3 cache)
   - **`dram`** — Memory subsystem energy
4. Idle baseline subtraction is supported: a baseline measurement is taken before trials to compute net energy above idle.

### Key API

| Function | Purpose |
|----------|---------|
| `run_experiment()` | High-level API: runs a workload for N trials with cooldowns, handles Scaphandre start/stop, and returns aggregated results |
| `parse_scaphandre_json()` | Parses raw Scaphandre JSON output |
| `aggregate_energy()` | Integrates power samples into energy totals |
| `measure_baseline()` | Measures idle system power for baseline subtraction |
| `save_results()` | Saves `ExperimentResults` to JSON |
| `compute_summary()` | Computes mean/stdev statistics across trials |

Each individual measurement script imports from this library (via relative path insertion) to avoid code duplication. Full documentation is available in `SCAPHANDRE_ENERGY.md`.

---

## Frappe/ERPNext Experiments

### Overview

Six functions from ERPNext are measured, each comparing an **unoptimized** vs. **optimized** version of the source code. The orchestrator script `run_frappe_measurements.py` automates the entire process.

### The File-Swapping Mechanism

Each experiment runs twice (unoptimized → optimized) with 120s delays between runs. The key mechanism for this is **file swapping**:

1. The `assets/` directory contains **12 Python files** — one `_optimized.py` and one `_unoptimized.py` for each of the 6 target source files in ERPNext:

   | Asset Basename | Target File in ERPNext |
   |----------------|----------------------|
   | `item` | `stock/doctype/item/item.py` |
   | `get_item_details` | `stock/get_item_details.py` |
   | `item_wise_sales_register` | `accounts/report/item_wise_sales_register/item_wise_sales_register.py` |
   | `gross_profit` | `accounts/report/gross_profit/gross_profit.py` |
   | `reorder_item` | `stock/reorder_item.py` |
   | `accounts_controller` | `controllers/accounts_controller.py` |

2. Before running the unoptimized measurement, the orchestrator **copies** the `<basename>_unoptimized.py` asset over the real file in the ERPNext installation.
3. After completing the unoptimized measurement, it **copies** the `<basename>_optimized.py` asset over the same file.
4. After all experiments, the **original files are restored** from an in-memory backup taken at startup.

### How `run_frappe_measurements.py` Works

```
For each of the 6 experiments:
  1. Swap in the UNOPTIMIZED version of the target file
  2. Run the measurement script (e.g., measure_get_buying_amount.py)
     → Output: energy_results_<name>_unoptimized.json
  3. Cooldown (120 seconds)
  4. Swap in the OPTIMIZED version of the target file
  5. Run the measurement script again
     → Output: energy_results_<name>_optimized.json
  6. Cooldown (120 seconds) before the next experiment
```

All scripts are executed within the **Frappe virtual environment** and pinned to a specific CPU core (`taskset -c 3`) to reduce measurement noise.

### Individual Measurement Scripts

Each `measure_*.py` script follows the same pattern:

1. **Initialize Frappe** — connects to the ERPNext site via `frappe.init()` and `frappe.connect()`.
2. **Fork a child process** — sets a recognizable process title (`erpnext_child_worker`) so Scaphandre can filter by PID/regex.
3. **Execute the workload** — calls the target function (e.g., `GrossProfitGenerator.get_buying_amount()`) **5,000 times** per trial.
4. **Repeat for 20 trials** — with 120-second cooldowns between trials.
5. **Measure idle baseline** — 30 seconds of idle measurement before trials for baseline subtraction.
6. **Save results** — JSON output containing per-trial and summary statistics.

The result filename is controlled via the `ENERGY_RESULTS_FILE` environment variable (set by the orchestrator).

### Running

```bash
# On the deployment server, run all 6 experiments:
cd path/to/scripts #adjust as needed
source path/to/env
python run_frappe_measurements.py

# Or run a single experiment:
python measure_get_buying_amount.py
```

---

## Mealie Experiments

### Overview

The Mealie experiments measure three categories of operations, orchestrated by `run_all_mealie_measurements.py`:

1. **Compression** — Energy cost of different HTTP response encodings (`identity`, `gzip`, `br`)
2. **Timeline** — Energy cost of fetching recipe timeline data (batch vs. single query patterns)
3. **Bulk Import** — Energy cost of importing 100 recipes (unoptimized vs. optimized)

### How `run_all_mealie_measurements.py` Works

The orchestrator runs in two phases:

#### Phase 1: Compression & Timeline (server kept running)

```
1. Start Mealie server (pinned to CPU core 2)
2. Run measure_compression.py three times:
   - Modify the ENCODING variable to "br", "gzip", "identity" in sequence
   - Output: energy_results_br.json, energy_results_gzip.json, energy_results_identity.json
3. Run recipe_timeline_batch.py
   - Output: energy_results_timeline_batch.json
4. Run recipe_timeline_single.py
   - Output: energy_results_timeline_single.json
5. Stop server
```

#### Phase 2: Bulk Import (server restarted per trial)

```
1. Save current state of recipe_data_service.py and recipe_bulk_scraper.py
2. Swap in UNOPTIMIZED versions from assets/
3. Modify RESULTS_FILE in measure_bulk_import.py → "energy_results_bulk_import_not_optimized.json"
4. Run measure_bulk_import.py (manages its own server lifecycle + DB restoration per trial)
5. Swap in OPTIMIZED versions from assets/
6. Modify RESULTS_FILE → "energy_results_bulk_import_optimized.json"
7. Run measure_bulk_import.py again
8. Restore original source files and script
```

The bulk import experiment is different from the others: each trial is a **single long-running operation** (importing 100 recipes) rather than thousands of repeated short calls. The script manages its own server lifecycle — starting, stopping, and restoring the database to a baseline state between each of the 20 trials.

### Running

```bash
# On the deployment server, run all Mealie experiments:
cd path/to/scripts
source path/to/env
export MEALIE_API_TOKEN=<your-token>
python run_all_mealie_measurements.py

# Or run individual experiments:
python measure_compression.py
python measure_bulk_import.py
```

---

## Experiment Parameters

| Parameter | Frappe Experiments | Mealie Compression/Timeline | Mealie Bulk Import |
|-----------|-------------------|----------------------------|-------------------|
| Measure runs per trial | 5,000 | 5,000 / 100 | 1 (single import) |
| Number of trials | 20 | 20 | 20 |
| Cooldown between trials | 120 s | 120 s | 120 s |
| Baseline measurement | 30 s | 30 s | 30 s |
| Scaphandre sampling | 0.5 ms | 0.5 ms | 100 ms |
| CPU pinning | Core 3 | Core 2 | Core 2 |

---

## Raw Results

All experiment results are stored as JSON files in `data/experiment_results_raw/`. Each file contains:

- **`config`** — Experiment parameters (label, runs, trials, etc.)
- **`baseline`** — Idle power measurements (host, pkg, dram power in Watts)
- **`trials`** — Per-trial data (duration, energy in Joules, power in Watts, net energy above baseline)
- **`summary`** — Aggregated statistics (mean, stdev) across all trials

---

## Results Analysis

The `results_analysis/` directory contains Jupyter notebooks for statistical analysis and visualization of the raw experiment data

