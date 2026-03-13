"""
Green Code Taxonomy - Energy-Efficient Coding Practices

Defines a hierarchical taxonomy of code optimization categories for energy efficiency.
Based on research taxonomy covering Data Layer, Network, Background Tasks, UI, 
Server-Side, Control Flow, and Build Pipeline optimizations.
"""

from enum import Enum
from dataclasses import dataclass, field
from typing import Optional


class TopCategory(str, Enum):
    """Top-level categories of energy-efficient coding practices."""
    DATA_LAYER = "data_layer"
    NETWORK_LAYER = "network_layer"
    BACKGROUND_TASKS = "background_tasks"
    USER_INTERFACE = "user_interface"
    SERVER_SIDE = "server_side"
    CONTROL_FLOW = "control_flow"
    BUILD_PIPELINE = "build_pipeline"


@dataclass
class TaxonomyNode:
    """
    A node in the taxonomy hierarchy.
    
    Attributes:
        id: Unique identifier (e.g., "data_layer.efficient_access.cache_vs_db")
        name: Human-readable name
        parent_id: ID of parent node (None for top-level)
        top_category: The top-level category this belongs to
        description: Detailed description of the optimization
        detection_hints: Keywords/patterns for AST-based detection
        examples: List of example IDs that demonstrate this pattern
    """
    id: str
    name: str
    top_category: TopCategory
    description: str
    parent_id: Optional[str] = None
    detection_hints: list[str] = field(default_factory=list)
    examples: list[str] = field(default_factory=list)


# =============================================================================
# TAXONOMY DEFINITION
# =============================================================================

TAXONOMY: dict[str, TaxonomyNode] = {}


def _add_node(node: TaxonomyNode) -> TaxonomyNode:
    """Helper to register a taxonomy node."""
    TAXONOMY[node.id] = node
    return node


# -----------------------------------------------------------------------------
# DATA LAYER 
# -----------------------------------------------------------------------------

_add_node(TaxonomyNode(
    id="data_layer",
    name="Data Layer",
    top_category=TopCategory.DATA_LAYER,
    description="Optimizations for how the app talks to other systems (DB queries, HTTP APIs, message queues, auth providers)",
))

# Efficient Data Access
_add_node(TaxonomyNode(
    id="data_layer.efficient_access",
    name="Efficient Data Access",
    parent_id="data_layer",
    top_category=TopCategory.DATA_LAYER,
    description="Optimizing database queries, ORM usage, and caching strategies",
))

_add_node(TaxonomyNode(
    id="data_layer.efficient_access.cache_vs_db",
    name="Retrieve from Cache Instead of DB",
    parent_id="data_layer.efficient_access",
    top_category=TopCategory.DATA_LAYER,
    description="Use cached data instead of querying the database when possible",
    detection_hints=["cache", "redis", "memcache", "lru_cache", "get_or_create"],
))

_add_node(TaxonomyNode(
    id="data_layer.efficient_access.batch_operations",
    name="Batch Database Operations",
    parent_id="data_layer.efficient_access",
    top_category=TopCategory.DATA_LAYER,
    description="Perform database operations in batches instead of one-by-one (N+1 query problem)",
    detection_hints=["bulk_create", "bulk_update", "select_related", "prefetch_related", 
                    "for.*db", "loop.*query", "IN (", "JOIN"],
))

_add_node(TaxonomyNode(
    id="data_layer.efficient_access.optimize_queries",
    name="Optimize Database Queries",
    parent_id="data_layer.efficient_access",
    top_category=TopCategory.DATA_LAYER,
    description="Use efficient query patterns (proper indexes, avoid SELECT *, use aggregations)",
    detection_hints=["select_for_update", "only(", "defer(", "values_list", "annotate", "aggregate"],
))

# Data Resource Management
_add_node(TaxonomyNode(
    id="data_layer.resource_management",
    name="Data Resource Management",
    parent_id="data_layer",
    top_category=TopCategory.DATA_LAYER,
    description="Managing external services, connections, and cleanup",
))

_add_node(TaxonomyNode(
    id="data_layer.resource_management.close_sessions",
    name="Close DB Sessions",
    parent_id="data_layer.resource_management",
    top_category=TopCategory.DATA_LAYER,
    description="Properly close database connections and sessions",
    detection_hints=["close()", "session.close", "connection.close", "with.*session"],
))

