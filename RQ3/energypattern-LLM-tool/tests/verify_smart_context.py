import sys
import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Add project root to sys.path to allow importing 'app'
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.graph import build_graph, GraphState
from pprint import pprint

def verify_smart_context():
    print("=== Verifying Smart Context Analysis (Multi-File) ===")
    
    # Analyze the reproduction project directory
    repro_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), 'inefficient_code_examples'))
    
    graph = build_graph()
    
    # input_type="path" allows load_repo_files to crawl the directory
    state = GraphState(
        input_type="path",
        repo_path=repro_dir
    )
    
    print(f"Running analysis on {repro_dir}...")
    result_dict = graph.invoke(state)
    result = GraphState(**result_dict)
    
    findings = result.findings
    print(f"Total findings: {len(findings)}")
    
    # Check for specific detections that require context
    
    # 1. Detection of 'computation(2)' being expensive in 'compute_many_times'
    found_computation_issue = False
    for f in findings:
        if f.function_name == "compute_many_times" and ("computation" in f.explanation.lower() or "loop" in f.explanation.lower() or "repeated" in f.explanation.lower()):
            found_computation_issue = True
            print("[PASS] Detected repeated expensive computation in 'compute_many_times'")
            print(f"   > Explanation: {f.explanation[:100]}...")
            break
            
    if not found_computation_issue:
        print("[FAIL] Did not detect expensive computation in 'compute_many_times'")
        
    # 2. Detection of busy wait in 'wait_for_flag'
    found_busy_wait = False
    for f in findings:
        if f.function_name == "wait_for_flag" and ("sleep" in f.patch or "time.sleep" in f.patch or "wait" in f.explanation.lower()):
            found_busy_wait = True
            print("[PASS] Detected busy wait in 'wait_for_flag'")
            break
            
    if not found_busy_wait:
        print("[FAIL] Did not detect busy wait in 'wait_for_flag'")

    # 3. Network call retry loop
    found_network_retry = False
    for f in findings:
        if f.function_name == "send_with_retry" and ("backoff" in f.explanation.lower() or "sleep" in f.patch):
            found_network_retry = True
            print("[PASS] Detected missing backoff in 'send_with_retry'")
            break
            
    if not found_network_retry:
        print("[FAIL] Did not detect missing backoff in 'send_with_retry'")

    print("=== Verification Complete ===")

if __name__ == "__main__":
    verify_smart_context()
