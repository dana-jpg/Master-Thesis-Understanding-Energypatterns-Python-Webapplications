from typing import List, Optional
import json
import os
from datetime import datetime

from pydantic import BaseModel, Field
from langchain_core.messages import HumanMessage
from langgraph.graph import StateGraph, END

from app.llm import get_llm
from app.prompts import (
    ENERGY_ANALYSIS_PROMPT, 
    ENERGY_ANALYSIS_PROMPT_WITH_AST, 
    ENERGY_ANALYSIS_PROMPT_WITH_CONTEXT,
    ENERGY_ANALYSIS_PROMPT_DETECTION_ONLY,
    ENERGY_ANALYSIS_PROMPT_WITH_AST_DETECTION_ONLY,
    ENERGY_ANALYSIS_PROMPT_WITH_CONTEXT_DETECTION_ONLY,
    ENERGY_ANALYSIS_WITH_EXAMPLES,
    ENERGY_ANALYSIS_WITH_EXAMPLES_DETECTION_ONLY,
    PREFILTER_PROMPT
)
from app.repo_loader import load_repo_files
from app.models import Finding
from app.cache import AnalysisCache, compute_hash
from app.ast_parser import parse_file, CodeUnit
from app.context import SymbolTable, ContextBuilder
from app.taxonomy import detect_likely_categories, get_compact_taxonomy_for_prompt, validate_taxonomy_category
from app.example_store import get_example_store, format_examples_for_prompt


# -----------------------------
# Graph state
# -----------------------------

class GraphState(BaseModel):
    repo_path: str = ""
    input_type: str = "path" 
    code_content: Optional[str] = None 
    files: List[str] = Field(default_factory=list)
    code_units: List[CodeUnit] = Field(default_factory=list)
    current_unit: Optional[CodeUnit] = None
    symbol_table: Optional[SymbolTable] = None
    findings: List[Finding] = Field(default_factory=list)
    analysis_mode: str = "suggestion" 
    
    class Config:
        arbitrary_types_allowed = True


# -----------------------------
# Globals (safe: read-only or idempotent)
# -----------------------------

# Tiered LLM instances
llm_fast = get_llm(tier="fast")   
llm_deep = get_llm(tier="deep")   
cache = AnalysisCache()

# Pre-filter toggle (set GREENCODE_PREFILTER=disabled to disable)
PREFILTER_ENABLED = os.environ.get("GREENCODE_PREFILTER", "enabled").lower() != "disabled"

# RAG toggle (set GREENCODE_RAG=disabled to disable example injection)
RAG_ENABLED = os.environ.get("GREENCODE_RAG", "enabled").lower() != "disabled"

MAX_CHARS = 4000
MIN_COMPLEXITY_THRESHOLD = 3
MIN_LOC_THRESHOLD = 15

# LLM usage counters
_llm_call_counts = {"fast": 0, "deep": 0, "cache_hits": 0, "skipped": 0, "failed": 0}

def reset_llm_counters():
    """Reset LLM call counters (call at start of analysis)."""
    global _llm_call_counts
    _llm_call_counts = {"fast": 0, "deep": 0, "cache_hits": 0, "skipped": 0, "failed": 0}

def get_llm_counters():
    """Get current LLM call counters."""
    return _llm_call_counts.copy()

def print_llm_stats():
    """Print current LLM usage statistics."""
    c = _llm_call_counts
    total = c["fast"] + c["deep"] + c["cache_hits"] + c["skipped"]
    print(f"\n📊 LLM Usage: Fast(8B)={c['fast']} | Deep(70B)={c['deep']} | Cache={c['cache_hits']} | Skipped={c['skipped']} | Failed={c['failed']} | Total units={total}")


import time

def retry_llm_call(llm, messages, max_retries=5, base_delay=1.0):
    """
    Call LLM with retry logic for rate limiting (429) errors.
    Uses exponential backoff: 1s, 2s, 4s, 8s, 16s
    """
    last_exception = None
    
    for attempt in range(max_retries):
        try:
            return llm.invoke(messages)
        except Exception as e:
            last_exception = e
            error_str = str(e).lower()
            
            # Check if it's a rate limit error (429)
            is_rate_limit = "429" in error_str or "rate" in error_str or "limit" in error_str or "too many" in error_str
            
            if is_rate_limit and attempt < max_retries - 1:
                delay = base_delay * (2 ** attempt)  
                print(f"  ⏳ Rate limited, waiting {delay:.1f}s before retry {attempt + 2}/{max_retries}...")
                time.sleep(delay)
            else:
                # Not a rate limit error or last attempt - re-raise
                raise last_exception
    
    raise last_exception


