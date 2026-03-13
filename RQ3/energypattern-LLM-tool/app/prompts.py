ENERGY_ANALYSIS_PROMPT = """
You are a software sustainability expert.

Analyze the following code for LOCAL, LINE-LEVEL energy inefficiencies.

Rules:
- Do NOT suggest changing the algorithm.
- Do NOT suggest replacing the implementation with another algorithm.
- Only suggest small, local code changes within the existing structure.
- The change MUST be applicable as a patch to this file.
- If the only possible improvement is to change the algorithm, return NO_ISSUE.

If no local issue exists, return exactly:
{{"result": "NO_ISSUE"}}

Otherwise return valid JSON with this schema:
{{
  "result": "ISSUE",
  "issue": string,
  "explanation": string,
  "patch": string
}}

The "patch" MUST be a unified diff that:
- Applies to this file
- Modifies only the minimal necessary lines
- Does NOT remove or replace the entire function

Do not include any text outside the JSON.

Code:
```{code}
"""

# AST-enhanced prompt (used when AST metadata is available)
ENERGY_ANALYSIS_PROMPT_WITH_AST = """
You are a software sustainability expert analyzing {language} code.

Code Unit Details:
- Function/Method: {function_name}
- File: {file_path}
- Lines: {start_line}-{end_line}
- Cyclomatic Complexity: {complexity}
- Lines of Code: {loc}

Analyze this code unit for LOCAL, LINE-LEVEL energy inefficiencies.

Rules:
- Do NOT suggest changing the algorithm.
- Do NOT suggest replacing the implementation with another algorithm.
- Only suggest small, local code changes within the existing structure.
- The change MUST be applicable as a patch to this specific function.
- If the only possible improvement is to change the algorithm, return NO_ISSUE.
- Focus on inefficiencies like: unnecessary computations, inefficient loops, redundant operations, poor data structure usage.
- Look for opportunities to introduce CACHING (e.g. lru_cache, memoization) for expensive, repeated operations.
- Look for Database inefficiencies like N+1 queries or un-batched writes.

If no local issue exists, return exactly:
{{"result": "NO_ISSUE"}}

Otherwise return valid JSON with this schema:
{{
  "result": "ISSUE",
  "issue": string (brief description),
  "explanation": string (detailed explanation of the energy impact),
  "patch": string (unified diff format)
}}

The "patch" MUST be a unified diff that:
- References the correct line numbers ({start_line}-{end_line})
- Modifies only the minimal necessary lines
- Does NOT remove or replace the entire function
- Includes proper context lines

Do not include any text outside the JSON.

Code:
```
{code}
```
"""

# Context-aware prompt includes related code (dependencies)
ENERGY_ANALYSIS_PROMPT_WITH_CONTEXT = """
You are a software sustainability expert analyzing {language} code.

Code Unit Details:
- Function/Method: {function_name}
- File: {file_path}
- Lines: {start_line}-{end_line}
- Cyclomatic Complexity: {complexity}

{related_code}

Analyze the TARGET code unit below for energy inefficiencies.
Use the DEPENDENCIES provided above to understand the hidden costs of function calls.

Rules:
- Focus on: repeated expensive calls, busy waiting, infinite loops without backoff, resource contention.
- Identify opportunities to introduce CACHING (e.g. lru_cache, memoization) for expensive, repeated operations (e.g. DB calls).
- Identify Database inefficiencies like N+1 queries.
- Do NOT suggest changing the algorithm.
- Do NOT suggest replacing the implementation with another algorithm.
- Only suggest small, local code changes within the existing structure.
- The change MUST be applicable as a patch to this specific function.
- If the only possible improvement is to change the algorithm, return NO_ISSUE.

If no local issue exists, return exactly:
{{"result": "NO_ISSUE"}}

Otherwise return valid JSON with this schema:
{{
  "result": "ISSUE",
  "issue": string (brief description),
  "explanation": string (detailed explanation of the energy impact, referencing dependencies if relevant),
  "patch": string (unified diff format)
}}

The "patch" MUST be a unified diff that:
- References the correct line numbers ({start_line}-{end_line})
- Modifies only the minimal necessary lines
- Does NOT remove or replace the entire function

Do not include any text outside the JSON.

TARGET Code:
```
{code}
```
"""

