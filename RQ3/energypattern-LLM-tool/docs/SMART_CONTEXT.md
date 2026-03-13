# Smart Context System

## How It Works

### 1. The Symbol Table
During the parsing phase (`extract_units`), every detected function and class is registered in a global `SymbolTable`.

*   **Key**: Function Name (e.g., `calculate_metrics`)
*   **Value**: List of `CodeUnit` objects (code, location, file path)

### 2. Dependency Discovery
For every function we analyze, the AST parser extracts a list of `dependencies` (names of functions called within the body).

*   Python: `ast.Call` nodes.
*   JS/Java/C++: Regex or simplified parsing heuristics.

### 3. Resolution Logic (`ContextBuilder`)

When analyzing `Function A`:

1.  **Import Resolution**: We check if the dependencies are explicitly imported.
    *   If `json.dumps` is called, we see `import json`. We know `dumps` comes from `json` (external) or `json.py` (internal).
    *   This prevents namespace collisions (e.g., `utils.save` vs `db.save`).
2.  **Filter External Libraries**:
    *   If a function is NOT found in our `SymbolTable` and NOT a local project file, we treat it as an external library and ignore it.
3.  **Class Context Injection**:
    *   If `Function A` is a method of `Class X`, we automatically find `Class X.__init__` and inject it.
    *   This reveals member variable definitions (e.g., `self.database_url`) that are critical for understanding the method's cost.




