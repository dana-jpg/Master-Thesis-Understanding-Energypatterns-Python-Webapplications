# RQ3: Antipattern Detector

## Installation

```bash
# Activate your virtual environment
source /path/to/venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

## Usage

```bash
python server.py
```


## Architecture

```
load_repo → extract_units → analyze_unit (pre-filter → RAG retrieval → deep analysis) → summarize
```

### Documentation

For detailed technical information, please refer to the `docs/` directory:

-  **[Architecture](docs/ARCHITECTURE.md)** - System design, LangGraph workflow, and Caching.
-  **[AST Analysis Strategy](docs/AST_ANALYSIS_STRATEGY.md)** - How parsing, complexity metrics, and suspicious tagging work.
-  **[Smart Context](docs/SMART_CONTEXT.md)** - Deep dive into dependency injection and the symbol table.
-  **[RAG Examples](docs/RAG_EXAMPLES.md)** - How before/after code examples are retrieved and injected via ChromaDB.

### Components

- **ast_parser.py** - Multi-language AST parser with complexity calculation
- **graph.py** - LangGraph workflow orchestration (includes RAG retrieval and tiered LLM logic)
- **models.py** - Data models for findings and code units
- **prompts.py** - LLM prompts (basic, AST-enhanced, context-aware, and RAG-enhanced with examples)
- **cache.py** - Function-level caching system
- **repo_loader.py** - Repository file discovery
- **example_store.py** - ChromaDB-backed vector store for before/after code examples (RAG)
- **taxonomy.py** - Hierarchical taxonomy of energy-efficient coding practices
- **context.py** - Smart context builder for dependency injection

## Supported Languages

| Language | Parser | Features |
|----------|--------|----------|
| Python | Built-in `ast` | Full support with complexity |
| JavaScript/TypeScript | `esprima` | Function extraction |
| Java | `javalang` | Method analysis |
| C/C++ | `tree-sitter` | Function parsing |

## Configuration

### LLM Provider

Configure in `app/llm.py`:

```python
def get_llm(
    provider: str = "ollama",
    model: str = "qwen2.5:3b-instruct",
)
```

### File Filters

Configure in `app/repo_loader.py`:

```python
EXCLUDE_DIRS = {".git", "venv", "node_modules", ...}
ALLOWED_EXTENSIONS = (".py", ".js", ".ts", ".java", ".c", ".cpp")
```

### RAG and Pre-filter

Toggle RAG example injection and the fast pre-filter via environment variables:

```bash
# Disable RAG example retrieval
export GREENCODE_RAG=disabled

# Disable pre-filter (send all units directly to deep model)
export GREENCODE_PREFILTER=disabled
```

Both are **enabled** by default.

## How It Works

1. **Load Repository** - Discovers all source files
2. **Extract Code Units** - Parses files with AST, extracts functions/classes
3. **Calculate Metrics** - Computes complexity, LOC, dependencies
4. **Prioritize** - Sorts by complexity (highest first)
5. **Pre-filter (Tier 1)** - Fast 8B model quickly screens each unit; trivial code is skipped
6. **Retrieve Examples (RAG)** - Queries ChromaDB for semantically similar before/after code examples
7. **Detect Taxonomy Categories** - Matches suspicious tags and code patterns to the taxonomy
8. **Deep Analysis (Tier 2)** - Sends each flagged function to the deep 70B model with rich context, retrieved examples, and valid taxonomy categories
9. **Classify & Cache** - Validates taxonomy category, stores results with function-level cache keys
10. **Report** - Generates findings with precise line numbers, taxonomy classifications, and example references

## Cache System

Cached results are stored in `.llm_analysis_cache.json` with keys:

```
{file_path}:{function_name}:{content_hash}
```