# ------------------------------------------------------------------
# Detection-Only Prompts (No Patch Generation)
# ------------------------------------------------------------------

ENERGY_ANALYSIS_PROMPT_DETECTION_ONLY = """
You are a software sustainability expert.

Analyze the following code for LOCAL, LINE-LEVEL energy inefficiencies.

Rules:
- Focus on: unnecessary computations, inefficient loops, redundant operations, poor data structure usage.
- Look for opportunities to introduce CACHING (e.g. lru_cache, memoization).
- Look for Database inefficiencies like N+1 queries.
- Do NOT generate a patch.
- If no local issue exists, return exactly:
{{"result": "NO_ISSUE"}}

Otherwise return valid JSON with this schema:
{{
  "result": "ISSUE",
  "issue": string (brief description),
  "explanation": string (detailed explanation of the energy impact)
}}

Do not include any text outside the JSON.

Code:
```{code}
```
"""

ENERGY_ANALYSIS_PROMPT_WITH_AST_DETECTION_ONLY = """
You are a software sustainability expert analyzing {language} code.

Code Unit Details:
- Function/Method: {function_name}
- File: {file_path}
- Lines: {start_line}-{end_line}
- Cyclomatic Complexity: {complexity}
- Lines of Code: {loc}

Analyze this code unit for LOCAL, LINE-LEVEL energy inefficiencies.

Rules:
- Focus on: unnecessary computations, inefficient loops, redundant operations, poor data structure usage.
- Look for opportunities to introduce CACHING (e.g. lru_cache, memoization).
- Look for Database inefficiencies like N+1 queries.
- Do NOT generate a patch.
- If no local issue exists, return exactly:
{{"result": "NO_ISSUE"}}

Otherwise return valid JSON with this schema:
{{
  "result": "ISSUE",
  "issue": string (brief description),
  "explanation": string (detailed explanation of the energy impact)
}}

Do not include any text outside the JSON.

Code:
```
{code}
```
"""

ENERGY_ANALYSIS_PROMPT_WITH_CONTEXT_DETECTION_ONLY = """
You are a software sustainability expert analyzing {language} code.

Code Unit Details:
- Function/Method: {function_name}
- File: {file_path}
- Lines: {start_line}-{end_line}
- Cyclomatic Complexity: {complexity}

{related_code}

Analyze the TARGET code unit below for energy inefficiencies.
Use the DEPENDENCIES provided above to understand the hidden costs of function calls.

Rules:
- Focus on: repeated expensive calls, busy waiting, infinite loops without backoff, resource contention.
- Identify opportunities to introduce CACHING (e.g. lru_cache, memoization).
- Identify Database inefficiencies like N+1 queries.
- Do NOT generate a patch.

If no local issue exists, return exactly:
{{"result": "NO_ISSUE"}}

Otherwise return valid JSON with this schema:
{{
  "result": "ISSUE",
  "issue": string (brief description),
  "explanation": string (detailed explanation of the energy impact, referencing dependencies if relevant)
}}

Do not include any text outside the JSON.

TARGET Code:
```
{code}
```
"""

# ------------------------------------------------------------------
# Pre-filter Prompt (for fast 8B model)
# ------------------------------------------------------------------

PREFILTER_PROMPT = """
Quickly assess this {language} function for energy inefficiency red flags.

Function: {function_name}
Complexity: {complexity}
Tags: {suspicious_tags}

Code:
```
{code}
```

Reply with ONLY ONE WORD:
- "PASS" ONLY if the code is trivial (e.g. getters/setters, simple logic) with NO potential issues.
- "FLAG" if you see ANY potential energy waste (be paranoid):
  * Busy loops / polling without sleep
  * Repeated expensive calls that could be cached
  * Heavy object creation in loops (e.g. regex compilation)
  * N+1 database patterns
  * String concatenation in loops
  * Unnecessary recomputation
  * Unbounded async concurrency (missing semaphore/limit)
  * Deepcopy in loops

One word only: PASS or FLAG
"""