_add_node(TaxonomyNode(
    id="data_layer.resource_management.clear_cache",
    name="Clear Unnecessary Cache Data",
    parent_id="data_layer.resource_management",
    top_category=TopCategory.DATA_LAYER,
    description="Clear cache entries that are no longer needed",
    detection_hints=["cache.delete", "cache.clear", "invalidate", "expire"],
))


# -----------------------------------------------------------------------------
# NETWORK LAYER 
# -----------------------------------------------------------------------------

_add_node(TaxonomyNode(
    id="network_layer",
    name="Network Layer",
    top_category=TopCategory.NETWORK_LAYER,
    description="Decide when and how to call resources (Data Layer, external APIs, other services)",
))

_add_node(TaxonomyNode(
    id="network_layer.batch_calls",
    name="Batch HTTP/API Calls",
    parent_id="network_layer",
    top_category=TopCategory.NETWORK_LAYER,
    description="Combine multiple API calls into batched requests",
    detection_hints=["batch", "bulk", "gather", "asyncio.gather", "parallel"],
))

_add_node(TaxonomyNode(
    id="network_layer.skip_unnecessary",
    name="Skip Unnecessary API Calls",
    parent_id="network_layer",
    top_category=TopCategory.NETWORK_LAYER,
    description="Avoid calling external APIs when not needed",
    detection_hints=["if.*fetch", "skip", "early return", "guard"],
))

_add_node(TaxonomyNode(
    id="network_layer.cache_results",
    name="Cache API Results",
    parent_id="network_layer",
    top_category=TopCategory.NETWORK_LAYER,
    description="Cache results of external API calls to avoid repeated requests",
    detection_hints=["@cache", "lru_cache", "memoize", "cached_property"],
))


# -----------------------------------------------------------------------------
# BACKGROUND TASKS 
# -----------------------------------------------------------------------------

_add_node(TaxonomyNode(
    id="background_tasks",
    name="Background Task Management",
    top_category=TopCategory.BACKGROUND_TASKS,
    description="Optimizing background work (Celery/cron jobs, periodic syncs, scheduled tasks)",
))

# Failure-Aware Execution
_add_node(TaxonomyNode(
    id="background_tasks.failure_aware",
    name="Failure-Aware Execution",
    parent_id="background_tasks",
    top_category=TopCategory.BACKGROUND_TASKS,
    description="Handle failures gracefully in background tasks",
))

_add_node(TaxonomyNode(
    id="background_tasks.failure_aware.exponential_backoff",
    name="Retry with Exponential Backoff",
    parent_id="background_tasks.failure_aware",
    top_category=TopCategory.BACKGROUND_TASKS,
    description="Use exponential backoff for retries instead of immediate retry",
    detection_hints=["backoff", "retry", "exponential", "delay", "sleep", "wait"],
))

# Task Execution Control
_add_node(TaxonomyNode(
    id="background_tasks.execution_control",
    name="Task Execution Control",
    parent_id="background_tasks",
    top_category=TopCategory.BACKGROUND_TASKS,
    description="Control how and when tasks execute",
))

_add_node(TaxonomyNode(
    id="background_tasks.execution_control.lock_duplicates",
    name="Cache-Based Locking",
    parent_id="background_tasks.execution_control",
    top_category=TopCategory.BACKGROUND_TASKS,
    description="Use cache-based locking to prevent duplicate task execution",
    detection_hints=["lock", "mutex", "acquire", "release", "atomic"],
))

_add_node(TaxonomyNode(
    id="background_tasks.execution_control.task_expiration",
    name="Task Expiration",
    parent_id="background_tasks.execution_control",
    top_category=TopCategory.BACKGROUND_TASKS,
    description="Set task expiration to avoid processing stale tasks",
    detection_hints=["expires", "ttl", "timeout", "max_age"],
))

_add_node(TaxonomyNode(
    id="background_tasks.execution_control.limit_concurrency",
    name="Limit Concurrency",
    parent_id="background_tasks.execution_control",
    top_category=TopCategory.BACKGROUND_TASKS,
    description="Limit the number of concurrent task executions",
    detection_hints=["semaphore", "max_workers", "pool_size", "concurrency", "rate_limit"],
))


# -----------------------------------------------------------------------------
# USER INTERFACE 
# -----------------------------------------------------------------------------

_add_node(TaxonomyNode(
    id="user_interface",
    name="User Interface",
    top_category=TopCategory.USER_INTERFACE,
    description="Optimizing client/frontend interactions (HTTP endpoints, controllers, polling, UI rendering)",
))

