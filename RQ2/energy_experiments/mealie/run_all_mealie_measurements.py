#!/usr/bin/env python3
"""
Energy Measurement Orchestrator

Runs all energy measurement scripts sequentially with proper timing and configuration.

Script execution order:
1. Start server once for compression and timeline measurements
2. measure_compression.py (3 times: br, gzip, identity)
3. recipe_timeline_batch.py
4. recipe_timeline_single.py
5. Stop server
6. measure_bulk_import.py (unoptimized version)
7. measure_bulk_import.py (optimized version - after applying git changes)

Each measurement has a 60-second cooldown between runs.
"""

import os
import sys
import time
import shutil
import subprocess
import signal
from pathlib import Path
from datetime import datetime

# ------------------------------------------
# CONFIGURATION
# ------------------------------------------

MEALIE_ROOT = Path("/home/username/mealie/mealie")
VENV_ACTIVATE = "/home/username/mealie/mealie/.venv/bin/activate"
SCRIPTS_DIR = MEALIE_ROOT / "dev/energy/scripts"

# Files to modify for optimization toggle
RECIPE_DATA_SERVICE = MEALIE_ROOT / "mealie/services/recipe/recipe_data_service.py"
RECIPE_BULK_SCRAPER = MEALIE_ROOT / "mealie/services/scraper/recipe_bulk_scraper.py"

DELAY_SECONDS = 120  # 2 minutes between measurements

# ------------------------------------------
# SERVER MANAGEMENT
# ------------------------------------------

