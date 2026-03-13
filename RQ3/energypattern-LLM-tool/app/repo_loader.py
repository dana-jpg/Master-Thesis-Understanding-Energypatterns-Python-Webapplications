import os
from typing import Set

EXCLUDE_DIRS: Set[str] = {
    ".git",
    ".venv",
    "venv",
    "node_modules",
    "dist",
    "build",
    "__pycache__",
    ".mypy_cache",
}

ALLOWED_EXTENSIONS = (
    ".py",
    ".js",
    ".ts",
    ".java",
    ".c",
    ".cpp",
)

def load_repo_files(state):
    # If files are already provided (e.g. for testing), skip discovery
    if state.files:
        return state

    repo_path = state.repo_path
    files = []

    for root, dirs, filenames in os.walk(repo_path):
        # Prune directories in-place
        dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS]

        for name in filenames:
            if name.startswith("."):
                continue
            if name.endswith(ALLOWED_EXTENSIONS):
                files.append(os.path.join(root, name))

    return state.copy(update={"files": sorted(files)})