# UI State Management
_add_node(TaxonomyNode(
    id="user_interface.state_management",
    name="UI State Management",
    parent_id="user_interface",
    top_category=TopCategory.USER_INTERFACE,
    description="Efficient management of UI state and backend communication",
))

_add_node(TaxonomyNode(
    id="user_interface.state_management.update_on_change",
    name="Only Update Backend When UI Changed",
    parent_id="user_interface.state_management",
    top_category=TopCategory.USER_INTERFACE,
    description="Avoid unnecessary backend calls when UI state hasn't changed",
    detection_hints=["dirty", "changed", "modified", "diff"],
))

_add_node(TaxonomyNode(
    id="user_interface.state_management.reduce_polling",
    name="Reduce Backend Polling",
    parent_id="user_interface.state_management",
    top_category=TopCategory.USER_INTERFACE,
    description="Reduce polling frequency or use push-based updates",
    detection_hints=["polling", "interval", "setInterval", "websocket"],
))

# Page Rendering
_add_node(TaxonomyNode(
    id="user_interface.rendering",
    name="Optimize Page Rendering",
    parent_id="user_interface",
    top_category=TopCategory.USER_INTERFACE,
    description="Efficient page rendering strategies",
))

_add_node(TaxonomyNode(
    id="user_interface.rendering.lazy_images",
    name="Lazy Rendering of Images",
    parent_id="user_interface.rendering",
    top_category=TopCategory.USER_INTERFACE,
    description="Load images lazily as they enter the viewport",
    detection_hints=["lazy", "loading=\"lazy\"", "intersection", "viewport"],
))

_add_node(TaxonomyNode(
    id="user_interface.rendering.partial",
    name="Partial Page Rendering",
    parent_id="user_interface.rendering",
    top_category=TopCategory.USER_INTERFACE,
    description="Render only parts of the page that changed (e.g., HTMX)",
    detection_hints=["htmx", "partial", "fragment", "ajax"],
))

_add_node(TaxonomyNode(
    id="user_interface.rendering.conditional",
    name="Conditional Rendering",
    parent_id="user_interface.rendering",
    top_category=TopCategory.USER_INTERFACE,
    description="Only render components when conditions are met",
    detection_hints=["v-if", "ng-if", "{#if", "conditional"],
))

# Client-Side Resource Management
_add_node(TaxonomyNode(
    id="user_interface.client_resources",
    name="Client-Side Resource Management",
    parent_id="user_interface",
    top_category=TopCategory.USER_INTERFACE,
    description="Efficient loading and management of client-side resources",
))

_add_node(TaxonomyNode(
    id="user_interface.client_resources.lazy_load",
    name="Lazy Load Resources",
    parent_id="user_interface.client_resources",
    top_category=TopCategory.USER_INTERFACE,
    description="Load heavy resources on demand instead of upfront",
    detection_hints=["lazy", "dynamic import", "import()", "defer", "async"],
))

_add_node(TaxonomyNode(
    id="user_interface.client_resources.on_interaction",
    name="Load on Interaction",
    parent_id="user_interface.client_resources",
    top_category=TopCategory.USER_INTERFACE,
    description="Load expensive resources only when user interacts",
    detection_hints=["onclick", "onhover", "onfocus", "interaction"],
))

_add_node(TaxonomyNode(
    id="user_interface.client_resources.efficient_format",
    name="Use Efficient Image Format",
    parent_id="user_interface.client_resources",
    top_category=TopCategory.USER_INTERFACE,
    description="Use WebP or other efficient formats instead of PNG/JPG",
    detection_hints=["webp", "avif", "format", "image"],
))


# -----------------------------------------------------------------------------
# SERVER SIDE REQUEST HANDLING
# -----------------------------------------------------------------------------

_add_node(TaxonomyNode(
    id="server_side",
    name="Server-Side Request Handling",
    top_category=TopCategory.SERVER_SIDE,
    description="Optimizing server-side response construction and request control",
))

# Response Construction
_add_node(TaxonomyNode(
    id="server_side.response",
    name="Response Construction",
    parent_id="server_side",
    top_category=TopCategory.SERVER_SIDE,
    description="Efficient construction of server responses",
))

