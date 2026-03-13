#!/usr/bin/env python3
"""
Bulk Import Only - Energy Measurement

Runs only the bulk import measurements (unoptimized and optimized versions).
This script is useful for running just the bulk import tests without repeating
the compression and timeline measurements.
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

MEALIE_ROOT = Path("/home/username/mealie/mealie")
VENV_ACTIVATE = "/home/username/mealie/mealie/.venv/bin/activate"
SCRIPTS_DIR = MEALIE_ROOT / "dev/energy/scripts"

# Files to modify for optimization toggle
RECIPE_DATA_SERVICE = MEALIE_ROOT / "mealie/services/recipe/recipe_data_service.py"
RECIPE_BULK_SCRAPER = MEALIE_ROOT / "mealie/services/scraper/recipe_bulk_scraper.py"

DELAY_SECONDS = 120  # 2 minutes between measurements

# ------------------------------------------
# UTILITIES
# ------------------------------------------

def log(message):
    """Print timestamped log message."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] {message}")


def run_script(script_name, description):
    """Run a measurement script and wait for completion."""
    log(f"Starting: {description}")
    
    env = os.environ.copy()
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
        return False
    else:
        log(f"Completed: {description}")
        return True


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
# MAIN
# ------------------------------------------

def main():
    """Run bulk import measurements."""
    log("=" * 70)
    log("BULK IMPORT ENERGY MEASUREMENTS")
    log("=" * 70)
    log(f"Scripts directory: {SCRIPTS_DIR}")
    log("")
    
    # Save current state of files
    log("Saving current state of service files...")
    current_data_service = RECIPE_DATA_SERVICE.read_text()
    current_bulk_scraper = RECIPE_BULK_SCRAPER.read_text()
    
    try:
        # Run unoptimized version
        log("\n--- UNOPTIMIZED VERSION ---")
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
        
        success1 = run_script("measure_bulk_import.py", "Bulk import (unoptimized)")
        
        delay()
        
        # Run optimized version
        log("\n--- OPTIMIZED VERSION ---")
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
        
        success2 = run_script("measure_bulk_import.py", "Bulk import (optimized)")
        
        # Restore original script
        with open(bulk_import_script, 'w') as f:
            f.write(original_content)
        
        log("\n" + "=" * 70)
        if success1 and success2:
            log("BULK IMPORT MEASUREMENTS COMPLETE!")
        else:
            log("BULK IMPORT MEASUREMENTS COMPLETED WITH WARNINGS")
        log("=" * 70)
        log("\nGenerated result files:")
        log("  - energy_results_bulk_import_not_optimized.json")
        log("  - energy_results_bulk_import_optimized.json")
        
    except KeyboardInterrupt:
        log("\nInterrupted by user")
        sys.exit(1)
    except Exception as e:
        log(f"\nError: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        # Always restore original files
        log("\nRestoring original service files...")
        RECIPE_DATA_SERVICE.write_text(current_data_service)
        RECIPE_BULK_SCRAPER.write_text(current_bulk_scraper)
        log("Files restored")


if __name__ == "__main__":
    main()