# Global WebSocket callback (set by server)
_websocket_callback = None

# LLM output log file
LLM_LOG_FILE = "model_answers.txt"

def set_websocket_callback(callback):
    """Set the WebSocket callback for progress updates."""
    global _websocket_callback
    _websocket_callback = callback

def emit_progress(message: str):
    """Emit progress update via WebSocket if available."""
    if _websocket_callback:
        _websocket_callback(message)

def log_llm_output(unit_info: str, prompt: str, response: str):
    """Log LLM prompt and response to file for monitoring."""
    try:
        with open(LLM_LOG_FILE, 'a', encoding='utf-8') as f:
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            f.write(f"\n{'='*80}\n")
            f.write(f"[{timestamp}] {unit_info}\n")
            f.write(f"{'='*80}\n")
            f.write("\nPROMPT:\n")
            f.write(f"{'-'*80}\n")
            f.write(f"{prompt}\n")
            f.write(f"{'-'*80}\n")
            f.write("\nRESPONSE:\n")
            f.write(f"{'-'*80}\n")
            f.write(f"{response}\n")
            f.write(f"{'-'*80}\n")
            f.flush()  
    except Exception as e:
        print(f"Warning: Failed to log LLM output: {e}")


# -----------------------------
# Extract code units node
# -----------------------------

def extract_code_units(state: GraphState) -> GraphState:
    """Parse all files and extract code units using AST"""
    import tempfile
    import os
    
    # Reset LLM counters for this analysis run
    reset_llm_counters()
    
    all_units = []
    
    # Handle direct code input
    if state.input_type == "code" and state.code_content:
        emit_progress("Analyzing provided code snippet...")
        
        # Detect language from code content (simple heuristic)
        language = "python"  
        if "function" in state.code_content or "const" in state.code_content or "let" in state.code_content:
            language = "javascript"
        elif "public class" in state.code_content or "void main" in state.code_content:
            language = "java"
        
        # Create a temporary file
        ext_map = {"python": ".py", "javascript": ".js", "java": ".java"}
        with tempfile.NamedTemporaryFile(mode='w', suffix=ext_map.get(language, ".txt"), delete=False) as tmp:
            tmp.write(state.code_content)
            tmp_path = tmp.name
        
        try:
            units = parse_file(tmp_path)
            if units:
                # Update file paths to be more readable
                for unit in units:
                    unit.file_path = f"<code-snippet>{ext_map.get(language, '.txt')}"
                all_units.extend(units)
            else:
                # Fallback: analyze as whole snippet
                all_units.append(CodeUnit(
                    name="<code-snippet>",
                    file_path=f"<code-snippet>{ext_map.get(language, '.txt')}",
                    start_line=1,
                    end_line=len(state.code_content.splitlines()),
                    code=state.code_content[:MAX_CHARS],
                    language=language,
                    complexity=0,
                    loc=len(state.code_content.splitlines()),
                    dependencies=[],
                    unit_type="file"
                ))
        finally:
            # Clean up temp file
            try:
                os.unlink(tmp_path)
            except:
                pass
        
        emit_progress(f"Found {len(all_units)} code units to analyze")
    else:
        # Handle repository/path input
        emit_progress(f"Extracting code units from {len(state.files)} files...")
        print(f"\n=== Extracting code units from {len(state.files)} files ===\n")
    
    for file_path in state.files:
        try:
            units = parse_file(file_path)
            if units:
                print(f"  {file_path}: {len(units)} units found")
                all_units.extend(units)
            else:
                # Fallback: if AST parsing fails, analyze whole file
                print(f"  {file_path}: AST parsing failed, using whole-file analysis")
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        code = f.read()
                    if code.strip():
                        # Create a synthetic code unit for the whole file
                        all_units.append(CodeUnit(
                            name="<whole-file>",
                            file_path=file_path,
                            start_line=1,
                            end_line=len(code.splitlines()),
                            code=code[:MAX_CHARS],
                            language="unknown",
                            complexity=0,
                            loc=len(code.splitlines()),
                            dependencies=[],
                            unit_type="file"
                        ))
                except Exception:
                    pass
        except Exception as e:
            print(f"  {file_path}: Error - {e}")
            continue
    
    if state.input_type != "code":
        print(f"\nTotal code units extracted: {len(all_units)}\n")
    
    emit_progress(f"Total code units extracted: {len(all_units)}")
    
    # Build Symbol Table
    symbol_table = SymbolTable()
    for unit in all_units:
        symbol_table.add_unit(unit)
    
    # Sort by complexity (highest first) to prioritize complex functions
    all_units.sort(key=lambda u: u.complexity, reverse=True)
    
    return state.copy(update={"code_units": all_units, "symbol_table": symbol_table})