_add_node(TaxonomyNode(
    id="server_side.response.data_selection",
    name="Response Data Selection",
    parent_id="server_side.response",
    top_category=TopCategory.SERVER_SIDE,
    description="Return only necessary data, limit response size",
    detection_hints=["limit", "paginate", "fields", "only", "exclude"],
))

_add_node(TaxonomyNode(
    id="server_side.response.compression",
    name="Use Efficient Compression",
    parent_id="server_side.response",
    top_category=TopCategory.SERVER_SIDE,
    description="Use Brotli/Zstandard instead of gzip, or enable compression",
    detection_hints=["gzip", "brotli", "zstd", "compress", "deflate"],
))

_add_node(TaxonomyNode(
    id="server_side.response.aot_compression",
    name="Do AOT Compression",
    parent_id="server_side.response",
    top_category=TopCategory.SERVER_SIDE,
    description="Pre-compress static assets instead of on-the-fly compression",
    detection_hints=["static", "precompressed", "build", "webpack"],
))

# Request Control
_add_node(TaxonomyNode(
    id="server_side.request_control",
    name="Request Control",
    parent_id="server_side",
    top_category=TopCategory.SERVER_SIDE,
    description="Control incoming request rate and behavior",
))

_add_node(TaxonomyNode(
    id="server_side.request_control.rate_limiting",
    name="Rate Limiting Endpoints",
    parent_id="server_side.request_control",
    top_category=TopCategory.SERVER_SIDE,
    description="Limit the number of requests per user/IP",
    detection_hints=["throttle", "rate_limit", "ratelimit", "quota"],
))


# -----------------------------------------------------------------------------
# CONTROL FLOW OPTIMIZATION 
# -----------------------------------------------------------------------------

_add_node(TaxonomyNode(
    id="control_flow",
    name="Control Flow Optimization",
    top_category=TopCategory.CONTROL_FLOW,
    description="Optimizing internal code logic (functions, loops, conditionals)",
))

# Algorithmic
_add_node(TaxonomyNode(
    id="control_flow.algorithmic",
    name="Algorithmic Optimizations",
    parent_id="control_flow",
    top_category=TopCategory.CONTROL_FLOW,
    description="High-level algorithmic improvements",
))

_add_node(TaxonomyNode(
    id="control_flow.algorithmic.approximate",
    name="Use Approximate Values",
    parent_id="control_flow.algorithmic",
    top_category=TopCategory.CONTROL_FLOW,
    description="Use approximations when exact values aren't needed",
    detection_hints=["approximate", "estimate", "round", "ceil", "floor"],
))

_add_node(TaxonomyNode(
    id="control_flow.algorithmic.avoid_expensive_builtins",
    name="Avoid Expensive Built-in Operations",
    parent_id="control_flow.algorithmic",
    top_category=TopCategory.CONTROL_FLOW,
    description="Replace expensive built-in operations with faster alternatives",
    detection_hints=["regex", "deepcopy", "json.loads", "eval"],
))

# Loop Optimizations
_add_node(TaxonomyNode(
    id="control_flow.loop",
    name="Loop Optimizations",
    parent_id="control_flow",
    top_category=TopCategory.CONTROL_FLOW,
    description="Optimizing loop performance",
))

_add_node(TaxonomyNode(
    id="control_flow.loop.skip_iterations",
    name="Skip Unnecessary Iterations",
    parent_id="control_flow.loop",
    top_category=TopCategory.CONTROL_FLOW,
    description="Skip loop iterations when not needed (early continue/break)",
    detection_hints=["continue", "break", "if.*continue"],
))

_add_node(TaxonomyNode(
    id="control_flow.loop.hoist_expensive",
    name="Move Expensive Operations Out of Loop",
    parent_id="control_flow.loop",
    top_category=TopCategory.CONTROL_FLOW,
    description="Move invariant expensive operations outside the loop",
    detection_hints=["for.*compile", "for.*open", "for.*connect", "loop invariant"],
))

# Function Optimizations
_add_node(TaxonomyNode(
    id="control_flow.function",
    name="Function Optimizations",
    parent_id="control_flow",
    top_category=TopCategory.CONTROL_FLOW,
    description="Optimizing function-level patterns",
))

_add_node(TaxonomyNode(
    id="control_flow.function.reuse_computed",
    name="Reuse Already Computed Results",
    parent_id="control_flow.function",
    top_category=TopCategory.CONTROL_FLOW,
    description="Cache and reuse computed values instead of recomputing",
    detection_hints=["cache", "memoize", "lru_cache", "computed", "result ="],
))

