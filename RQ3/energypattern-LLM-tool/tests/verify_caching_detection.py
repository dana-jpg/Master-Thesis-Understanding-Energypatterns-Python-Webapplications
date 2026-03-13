
import sys
import os
from dotenv import load_dotenv

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

load_dotenv()

from app.graph import build_graph, GraphState

def verify_caching_detection():
    print("=== VERIFICATION: Caching Detection ===")
    
    app = build_graph()
    test_file = os.path.abspath("tests/inefficient_code_examples/caching_issue.py")
    
    initial_state = GraphState(
        files=[test_file],
        input_type="path"
    )
    
    print(f"Analyzing {test_file}...")
    final_state = app.invoke(initial_state)
    
    findings = final_state.get("findings", [])
    print(f"\nFound {len(findings)} issues.")
    
    caching_detected = False
    
    for f in findings:
        print(f"\nFunction: {f.function_name}")
        print(f"Issue: {f.issue}")
        print(f"Explanation: {f.explanation[:100]}...")
        
        text_to_check = (f.issue + f.explanation + (f.patch or "")).lower()
        if "cache" in text_to_check or "caching" in text_to_check or "memoization" in text_to_check:
            caching_detected = True
            print("Caching suggestion found!")
            
    if caching_detected:
        print("\nSUCCESS: Caching opportunity detected.")
    else:
        print("\nFAILURE: No caching suggestion found.")
        sys.exit(1)

if __name__ == "__main__":
    verify_caching_detection()