# -----------------------------
# Analysis node
# -----------------------------

def analyze_next_unit(state: GraphState) -> GraphState:
    """Analyze the next code unit"""
    # No units left to analyze
    if not state.code_units:
        return state.copy(update={"current_unit": None})

    # Take next unit immutably
    unit, *remaining_units = state.code_units

    # Skip empty units
    if not unit.code.strip():
        return state.copy(update={
            "code_units": remaining_units,
            "current_unit": unit,
        })

    # -----------------------------
    # Smart Filtering (Efficiency)
    # -----------------------------
    if not is_worth_analyzing(unit):
        _llm_call_counts["skipped"] += 1
        print(f"Skipping {unit.name} (Trivial: complexity={unit.complexity}, loc={unit.loc})")
        return state.copy(update={
            "code_units": remaining_units,
            "current_unit": unit,
        })

    # -----------------------------
    # Cache lookup (content-based with function name)
    # -----------------------------

    content_hash = compute_hash(unit.code)
    # Include analysis_mode in cache key so we don't return cached suggestions when in detection mode
    cache_key = f"{unit.file_path}:{unit.name}:{content_hash}:{state.analysis_mode}"
    cached = cache.get(cache_key)

    if cached is not None:
        _llm_call_counts["cache_hits"] += 1
        # Cached NO_ISSUE
        if cached.get("result") == "NO_ISSUE":
            return state.copy(update={
                "code_units": remaining_units,
                "current_unit": unit,
            })

        # Cached ISSUE
        finding = Finding(
            file=unit.file_path,
            function_name=unit.name,
            start_line=unit.start_line,
            end_line=unit.end_line,
            complexity=unit.complexity,
            issue=cached["issue"],
            explanation=cached["explanation"],
            patch=cached.get("patch"),
            problematic_code=unit.code
        )

        return state.copy(update={
            "code_units": remaining_units,
            "current_unit": unit,
            "findings": state.findings + [finding],
        })

    # -----------------------------
    # LLM invocation (cache miss)
    # -----------------------------
    
    emit_progress(f"Analyzing {unit.name} in {unit.file_path}...")

    # -----------------------------
    # TIER 1: Fast Pre-filter (8B model)
    # -----------------------------
    if PREFILTER_ENABLED:
        prefilter_prompt = PREFILTER_PROMPT.format(
            language=unit.language,
            function_name=unit.name,
            complexity=unit.complexity,
            suspicious_tags=", ".join(unit.suspicious_tags) if unit.suspicious_tags else "none",
            code=unit.code
        )
        
        try:
            _llm_call_counts["fast"] += 1
            prefilter_response = retry_llm_call(llm_fast, [HumanMessage(content=prefilter_prompt)])
            prefilter_result = prefilter_response.content.strip().upper()
            
            # Print stats every 50 fast calls
            if _llm_call_counts["fast"] % 50 == 0:
                print_llm_stats()
            
            print(f"  [Pre-filter] {unit.name}: {prefilter_result}")
            
            if prefilter_result == "PASS":
                # Fast model says it's fine - cache and skip
                cache.set(cache_key, {"result": "NO_ISSUE"})
                emit_progress(f"  ↳ {unit.name}: Passed pre-filter (no issues)")
                return state.copy(update={
                    "code_units": remaining_units,
                    "current_unit": unit,
                })
            else:
                emit_progress(f"  ↳ {unit.name}: Flagged — running deep analysis")
                
        except Exception as e:
            # Pre-filter failed after retries, fall through to deep analysis
            _llm_call_counts["failed"] += 1
            print(f"  [Pre-filter] {unit.name}: Failed after retries ({e}), falling back to deep analysis")

    # -----------------------------
    # TIER 2: Deep Analysis (70B model)
    # -----------------------------
    _llm_call_counts["deep"] += 1
    
    # Get context (related code) from Symbol Table
    context_builder = ContextBuilder(state.symbol_table if state.symbol_table else SymbolTable())
    related_code = context_builder.get_context_for_unit(unit) if unit.unit_type != "file" else ""
    
    # -----------------------------
    # RAG: Retrieve Similar Examples
    # -----------------------------
    examples_section = ""
    detected_categories = []
    
    if RAG_ENABLED and unit.unit_type != "file":
        try:
            # Detect likely categories from suspicious tags and code
            detected_categories = detect_likely_categories(
                unit.suspicious_tags if unit.suspicious_tags else [],
                unit.code
            )
            
            # Retrieve similar examples from vector store
            example_store = get_example_store(examples_dir="examples")
            similar_examples = example_store.find_similar(unit.code, n_results=2)
            
            if similar_examples:
                examples_section = format_examples_for_prompt(similar_examples, max_examples=2)
                print(f"  > RAG: Found {len(similar_examples)} similar examples for {unit.name}")
            else:
                examples_section = "No similar examples found in the database."
                
        except Exception as e:
            print(f"  > RAG: Failed to retrieve examples: {e}")
            examples_section = "Example retrieval unavailable."
    
    # -----------------------------
    # Build Prompt
    # -----------------------------
    if unit.unit_type != "file":
        if RAG_ENABLED and examples_section:
            # Use RAG-enhanced prompt with examples
            prompt_template = (
                ENERGY_ANALYSIS_WITH_EXAMPLES_DETECTION_ONLY 
                if state.analysis_mode == "detection" 
                else ENERGY_ANALYSIS_WITH_EXAMPLES
            )
            
            # Get compact taxonomy for prompt (~135 tokens for all categories)
            valid_categories = get_compact_taxonomy_for_prompt()
            
            prompt = prompt_template.format(
                language=unit.language,
                function_name=unit.name,
                file_path=unit.file_path,
                start_line=unit.start_line,
                end_line=unit.end_line,
                complexity=unit.complexity,
                valid_categories=valid_categories,
                examples_section=examples_section,
                related_code=f"DEPENDENCIES:\n{related_code}" if related_code else "No dependencies found.",
                code=unit.code
            )
        elif related_code:
            # Use context-aware prompt (no RAG)
            print(f"  > Context found for {unit.name}: {len(related_code)} chars")
            
            prompt_template = (
                ENERGY_ANALYSIS_PROMPT_WITH_CONTEXT_DETECTION_ONLY 
                if state.analysis_mode == "detection" 
                else ENERGY_ANALYSIS_PROMPT_WITH_CONTEXT
            )
            
            prompt = prompt_template.format(
                language=unit.language,
                function_name=unit.name,
                file_path=unit.file_path,
                start_line=unit.start_line,
                end_line=unit.end_line,
                complexity=unit.complexity,
                related_code=related_code,
                code=unit.code
            )
        else:
            # Fallback to standard AST prompt
            prompt_template = (
                ENERGY_ANALYSIS_PROMPT_WITH_AST_DETECTION_ONLY 
                if state.analysis_mode == "detection" 
                else ENERGY_ANALYSIS_PROMPT_WITH_AST
            )
            
            prompt = prompt_template.format(
                language=unit.language,
                function_name=unit.name,
                file_path=unit.file_path,
                start_line=unit.start_line,
                end_line=unit.end_line,
                complexity=unit.complexity,
                loc=unit.loc,
                code=unit.code
            )
    else:
        # Fallback to original prompt for whole-file analysis
        prompt_template = (
            ENERGY_ANALYSIS_PROMPT_DETECTION_ONLY 
            if state.analysis_mode == "detection" 
            else ENERGY_ANALYSIS_PROMPT
        )
        prompt = prompt_template.format(code=unit.code)

    try:
        response = retry_llm_call(llm_deep, [
            HumanMessage(content=prompt)
        ])
        print("\n===== LLM RAW RESPONSE =====")
        print(f"Unit: {unit.name} in {unit.file_path}")
        print(response.content)
        print("===== END LLM RESPONSE =====\n")
        
        # Log to file for real-time monitoring
        log_llm_output(
            f"Unit: {unit.name} in {unit.file_path}",
            prompt,
            response.content
        )

    except Exception as e:
        # LLM failure after retries - track and continue
        _llm_call_counts["failed"] += 1
        print(f"   Deep analysis failed for {unit.name}: {e}")
        return state.copy(update={
            "code_units": remaining_units,
            "current_unit": unit,
        })

    try:
        # Handle different response content types (Gemini can return a list)
        content = response.content
        if isinstance(content, list):
            # Extract text from the first text part
            text_parts = [part['text'] for part in content if part.get('type') == 'text']
            content = "".join(text_parts) if text_parts else ""
        elif not isinstance(content, str):
            content = str(content)

        # Clean markdown code blocks if present
        content = content.strip()
        if content.startswith("```json"):
            content = content[7:]
        elif content.startswith("```"):
            content = content[3:]
        
        if content.endswith("```"):
            content = content[:-3]
        
        content = content.strip()

        result = json.loads(content)
    except json.JSONDecodeError:
        # Invalid model output: skip but do not cache
        return state.copy(update={
            "code_units": remaining_units,
            "current_unit": unit,
        })

    # -----------------------------
    # Handle NO_ISSUE
    # -----------------------------

    if result.get("result") == "NO_ISSUE":
        cache.set(cache_key, {"result": "NO_ISSUE"})
        return state.copy(update={
            "code_units": remaining_units,
            "current_unit": unit,
        })

    # -----------------------------
    # Handle ISSUE
    # -----------------------------

    if result.get("result") == "ISSUE":
        cache.set(cache_key, result)
        
        # Validate and normalize the taxonomy category
        raw_category = result.get("taxonomy_category", "")
        validated_category, is_valid = validate_taxonomy_category(raw_category)
        if not is_valid and raw_category:
            print(f"  > Taxonomy: Normalized '{raw_category}' -> '{validated_category}'")

        finding = Finding(
            file=unit.file_path,
            function_name=unit.name,
            start_line=unit.start_line,
            end_line=unit.end_line,
            complexity=unit.complexity,
            issue=result.get("issue", ""),
            explanation=result.get("explanation", ""),
            patch=result.get("patch"),
            problematic_code=result.get("problematic_code", unit.code),
            taxonomy_category=validated_category,
            similar_to_example=result.get("similar_to_example"),
        )

        return state.copy(update={
            "code_units": remaining_units,
            "current_unit": unit,
            "findings": state.findings + [finding],
        })

    # -----------------------------
    # Unknown response shape (do not cache)
    # -----------------------------

    return state.copy(update={
        "code_units": remaining_units,
        "current_unit": unit,
    })