_add_node(TaxonomyNode(
    id="control_flow.function.optimize_data_flow",
    name="Optimize Function-Level Data Flow",
    parent_id="control_flow.function",
    top_category=TopCategory.CONTROL_FLOW,
    description="Pass data objects instead of IDs to avoid repeated lookups",
    detection_hints=["fetch", "get_by_id", "lookup"],
))

_add_node(TaxonomyNode(
    id="control_flow.function.exit_early",
    name="Exit Early",
    parent_id="control_flow.function",
    top_category=TopCategory.CONTROL_FLOW,
    description="Return early if conditions are met to avoid heavy computation",
    detection_hints=["if.*return", "guard", "early return", "short-circuit"],
))

_add_node(TaxonomyNode(
    id="control_flow.function.skip_data_layer",
    name="Skip Unnecessary Calls to Data Layer",
    parent_id="control_flow.function",
    top_category=TopCategory.CONTROL_FLOW,
    description="Avoid database/API calls when not needed",
    detection_hints=["if.*db", "skip.*query", "unnecessary.*call"],
))

# Class Optimizations
_add_node(TaxonomyNode(
    id="control_flow.class",
    name="Class Optimizations",
    parent_id="control_flow",
    top_category=TopCategory.CONTROL_FLOW,
    description="Optimizing class-level patterns",
))

_add_node(TaxonomyNode(
    id="control_flow.class.avoid_expensive_init",
    name="Avoid Expensive Operations in Init",
    parent_id="control_flow.class",
    top_category=TopCategory.CONTROL_FLOW,
    description="Defer expensive operations from __init__ to when needed",
    detection_hints=["__init__", "lazy", "deferred"],
))


# -----------------------------------------------------------------------------
# BUILD PIPELINE 
# -----------------------------------------------------------------------------

_add_node(TaxonomyNode(
    id="build_pipeline",
    name="Build Pipeline Optimization",
    top_category=TopCategory.BUILD_PIPELINE,
    description="Optimizing build tools, bundlers, and CI/CD pipelines",
))

_add_node(TaxonomyNode(
    id="build_pipeline.efficient_tools",
    name="Use Efficient Build Tools",
    parent_id="build_pipeline",
    top_category=TopCategory.BUILD_PIPELINE,
    description="Use faster build tools (esbuild vs webpack, UglifyJS vs Closure)",
    detection_hints=["webpack", "esbuild", "vite", "rollup", "minify"],
))


# =============================================================================
# UTILITY FUNCTIONS
# =============================================================================

def get_node(node_id: str) -> Optional[TaxonomyNode]:
    """Get a taxonomy node by ID."""
    return TAXONOMY.get(node_id)


def get_children(parent_id: str) -> list[TaxonomyNode]:
    """Get all direct children of a taxonomy node."""
    return [node for node in TAXONOMY.values() if node.parent_id == parent_id]


def get_leaf_nodes() -> list[TaxonomyNode]:
    """Get all leaf nodes (nodes with no children)."""
    parent_ids = {node.parent_id for node in TAXONOMY.values() if node.parent_id}
    return [node for node in TAXONOMY.values() if node.id not in parent_ids]


def get_nodes_by_category(category: TopCategory) -> list[TaxonomyNode]:
    """Get all nodes belonging to a top-level category."""
    return [node for node in TAXONOMY.values() if node.top_category == category]


def detect_likely_categories(suspicious_tags: list[str], code: str = "") -> list[str]:
    """
    Detect likely taxonomy categories based on AST tags and code patterns.
    
    Args:
        suspicious_tags: Tags from AST analysis (e.g., ["has_loop", "has_db_call"])
        code: Optional code string to search for patterns
    
    Returns:
        List of matching taxonomy node IDs, sorted by relevance
    """
    matches: list[tuple[str, int]] = []  # (node_id, score)
    
    text_to_search = " ".join(suspicious_tags).lower() + " " + code.lower()
    
    for node in get_leaf_nodes():
        score = 0
        for hint in node.detection_hints:
            if hint.lower() in text_to_search:
                score += 1
        
        if score > 0:
            matches.append((node.id, score))
    
    # Sort by score descending
    matches.sort(key=lambda x: x[1], reverse=True)
    
    return [node_id for node_id, _ in matches[:5]]  # Return top 5


