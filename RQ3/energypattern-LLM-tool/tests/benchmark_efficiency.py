
import sys
import os
from pathlib import Path

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Load environment variables
from dotenv import load_dotenv
load_dotenv()

from app.ast_parser import parse_file
from app.graph import is_worth_analyzing

def benchmark_efficiency():
    print("=== BENCHMARK: Smart Filtering efficiency ===")
    
    test_dir = Path("tests/inefficient_code_examples")
    files = list(test_dir.glob("*.py"))
    
    total_units = 0
    kept_units = 0
    skipped_units = 0
    
    for f in files:
        units = parse_file(str(f))
        for u in units:
            total_units += 1
            should_keep = is_worth_analyzing(u)
            
            status = "KEEP" if should_keep else "SKIP"
            tags = ",".join(u.suspicious_tags) if u.suspicious_tags else "-"
            
            print(f"[{status}] {u.name:<20} | Comp: {u.complexity:<2} | LOC: {u.loc:<3} | Tags: {tags}")
            
            if should_keep:
                kept_units += 1
            else:
                skipped_units += 1
                
    reduction = (skipped_units / total_units) * 100 if total_units else 0
    print("-" * 60)
    print(f"Total Units: {total_units}")
    print(f"Kept Units:  {kept_units}")
    print(f"Skipped:     {skipped_units}")
    print(f"Reduction:   {reduction:.1f}% LLM Calls Saved")
    print("-" * 60)

if __name__ == "__main__":
    benchmark_efficiency()