# ------------------------------------------------------------------
# RAG-Enhanced Prompt with Examples (for taxonomy-aware analysis)
# ------------------------------------------------------------------

ENERGY_ANALYSIS_WITH_EXAMPLES = """
You are a software sustainability expert analyzing {language} code.

## Code Unit Details
- Function/Method: {function_name}
- File: {file_path}
- Lines: {start_line}-{end_line}
- Cyclomatic Complexity: {complexity}

## Valid Taxonomy Categories
You MUST pick from these categories. Format: prefix: leaf_name | leaf_name | ...
{valid_categories}

When responding, use the FULL ID format: prefix_layer.sub.leaf_name (e.g., data_layer.efficient_access.batch_operations)

## Reference Examples
The following are REAL examples of energy inefficiencies similar to what you might find.
Study these patterns - if you see something similar in the target code, suggest a similar fix.

{examples_section}

---

## Related Code (Dependencies)
{related_code}

## Analysis Task
Analyze the TARGET code below for energy inefficiencies.
Use the reference examples above to guide your analysis - look for similar patterns.
Use the DEPENDENCIES to understand the hidden costs of function calls.

### Rules
- Focus on: N+1 queries, repeated expensive calls, unbounded concurrency, missing caching, lazy loading opportunities
- Only suggest LOCAL code changes (no algorithm replacements)
- If you find an issue, classify it using one of the VALID TAXONOMY CATEGORIES listed above
- The change MUST be applicable as a patch to this specific function
- If no local issue exists, return NO_ISSUE

### Response Format

If no local issue exists, return exactly:
{{"result": "NO_ISSUE"}}

Otherwise return valid JSON with this schema:
{{
  "result": "ISSUE",
  "taxonomy_category": string (MUST be a full category ID from the valid list above, e.g., "data_layer.efficient_access.batch_operations"),
  "issue": string (brief description),
  "explanation": string (detailed explanation, reference similar examples if applicable),
  "similar_to_example": string (example ID if similar to a reference example, else null),
  "problematic_code": string (the specific problematic lines),
  "patch": string (unified diff format)
}}

The "patch" MUST be a unified diff that:
- References the correct line numbers ({start_line}-{end_line})
- Modifies only the minimal necessary lines
- Does NOT remove or replace the entire function

Do not include any text outside the JSON.

## TARGET Code
```
{code}
```
"""

ENERGY_ANALYSIS_WITH_EXAMPLES_DETECTION_ONLY = """
You are a software sustainability expert analyzing {language} code.

## Code Unit Details
- Function/Method: {function_name}
- File: {file_path}
- Lines: {start_line}-{end_line}
- Cyclomatic Complexity: {complexity}

## Valid Taxonomy Categories
You MUST pick from these categories. Format: prefix: leaf_name | leaf_name | ...
{valid_categories}

When responding, use the FULL ID format: prefix_layer.sub.leaf_name (e.g., data_layer.efficient_access.batch_operations)

## Reference Examples
The following are REAL examples of energy inefficiencies similar to what you might find.
Study these patterns - if you see something similar in the target code, identify it.

{examples_section}

---

## Related Code (Dependencies)
{related_code}

## Analysis Task
Analyze the TARGET code below for energy inefficiencies.
Use the reference examples above to guide your analysis - look for similar patterns.

### Rules
- Focus on: N+1 queries, repeated expensive calls, unbounded concurrency, missing caching
- Classify any issue using one of the VALID TAXONOMY CATEGORIES listed above
- Do NOT generate a patch
- If no local issue exists, return NO_ISSUE

### Response Format

If no local issue exists, return exactly:
{{"result": "NO_ISSUE"}}

Otherwise return valid JSON with this schema:
{{
  "result": "ISSUE",
  "taxonomy_category": string (MUST be a full category ID from the valid list above),
  "issue": string (brief description),
  "explanation": string (detailed explanation, reference similar examples if applicable),
  "similar_to_example": string (example ID if similar to a reference example, else null),
  "problematic_code": string (the specific lines that are problematic)
}}

Do not include any text outside the JSON.

## TARGET Code
```
{code}
```
"""