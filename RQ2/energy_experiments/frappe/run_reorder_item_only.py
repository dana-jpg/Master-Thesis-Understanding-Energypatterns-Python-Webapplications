#!/usr/bin/env python3
"""
Frappe/ERPNext Energy Measurement Orchestrator

Runs all 6 ERPNext energy measurement experiments sequentially,
toggling between unoptimized and optimized versions using asset file swapping.

Each experiment runs twice (unoptimized → optimized) with 60s delays between runs.
"""

import os
import sys
import time
import shutil
import subprocess
from pathlib import Path
from datetime import datetime

# ------------------------------------------
# CONFIGURATION
# ------------------------------------------

SCRIPTS_DIR = Path("/home/username/frappe/apps/energy_tests/scripts")
ASSETS_DIR = SCRIPTS_DIR / "assets"
ERPNEXT_ROOT = Path("/home/username/frappe/apps/erpnext/erpnext")
FRAPPE_VENV = "/home/username/frappe/env/bin/activate"

DELAY_SECONDS = 120  # 2 minutes between measurements
CPU_ID = 3  # CPU to pin measurement scripts to

# File mappings: (asset_basename, target_path_relative_to_erpnext)
FILE_MAPPINGS = [
    ("item", "stock/doctype/item/item.py"),
    ("get_item_details", "stock/get_item_details.py"),
    ("item_wise_sales_register", "accounts/report/item_wise_sales_register/item_wise_sales_register.py"),
    ("gross_profit", "accounts/report/gross_profit/gross_profit.py"),
    ("reorder_item", "stock/reorder_item.py"),
    ("accounts_controller", "controllers/accounts_controller.py"),
]

# Experiments: (script_name, description, asset_basename)
EXPERIMENTS = [
    ("measure_reorder_item.py", "Reorder Item", "reorder_item"),
]

# ------------------------------------------
# UTILITIES
# ------------------------------------------

def log(message):
    """Print timestamped log message."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] {message}", flush=True)


def delay(seconds=DELAY_SECONDS):
    """Wait between measurements."""
    log(f"Cooling down for {seconds} seconds...")
    time.sleep(seconds)


# ------------------------------------------
# FILE MANAGEMENT
# ------------------------------------------

def get_file_path(asset_basename):
    """Get the target file path for the given asset basename."""
    for basename, rel_path in FILE_MAPPINGS:
        if basename == asset_basename:
            return ERPNEXT_ROOT / rel_path
    raise ValueError(f"Unknown asset basename: {asset_basename}")


def swap_file(asset_basename, version):
    """Swap in the specified version (optimized or unoptimized)."""
    asset_file = ASSETS_DIR / f"{asset_basename}_{version}.py"
    target_file = get_file_path(asset_basename)
    
    if not asset_file.exists():
        raise FileNotFoundError(f"Asset file not found: {asset_file}")
    
    log(f"Swapping to {version} version: {target_file.name}")
    shutil.copy(asset_file, target_file)


def save_current_state():
    """Save current state of all files before modifications."""
    log("Saving current state of all files...")
    saved_state = {}
    
    for basename, _ in FILE_MAPPINGS:
        target_file = get_file_path(basename)
        if target_file.exists():
            saved_state[basename] = target_file.read_text()
    
    return saved_state


def restore_state(saved_state):
    """Restore files to their original state."""
    log("Restoring original file state...")
    
    for basename, content in saved_state.items():
        target_file = get_file_path(basename)
        target_file.write_text(content)
    
    log("Files restored")


# ------------------------------------------
# SCRIPT EXECUTION
# ------------------------------------------

def run_script(script_name, version, description):
    """Run a measurement script with the specified file version."""
    log(f"Starting: {description} ({version})")
    
    experiment_name = script_name.replace("measure_", "").replace(".py", "")
    results_filename = f"energy_results_{experiment_name}_{version}.json"
    
    # Run the script with frappe venv and CPU pinning
    # Pass results filename via environment variable
    cmd = f"cd {SCRIPTS_DIR} && source {FRAPPE_VENV} && export ENERGY_RESULTS_FILE={results_filename} && taskset -c {CPU_ID} python -u {script_name}"
    
    result = subprocess.run(
        cmd,
        shell=True,
        executable="/bin/bash",
        capture_output=False
    )
    
    if result.returncode != 0:
        log(f"WARNING: {script_name} ({version}) exited with code {result.returncode}")
        return False
    else:
        log(f"Completed: {description} ({version})")
        return True


# ------------------------------------------
# MAIN
# ------------------------------------------

def main():
    """Run all experiments in sequence."""
    log("=" * 70)
    log("FRAPPE/ERPNEXT ENERGY MEASUREMENT ORCHESTRATOR")
    log("=" * 70)
    log(f"Scripts directory: {SCRIPTS_DIR}")
    log(f"Assets directory: {ASSETS_DIR}")
    log(f"CPU pinning: CPU {CPU_ID}")
    log(f"Delay between measurements: {DELAY_SECONDS}s")
    log("")
    
    # Save current state
    saved_state = save_current_state()
    
    try:
        for idx, (script_name, description, asset_basename) in enumerate(EXPERIMENTS):
            log(f"\n{'=' * 70}")
            log(f"EXPERIMENT {idx + 1}/6: {description}")
            log(f"{'=' * 70}")
            
            # Run unoptimized version
            log(f"\n--- UNOPTIMIZED VERSION ---")
            swap_file(asset_basename, "unoptimized")
            run_script(script_name, "unoptimized", description)
            
            delay()
            
            # Run optimized version
            log(f"\n--- OPTIMIZED VERSION ---")
            swap_file(asset_basename, "optimized")
            run_script(script_name, "optimized", description)
            
            # Delay before next experiment (except after the last one)
            if idx < len(EXPERIMENTS) - 1:
                delay()
        
        log("\n" + "=" * 70)
        log("ALL MEASUREMENTS COMPLETE!")
        log("=" * 70)
        log("\nGenerated result files (12 total):")
        for script_name, _, _ in EXPERIMENTS:
            experiment_name = script_name.replace("measure_", "").replace(".py", "")
            log(f"  - energy_results_{experiment_name}_unoptimized.json")
            log(f"  - energy_results_{experiment_name}_optimized.json")
        
    except KeyboardInterrupt:
        log("\nInterrupted by user")
        sys.exit(1)
    except Exception as e:
        log(f"\nError: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        # Always restore files
        restore_state(saved_state)


if __name__ == "__main__":
    main()