def get_category_description(node_id: str) -> str:
    """Get a formatted description of a category for prompts."""
    node = get_node(node_id)
    if not node:
        return ""
    
    parts = [node.name]
    
    # Add parent context
    if node.parent_id:
        parent = get_node(node.parent_id)
        if parent:
            parts.insert(0, parent.name)
    
    return " > ".join(parts) + f": {node.description}"


# =============================================================================
# PROMPT GENERATION UTILITIES
# =============================================================================

def get_compact_taxonomy_for_prompt() -> str:
    """
    Get a token-efficient representation of all taxonomy categories for LLM prompts.
    
    Uses ~135 tokens instead of ~290 for full list.
    Format: category_prefix: leaf1|leaf2|leaf3
    """
    # Group leaf nodes by parent category
    groups = {}
    for node in get_leaf_nodes():
        # Get the top-level parent (e.g., "data_layer" from "data_layer.efficient_access.batch_operations")
        parts = node.id.split(".")
        if len(parts) >= 1:
            top = parts[0]
            # Use short prefix
            prefix_map = {
                "data_layer": "data",
                "network_layer": "network",
                "background_tasks": "background",
                "user_interface": "ui",
                "server_side": "server",
                "control_flow": "control",
                "build_pipeline": "build",
            }
            prefix = prefix_map.get(top, top)
            
            if prefix not in groups:
                groups[prefix] = []
            
            # Extract just the leaf name
            leaf_name = parts[-1]
            groups[prefix].append(leaf_name)
    
    # Build compact string
    lines = []
    for prefix, leaves in groups.items():
        lines.append(f"{prefix}: {' | '.join(leaves)}")
    
    return "\n".join(lines)


def get_all_valid_category_ids() -> set[str]:
    """Get all valid taxonomy category IDs (leaf nodes only)."""
    return {node.id for node in get_leaf_nodes()}


def validate_taxonomy_category(category: str) -> tuple[str, bool]:
    """
    Validate and normalize a taxonomy category returned by the LLM.
    
    Args:
        category: The category string from LLM response
        
    Returns:
        Tuple of (normalized_category, is_valid)
        If invalid, returns the closest match or "unknown"
    """
    if not category:
        return "unknown", False
    
    # Direct match with full ID
    if category in TAXONOMY:
        node = TAXONOMY[category]
        # Check if it's a leaf node (valid category)
        children = get_children(category)
        if not children:  # It's a leaf
            return category, True
        else:
            # User specified a parent, find first leaf child
            leaves = [n for n in TAXONOMY.values() 
                     if n.id.startswith(category) and not get_children(n.id)]
            if leaves:
                return leaves[0].id, False  # Return first leaf, mark as corrected
    
    # Try to find by leaf name only (e.g., "batch_operations")
    category_lower = category.lower().replace("-", "_").replace(" ", "_")
    for node in get_leaf_nodes():
        leaf_name = node.id.split(".")[-1]
        if leaf_name.lower() == category_lower:
            return node.id, True
    
    # Try fuzzy matching on leaf names
    best_match = None
    best_score = 0
    for node in get_leaf_nodes():
        leaf_name = node.id.split(".")[-1].lower()
        # Simple substring matching
        if category_lower in leaf_name or leaf_name in category_lower:
            score = len(set(category_lower) & set(leaf_name))
            if score > best_score:
                best_score = score
                best_match = node.id
    
    if best_match:
        return best_match, False
    
    return "unknown", False


def expand_short_category(short_category: str) -> Optional[str]:
    """
    Expand a short category name to full ID.
    
    Examples:
        "data.batch_operations" -> "data_layer.efficient_access.batch_operations"
        "batch_operations" -> "data_layer.efficient_access.batch_operations"
    """
    short_category = short_category.lower().strip()
    
    # Try direct lookup first
    if short_category in TAXONOMY:
        return short_category
    
    # Expand prefix
    prefix_map = {
        "data": "data_layer",
        "network": "network_layer",
        "background": "background_tasks",
        "ui": "user_interface",
        "server": "server_side",
        "control": "control_flow",
        "build": "build_pipeline",
    }
    
    parts = short_category.split(".")
    if parts[0] in prefix_map:
        parts[0] = prefix_map[parts[0]]
        expanded = ".".join(parts)
        if expanded in TAXONOMY:
            return expanded
    
    # If just leaf name, search for it
    leaf_name = parts[-1]
    for node in get_leaf_nodes():
        if node.id.endswith(f".{leaf_name}"):
            return node.id
    
    return None