def log(message):
    """Print timestamped log message."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] {message}")


def start_server():
    """Start the Mealie server."""
    log("Starting Mealie server...")
    
    # Kill any existing server
    subprocess.run(["pkill", "-f", "task py"], stderr=subprocess.DEVNULL)
    time.sleep(2)
    
    # Start server
    cmd = f"cd {MEALIE_ROOT} && source {VENV_ACTIVATE} && nohup taskset -c 2 task py > server.log 2>&1 &"
    subprocess.run(cmd, shell=True, executable="/bin/bash")
    
    # Wait for server to be ready
    log("Waiting for server to be ready...")
    time.sleep(15)
    log("Server started")


def stop_server():
    """Stop the Mealie server."""
    log("Stopping Mealie server...")
    subprocess.run(["pkill", "-f", "task py"], stderr=subprocess.DEVNULL)
    time.sleep(3)
    log("Server stopped")


# ------------------------------------------
# SCRIPT EXECUTION
# ------------------------------------------

def run_script(script_name, description, env_overrides=None):
    """Run a measurement script and wait for completion."""
    log(f"Starting: {description}")
    
    env = os.environ.copy()
    if env_overrides:
        env.update(env_overrides)
    
    cmd = f"cd {SCRIPTS_DIR} && source {VENV_ACTIVATE} && python {script_name}"
    
    result = subprocess.run(
        cmd,
        shell=True,
        executable="/bin/bash",
        env=env,
        capture_output=False
    )
    
    if result.returncode != 0:
        log(f"WARNING: {script_name} exited with code {result.returncode}")
    else:
        log(f"Completed: {description}")
    
    return result.returncode


def delay(seconds=DELAY_SECONDS):
    """Wait between measurements."""
    log(f"Cooling down for {seconds} seconds...")
    time.sleep(seconds)


# ------------------------------------------
# FILE SWAPPING
# ------------------------------------------

def swap_to_unoptimized():
    """Swap in unoptimized versions of files."""
    log("Swapping to UNOPTIMIZED versions...")
    
    assets_dir = SCRIPTS_DIR / "assets"
    shutil.copy(
        assets_dir / "recipe_data_service_unoptimized.py",
        RECIPE_DATA_SERVICE
    )
    shutil.copy(
        assets_dir / "recipe_bulk_scraper_unoptimized.py",
        RECIPE_BULK_SCRAPER
    )
    
    log("Unoptimized versions installed")


def swap_to_optimized():
    """Swap in optimized versions of files."""
    log("Swapping to OPTIMIZED versions...")
    
    assets_dir = SCRIPTS_DIR / "assets"
    shutil.copy(
        assets_dir / "recipe_data_service_optimized.py",
        RECIPE_DATA_SERVICE
    )
    shutil.copy(
        assets_dir / "recipe_bulk_scraper_optimized.py",
        RECIPE_BULK_SCRAPER
    )
    
    log("Optimized versions installed")



# ------------------------------------------
# MEASUREMENT SEQUENCE
# ------------------------------------------

def modify_compression_script(encoding):
    """Modify measure_compression.py to use specified encoding."""
    script_path = SCRIPTS_DIR / "measure_compression.py"
    
    with open(script_path, 'r') as f:
        content = f.read()
    
    # Replace ENCODING line
    lines = content.split('\n')
    for i, line in enumerate(lines):
        if line.startswith('ENCODING = '):
            lines[i] = f'ENCODING = "{encoding}"  # "identity" | "gzip" | "br"'
            break
    
    with open(script_path, 'w') as f:
        f.write('\n'.join(lines))


def run_compression_measurements():
    """Run compression measurements for all three encodings."""
    encodings = ["br", "gzip", "identity"]
    
    for i, encoding in enumerate(encodings):
        modify_compression_script(encoding)
        run_script(
            "measure_compression.py",
            f"Compression measurement ({encoding})"
        )
        
        if i < len(encodings) - 1:
            delay()


def run_timeline_measurements():
    """Run timeline measurements."""
    run_script("recipe_timeline_batch.py", "Timeline batch measurement")
    delay()
    run_script("recipe_timeline_single.py", "Timeline single measurement")


def run_bulk_import_measurements():
    """Run bulk import measurements (unoptimized and optimized)."""
    # Save current state of files
    log("Saving current state of service files...")
    current_data_service = RECIPE_DATA_SERVICE.read_text()
    current_bulk_scraper = RECIPE_BULK_SCRAPER.read_text()
    
    try:
        # Run unoptimized version
        log("Running bulk import - UNOPTIMIZED version")
        swap_to_unoptimized()
        
        # Modify measure_bulk_import.py to use different result filename
        bulk_import_script = SCRIPTS_DIR / "measure_bulk_import.py"
        with open(bulk_import_script, 'r') as f:
            content = f.read()
        
        original_content = content
        content = content.replace(
            'RESULTS_FILE = "energy_results_bulk_import.json"',
            'RESULTS_FILE = "energy_results_bulk_import_not_optimized.json"'
        )
        
        with open(bulk_import_script, 'w') as f:
            f.write(content)
        
        run_script("measure_bulk_import.py", "Bulk import (unoptimized)")
        
        delay()
        
        # Apply optimizations and run again
        log("Running bulk import - OPTIMIZED version")
        swap_to_optimized()
        
        # Change result filename to optimized
        with open(bulk_import_script, 'r') as f:
            content = f.read()
        
        content = content.replace(
            'RESULTS_FILE = "energy_results_bulk_import_not_optimized.json"',
            'RESULTS_FILE = "energy_results_bulk_import_optimized.json"'
        )
        
        with open(bulk_import_script, 'w') as f:
            f.write(content)
        
        run_script("measure_bulk_import.py", "Bulk import (optimized)")
        
        # Restore original script
        with open(bulk_import_script, 'w') as f:
            f.write(original_content)
        
    finally:
        # Always restore original files
        log("Restoring original service files...")
        RECIPE_DATA_SERVICE.write_text(current_data_service)
        RECIPE_BULK_SCRAPER.write_text(current_bulk_scraper)
        log("Files restored")



# ------------------------------------------
# MAIN
# ------------------------------------------

def main():
    """Run all measurements in sequence."""
    log("=" * 70)
    log("ENERGY MEASUREMENT ORCHESTRATOR")
    log("=" * 70)
    log(f"Scripts directory: {SCRIPTS_DIR}")
    log(f"Delay between measurements: {DELAY_SECONDS}s")
    log("")
    
    try:
        # Phase 1: Compression and Timeline (require server running)
        log("=" * 70)
        log("PHASE 1: Compression and Timeline Measurements")
        log("=" * 70)
        
        start_server()
        
        log("\n--- Compression Measurements (3 runs) ---")
        run_compression_measurements()
        
        delay()
        
        log("\n--- Timeline Measurements (2 runs) ---")
        run_timeline_measurements()
        
        stop_server()
        
        delay()
        
        # Phase 2: Bulk Import (manages its own server)
        log("\n" + "=" * 70)
        log("PHASE 2: Bulk Import Measurements")
        log("=" * 70)
        
        run_bulk_import_measurements()
        
        log("\n" + "=" * 70)
        log("ALL MEASUREMENTS COMPLETE!")
        log("=" * 70)
        log("\nGenerated result files:")
        log("  - energy_results_br.json")
        log("  - energy_results_gzip.json")
        log("  - energy_results_identity.json")
        log("  - energy_results_timeline_batch.json")
        log("  - energy_results_timeline_single.json")
        log("  - energy_results_bulk_import_not_optimized.json")
        log("  - energy_results_bulk_import_optimized.json")
        
    except KeyboardInterrupt:
        log("\nInterrupted by user")
        stop_server()
        sys.exit(1)
    except Exception as e:
        log(f"\nError: {e}")
        import traceback
        traceback.print_exc()
        stop_server()
        sys.exit(1)


if __name__ == "__main__":
    main()
