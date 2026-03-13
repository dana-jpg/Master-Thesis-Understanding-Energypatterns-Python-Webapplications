import os
import json
import asyncio
import glob
from concurrent.futures import ThreadPoolExecutor
from typing import List, Dict, Any

from app.graph import build_graph, GraphState

# Configurations
TEST_DIR = os.path.dirname(os.path.abspath(__file__))
RESULTS_FILE = os.path.join(TEST_DIR, "test_results.json")

class TestRunner:
    def __init__(self):
        self.graph = build_graph()
        self.results = []
        self.stats = {"passed": 0, "failed": 0, "total": 0}

    def run_single_test(self, case: Dict[str, Any], filename: str) -> Dict[str, Any]:
        """Run a single test case."""
        print(f"Running test: {case['id']} ({filename})")
        
        state = GraphState(
            input_type='code',
            code_content=case['code'],
            analysis_mode='detection'
        )
        
        try:
            # Invoke graph
            final_state_dict = self.graph.invoke(state, {"recursion_limit": 100})
            final_state = GraphState(**final_state_dict)
            findings = final_state.findings
            
            # Verify results
            expected_category = case.get('expected_category')
            expected_issue_substr = case.get('expected_issue_substr') # Optional substring check
            
            found_category = None
            passed = False
            failure_reason = ""
            
            if not findings:
                if expected_category is None: # We expected no issues
                    passed = True
                else:
                    failure_reason = "No issues found, but expected one."
            else:
                # Check if any finding matches the expected category
                matches = []
                for f in findings:
                    if f.taxonomy_category == expected_category:
                        matches.append(f)
                
                if matches:
                    found_category = matches[0].taxonomy_category
                    if expected_issue_substr:
                         # Verify issue description
                         if any(expected_issue_substr.lower() in f.issue.lower() for f in matches):
                             passed = True
                         else:
                             failure_reason = f"Category match, but issue text didn't contain '{expected_issue_substr}'"
                    else:
                        passed = True
                else:
                    # Provide details on what WAS found
                    found_cats = [f.taxonomy_category for f in findings]
                    failure_reason = f"Expected category {expected_category}, found: {found_cats}"
                    
            result = {
                "id": case['id'],
                "filename": filename,
                "passed": passed,
                "expected_category": expected_category,
                "found_category": found_category,
                "failure_reason": failure_reason,
                "findings": [f.to_dict() for f in findings]
            }
            
            return result

        except Exception as e:
            return {
                "id": case['id'],
                "filename": filename,
                "passed": False,
                "expected_category": case.get('expected_category'),
                "found_category": None,
                "failure_reason": f"Exception during execution: {str(e)}",
                "findings": []
            }

    def run_all(self):
        """Run all test files matching cases_*.json."""
        test_files = glob.glob(os.path.join(TEST_DIR, "cases_*.json"))
        all_cases = []
        
        for tf in test_files:
            with open(tf, 'r') as f:
                cases = json.load(f)
                for c in cases:
                    all_cases.append((c, os.path.basename(tf)))
        
        self.stats["total"] = len(all_cases)
        print(f"Found {len(all_cases)} test cases in {len(test_files)} files.")
    
        for case, filename in all_cases:
            res = self.run_single_test(case, filename)
            self.results.append(res)
            if res['passed']:
                self.stats["passed"] += 1
                print(f"PASS: {case['id']}")
            else:
                self.stats["failed"] += 1
                print(f"FAIL: {case['id']} - {res['failure_reason']}")

        # Report
        print("\n" + "="*40)
        print(f"Test Run Complete")
        print(f"Total: {self.stats['total']}")
        print(f"Passed: {self.stats['passed']}")
        print(f"Failed: {self.stats['failed']}")
        print("="*40)
        
        with open(RESULTS_FILE, 'w') as f:
            json.dump({
                "stats": self.stats,
                "results": self.results
            }, f, indent=2)
            print(f"Detailed results saved to {RESULTS_FILE}")

if __name__ == "__main__":
    runner = TestRunner()
    runner.run_all()
