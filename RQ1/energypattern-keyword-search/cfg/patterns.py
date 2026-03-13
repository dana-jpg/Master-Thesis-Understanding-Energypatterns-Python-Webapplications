import re
from typing import Dict, List

PatternsMap = Dict[str, List[str]]


def strip_keyword_from_regex(keyword):
    return re.sub(r'\\b|.\\?', '', keyword)


def keyword_sorter(keyword: str):
    # Sorts by number of words (highest first), hyphens (highest first),
    # length (lowest first), and alphabetically (A to Z)
    keyword_clean = strip_keyword_from_regex(keyword)
    return -keyword.count(" "), -keyword.count("-"), -len(keyword_clean), keyword_clean


def transform_keywords(pattern_map: PatternsMap, sorter=keyword_sorter, *, keep_regex_notation=True):
    return {category: sorted(keywords if keep_regex_notation else (strip_keyword_from_regex(k) for k in keywords),
                             key=sorter) for category, keywords in pattern_map.items()}


patterns_raw = {
    "datatransfer": [
        # Reduce request frequency / push over poll
        "us cache", "introduc cache", "enabl cache", "reuse cached data", "implement cache", "reduc network call", "reduc network calls", "reduc api call", "reduc api calls",
        "fewer requests", "minimiz requests", "cut request rate", "reduc refresh rate", "lower refresh rate",
        "increas refresh interval", "increas request interval", "refresh less often", "slow refresh", "slow update",
        r"refresh on change", "periodic refresh", r"every\ \*\ minutes",
        "replac poll", "avoid poll", "stop poll", "long poll", "push over poll", "push updates",
        "server push", r"socket\.io", "server-sent events",

        #Batch requests
        "batch request", "batch api call", "batch network call", "bulk request", "bulk upload", "bulk update", "combine request", "reduc round trips",

        # Rate limiting / retry
        "rate limit request", "rate limiting", "throttl request", "throttling",
        "debounc fetch", "debounc request", "deduplicat request", "coalesc duplicate requests",
        "exponential backoff", "retry with backoff", "backoff with jitter",
        "dynamic retry delay", "increas retry delay", "retry after", "rate limit",

        # Reduce size / compression
        "compress payload", "gzip", "deflate",
        "minify json", "compact json", "shrink payload", "reduc payload",
        "binary json", "messagepack", "cbor",
        "delta update", "diff sync", "patch update",
        "partial response", "sparse fields", "only necessary fields",
        "optimiz data transfer", "reduce bandwidth", "reduce data rate", "lower bitrate",

        # Offload
        "offload compute", "offload processing", "edge offload", "cloud offload",
        "cdn compute", "server-side render", "pre-render"
    ],

    "UI": [
        # Images / resolution
        "lazy load image", "lazy load media", "defer offscreen images", "below the fold",
        "defer render", "defer loading",
        "convert to webp", "convert to avif",
        "serve responsive images", "responsive images",
        "use smaller resolution", "lower resolution", "downscale images",
        "optimize images", "compress images",

        # Animations / graphics
        "disable animation", "reduc animation", "remov animation", "limit animation",
        "reduce motion", "limit fps", "lower frame rate",
        "heavy paint", "heavy reflow", "expensive render", "render bottleneck", "gpu heavy",
        "canvas heavy", "webgl heavy", "background video", "disable autoplay", "no autoplay", "stop autoplay",
    ],

    "code_optimization": [
        # G1: Common subexpression elimination
        "avoid recompute", "do not recompute", "store result", "memoize",
        "reuse computed value", "common subexpression", "assign to variable", "temporary variable",

        # G2: Sorting
        "avoid resort", "already sorted", "presorted", "skip sort", "nearly sorted", "partial sort",

        # G3: Loop optimizations
        "loop unrolling", "loop unswitching", "early termination", "break early", "guard clause",
        "short circuit in loop", "hoist invariant", "loop invariant", "move call outside loop",
        "avoid expensive call in loop", "store loop end condition", "reduce loop overhead",

        # G4: Short-circuit logic
        "short circuit", "short-circuit operator", "return early",

        # G5: Approximation / lower precision
        "use approximation", "reduce precision", "lower precision",
        "float32", "float16", "bfloat16", "int8", "quantize", "tolerance", "epsilon",

        # G6: Remove unnecessary state
        "remove debug variable", "remove temp variable", "avoid storing computed data",
        "reduce intermediate state", "avoid duplicate state"
    ]
}

patterns = transform_keywords(patterns_raw)
