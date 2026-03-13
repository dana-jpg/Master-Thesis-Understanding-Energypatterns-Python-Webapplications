import json
import hashlib
from pathlib import Path
from typing import Optional, Dict, Any

CACHE_PATH = Path(".llm_analysis_cache.json")


def compute_hash(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


class AnalysisCache:
    def __init__(self, path: Path = CACHE_PATH):
        self.path = path
        self._cache: Dict[str, Dict[str, Any]] = {}
        self._load()

    def _load(self):
        if self.path.exists():
            self._cache = json.loads(self.path.read_text())
        else:
            self._cache = {}

    def save(self):
        self.path.write_text(json.dumps(self._cache, indent=2))

    def get(self, content_hash: str) -> Optional[Dict[str, Any]]:
        return self._cache.get(content_hash)

    def set(self, content_hash: str, result: Dict[str, Any]):
        self._cache[content_hash] = result
        self.save()