# -----------------------------
# Control flow
# -----------------------------

def should_continue(state: GraphState) -> str:
    return "analyze" if state.code_units else "summarize"


def summarize(state: GraphState) -> GraphState:
    """Save findings to JSON file and return final state."""
    # Print final LLM usage stats
    print_llm_stats()
    stats = get_llm_counters()
    
    if state.findings:
        # Generate timestamped filename
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        output_file = f"analysis_results_{timestamp}.json"
        
        # Build output data with LLM stats
        output_data = {
            "timestamp": datetime.now().isoformat(),
            "repo_path": state.repo_path,
            "input_type": state.input_type,
            "analysis_mode": state.analysis_mode,
            "total_findings": len(state.findings),
            "llm_usage": stats,
            "findings": [f.to_dict() for f in state.findings]
        }
        
        # Save to file
        try:
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(output_data, f, indent=2, ensure_ascii=False)
            print(f"\n Analysis saved to: {output_file}")
            emit_progress(f"Analysis saved to {output_file}")
        except Exception as e:
            print(f"\n Failed to save results: {e}")
    else:
        print("\n No issues found - nothing to save.")
        emit_progress("Analysis complete - no issues found")
    
    return state


# -----------------------------
# Graph construction
# -----------------------------

def build_graph():
    graph = StateGraph(GraphState)

    graph.add_node("load_repo", load_repo_files)
    graph.add_node("extract_units", extract_code_units)
    graph.add_node("analyze", analyze_next_unit)
    graph.add_node("summarize", summarize)

    graph.set_entry_point("load_repo")

    graph.add_edge("load_repo", "extract_units")
    graph.add_edge("extract_units", "analyze")

    graph.add_conditional_edges(
        "analyze",
        should_continue,
        {
            "analyze": "analyze",
            "summarize": "summarize",
        },
    )

    graph.add_edge("summarize", END)

    return graph.compile()


def is_worth_analyzing(unit: CodeUnit) -> bool:
    """
    Determine if a code unit is worth sending to the LLM.
    Returns True if:
    - Complexity >= 3
    - LOC >= 15
    - Has suspicious tags (LOOP, IO, DB, etc.)
    """
    # Always analyze if it has suspicious internal behavior
    if unit.suspicious_tags:
        return True
    
    # Analyze if complex enough
    if unit.complexity >= MIN_COMPLEXITY_THRESHOLD:
        return True
        
    # Analyze if long enough
    if unit.loc >= MIN_LOC_THRESHOLD:
        return True
        
    return False
