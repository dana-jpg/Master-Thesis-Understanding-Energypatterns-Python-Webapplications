
import sys
import os
from dotenv import load_dotenv

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

load_dotenv()

from app.graph import build_graph, GraphState

def verify_modes():
    print("=== VERIFICATION: Analysis Modes ===")
    
    test_file = os.path.abspath("tests/inefficient_code_examples/caching_issue.py")
    
    # 1. Test Suggestion Mode (Default)
    print("\n--- Testing Suggestion Mode ---")
    state_sugg = GraphState(
        files=[test_file],
        input_type="path",
        analysis_mode="suggestion"
    )
    app_sugg = build_graph()
    final_sugg = app_sugg.invoke(state_sugg)
    
    findings_sugg = final_sugg.get("findings", [])
    if not findings_sugg:
        print(" No findings in suggestion mode!")
    else:
        has_patch = any(f.patch is not None for f in findings_sugg)
        if has_patch:
            print(f" Suggestion Mode: Found {len(findings_sugg)} issues with patches.")
        else:
            print(" Suggestion Mode: Found issues but NO patches!")

    # 2. Test Detection Mode
    print("\n--- Testing Detection Mode ---")
    state_detect = GraphState(
        files=[test_file],
        input_type="path",
        analysis_mode="detection"
    )
    app_detect = build_graph()
    final_detect = app_detect.invoke(state_detect)
    
    findings_detect = final_detect.get("findings", [])
    if not findings_detect:
        print(" No findings in detection mode!")
    else:
        has_patch = any(f.patch is not None for f in findings_detect)
        if not has_patch:
            print(f" Detection Mode: Found {len(findings_detect)} issues without patches.")
            
            # Verify problematic_code is present
            has_code = any(f.problematic_code is not None for f in findings_detect)
            if has_code:
                 print(f" Detection Mode: Found {len(findings_detect)} findings with problematic_code.")
                 for f in findings_detect:
                     code_len = len(f.problematic_code) if f.problematic_code else 0
                     print(f"   - {f.function_name}: Code len={code_len} chars")
            else:
                 print(" Detection Mode: Missing problematic_code!")
        else:
            print(" Detection Mode: Found issues WITH patches (Should be None)!")
            for f in findings_detect:
                if f.patch:
                    print(f"   - {f.function_name}: Patch len={len(f.patch)}")

if __name__ == "__main__":
    verify_modes()
