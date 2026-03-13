# AST Analysis Strategy

The system (`app/ast_parser.py`) uses a factory pattern to select the correct parser based on file extension.

### Python (`ast` module)
We use Python's built-in `ast` library for full fidelity parsing.
*   **Recursive Extraction**: We perform a recursive walk (`_visit_nodes`) to track scope and class hierarchy.
*   **Class Awareness**: Methods are linked to their parent classes, allowing context injection of `__init__`.
*   **Import Tracking**: We capture `import` statements to correctly resolve where dependencies come from.
*   **Dependencies**: We traverse the function body to find `Call` nodes to build the dependency graph.

### JavaScript / TypeScript (`esprima`)
We use `esprima` (via Python bindings) to parse JS/TS.
*   **Extraction**: distinct handling for `FunctionDeclaration` and `FunctionExpression`.
*   **Fallback**: If `esprima` fails (e.g., complex TSX syntax), we gracefully fallback to whole-file analysis.

### Java (`javalang`)
We use `javalang` to identify method declarations.
*   **Challenge**: `javalang` does not provide end line numbers.
*   **Solution**: We use a brace-counting heuristic (`_find_method_end`) starting from the method declaration line to determine the scope.

### C/C++ (`tree-sitter`)
We rely on `tree-sitter` for robust parsing of C/C++.
*   **Extraction**: We look for `function_definition` nodes.
*   **Declarators**: recursive unpacking of C-style declarators to find the actual function name.

## Efficiency Metrics

We compute two key metrics to decide *if* a function is worth analyzing.

### 1. Cyclomatic Complexity
A quantitative measure of the number of linearly independent paths through a program's source code.

*   **Base**: 1
*   **New Path**: +1 for every `if`, `while`, `for`, `except`, `case`, `&&`, `||`.

**Usage**: We sort the analysis queue by Complexity (Descending). High complexity functions are statistically more likely to contain inefficiencies (nested loops, complex branching).

### 2. Lines of Code (LOC)
Count of non-empty, non-comment lines.

**Usage**: Very short functions (e.g., getters/setters, `< 15` LOC) are often skipped unless they contain suspicious tags.

## Suspicious Tagging

We use regex and AST traversal to "tag" functions with potential energy hotspots. If a function has a tag, it bypasses the complexity filter and is **always** analyzed.

| Tag | Triggers (Regex/AST) | Why? |
|-----|----------------------|------|
| `LOOP` | `for`, `while`, `map`, `reduce` | Iteration is the #1 source of CPU energy consumption. |
| `IO` | `read`, `write`, `socket`, `http`, `fetch`, `open` | Blocking I/O often leads to inefficient waiting or polling. |
| `WAIT` | `sleep`, `wait`, `delay`, `timeout` | explicit delays are often arbitrary and wasteful ("Busy Waiting"). |
| `DB` | `sql`, `query`, `cursor`, `execute`, `select` | Database roundtrips are expensive; N+1 queries are a common green coding issue. |
| `THREAD` | `async`, `await`, `thread`, `future` | Concurrency issues can lead to race conditions or resource contention. |
| `COMPUTATION` | `numpy`, `pandas`, `matrix`, `calculate` | Heavy math operations that might benefit from vectorization. |



