#!/usr/bin/env python3
"""
repo_filter.py

Logic for:
  - Parsing dependency files and detecting web frameworks
  - Filtering candidate repositories using thresholds

This module is HTTP-agnostic. It relies on injected callables (Helpers)
so it can be unit-tested without real GitHub calls.

Usage:
  - Provide concrete implementations for Helpers in your main script.
  - Optionally provide `get_repo_sbom` to leverage GitHub's SBOM endpoint.
"""

from dataclasses import dataclass
from typing import Callable, Dict, Iterable, List, Optional, Set, Tuple

# ----------------------- Public configuration -----------------------

DEFAULT_WEB_FRAMEWORKS: Set[str] = {
    # Backends / APIs
    "django", "djangorestframework", "flask", "fastapi", "starlette", "quart",
    "sanic", "tornado", "aiohttp", "bottle", "falcon", "hug", "masonite",
    # App frameworks/UI
    "streamlit", "dash", "panel", "gradio", "voila",
}

@dataclass(frozen=True)
class FilterParams:
    min_python: float
    min_stars: int
    min_contributors: int
    min_commits: int
    days: int
    skip_contributors: bool
    skip_activity: bool
    detect_webapps: bool
    require_web_frameworks: bool
    frameworks: Set[str]
    since_iso: str  

@dataclass(frozen=True)
class Helpers:
    # Core metrics
    compute_python_percentage: Callable[[str, str], float]
    count_contributors: Callable[[str, str], int]
    count_recent_commits: Callable[[str, str, str], int]
    # Repo content access (kept for interface compatibility, unused when fallback is disabled)
    fetch_file_base64: Callable[[str, str, str], Optional[str]]
    find_dependency_paths: Callable[[str, str], List[str]]
    # SBOM (returns (status_code, iterable_of_(ecosystem, name)))
    get_repo_sbom: Optional[Callable[[str, str], Tuple[int, Iterable[Tuple[str, str]]]]] = None
    # Optional: minimal logging hooks (progress + generic)
    log: Optional[Callable[[str], None]] = None
    progress: Optional[Callable[[int, int, str], None]] = None

# ----------------------- Detection (SBOM only) -----------------------

def detect_web_frameworks(owner: str, repo: str, frameworks: Set[str], helpers: Helpers) -> List[str]:
    """
    Detect frameworks using ONLY the GitHub SBOM endpoint.
    Fallback scanning is intentionally disabled.
    """
    print(f"[+] Checking GitHub dependency API for {owner}/{repo} ...", flush=True)

    if helpers.get_repo_sbom is None:
        # No SBOM helper available → behave as "API unavailable"
        print(f"  [warn] Dependency API unavailable (no helper), skipping.", flush=True)
        return []

    try:
        status, pkgs = helpers.get_repo_sbom(owner, repo)
        if status != 200:
            print(f"  [warn] Dependency API unavailable ({status}), skipping.", flush=True)
            return []
        found: Set[str] = set()
        for eco, name in pkgs:
            if not name:
                continue
            if (eco or "").lower() in ("pypi", "python", "pip", "") and name.lower() in frameworks:
                found.add(name.lower())
        if found:
            # Keep logs minimal as requested (no extra "via API" success line)
            return sorted(found)
        else:
            print(f"  → No web frameworks detected via API.", flush=True)
            return []
    except Exception as _e:
        print(f"  [warn] Dependency API error for {owner}/{repo}: {_e}", flush=True)
        return []

# ----------------------- Filtering -----------------------

def filter_repositories(
    candidates: List[Dict],
    params: FilterParams,
    helpers: Helpers
) -> List[Tuple[Dict, float, int, int, List[str]]]:
    """
    Filters candidates based on Python%, stars, contributors, activity,
    and (optionally) detected web frameworks.

    Returns a list of tuples:
      (repo_json, python_pct, contributors, commits_recent, frameworks_found)
    """
    results: List[Tuple[Dict, float, int, int, List[str]]] = []

    total = len(candidates)
    for i, repo in enumerate(candidates, start=1):
        full_name = repo.get("full_name")
        if not full_name or "/" not in full_name:
            continue

        # Exclude repos that appear to be frameworks or libraries
        name_lower = full_name.lower()
        desc_lower = (repo.get("description") or "").lower()
        if "framework" in name_lower or "library" in name_lower or \
        "toolkit" in desc_lower or "sdk" in desc_lower or \
         "cli" in desc_lower or "command-line" in desc_lower or \
        "framework" in desc_lower or "library" in desc_lower:
            continue


        # progress line (exact format requested)
        if helpers.progress:
            helpers.progress(i, total, full_name)
        else:
            print(f"\n[{i}/{total}] Checking {full_name} ...", flush=True)

        owner, name = full_name.split("/", 1)

        # Python %
        py_pct = helpers.compute_python_percentage(owner, name)
        if py_pct < params.min_python:
            continue

        # Stars
        stars = int(repo.get("stargazers_count", 0))
        if stars < params.min_stars:
            continue

        # Contributors
        if params.skip_contributors:
            contributors = -1
        else:
            contributors = helpers.count_contributors(owner, name)
            if contributors < params.min_contributors:
                continue

        # Activity (recent commits)
        if params.skip_activity:
            commits_recent = -1
        else:
            commits_recent = helpers.count_recent_commits(owner, name, params.since_iso)
            if commits_recent < params.min_commits:
                continue

        # Optional web framework detection (SBOM only)
        frameworks_found: List[str] = []
        if params.detect_webapps:
            frameworks_found = detect_web_frameworks(owner, name, params.frameworks, helpers)
            if params.require_web_frameworks and not frameworks_found:
                continue

        results.append((repo, py_pct, contributors, commits_recent, frameworks_found))

    return results
