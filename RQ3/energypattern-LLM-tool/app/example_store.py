"""
Example Store - Vector-based Retrieval for Code Examples

Uses ChromaDB to store and retrieve before/after code examples
based on semantic similarity to the code being analyzed.
"""

import json
from pathlib import Path
from typing import Optional
import logging

logger = logging.getLogger(__name__)


class ExampleStore:
    """
    Vector store for before/after code optimization examples.
    
    Uses ChromaDB for semantic similarity search to find relevant
    examples that can guide the LLM in identifying similar patterns.
    """
    
    def __init__(self, persist_dir: str = ".chromadb", use_embeddings: bool = True):
        """
        Initialize the example store.
        
        Args:
            persist_dir: Directory to persist ChromaDB data
            use_embeddings: If True, use sentence-transformers for embeddings.
                           If False, use simple keyword matching (fallback).
        """
        self.persist_dir = persist_dir
        self.use_embeddings = use_embeddings
        self._client = None
        self._collection = None
        self._examples_cache: dict[str, dict] = {}
        
    def _get_client(self):
        """Lazy initialization of ChromaDB client."""
        if self._client is None:
            try:
                import chromadb
                self._client = chromadb.PersistentClient(path=self.persist_dir)
            except ImportError:
                logger.warning("ChromaDB not installed. Run: pip install chromadb")
                raise
        return self._client
    
    def _get_collection(self):
        """Get or create the examples collection."""
        if self._collection is None:
            client = self._get_client()
            
            if self.use_embeddings:
                try:
                    from chromadb.utils import embedding_functions
                   
                    embedding_fn = embedding_functions.SentenceTransformerEmbeddingFunction(
                        model_name="all-MiniLM-L6-v2"  
                    )
                    self._collection = client.get_or_create_collection(
                        name="green_code_examples",
                        embedding_function=embedding_fn,
                        metadata={"hnsw:space": "cosine"}
                    )
                except ImportError:
                    logger.warning(
                        "sentence-transformers not installed. "
                        "Falling back to default embeddings. "
                        "Run: pip install sentence-transformers"
                    )
                    self._collection = client.get_or_create_collection(
                        name="green_code_examples"
                    )
            else:
                self._collection = client.get_or_create_collection(
                    name="green_code_examples"
                )
                
        return self._collection
    
    def add_example(self, example: dict) -> None:
        """
        Add a before/after example to the store.
        
        Args:
            example: Dict with keys: id, taxonomy_id, title, description,
                    before (dict with 'code'), after (dict with 'code'),
                    key_insight, energy_impact
        """
        collection = self._get_collection()
        
        # Check if already exists
        existing = collection.get(ids=[example["id"]])
        if existing["ids"]:
            logger.debug(f"Example {example['id']} already exists, updating...")
            collection.delete(ids=[example["id"]])
        
        # Create searchable document from before code + description
        document = f"{example.get('title', '')}\n{example.get('description', '')}\n{example['before']['code']}"
        
        # Store after code and insights in metadata
        metadata = {
            "taxonomy_id": example.get("taxonomy_id", ""),
            "title": example.get("title", ""),
            "key_insight": example.get("key_insight", ""),
            "energy_impact": example.get("energy_impact", ""),
            "language": example.get("language", "python"),
            "source": example.get("source", ""),
        }
        
        collection.add(
            ids=[example["id"]],
            documents=[document],
            metadatas=[metadata]
        )
        
        # Cache the full example for retrieval
        self._examples_cache[example["id"]] = example
        
        logger.debug(f"Added example: {example['id']}")
    
    def find_similar(self, code: str, n_results: int = 3, 
                     category_filter: Optional[str] = None) -> list[dict]:
        """
        Find the most similar examples to the given code.
        
        Args:
            code: The code to find similar examples for
            n_results: Number of results to return
            category_filter: Optional taxonomy_id prefix to filter by
            
        Returns:
            List of dicts with: id, title, before, after, key_insight, 
            taxonomy_id, similarity
        """
        collection = self._get_collection()
        
        # Build where filter if category specified
        where_filter = None
        if category_filter:
            where_filter = {
                "taxonomy_id": {"$contains": category_filter}
            }
        
        try:
            results = collection.query(
                query_texts=[code],
                n_results=n_results,
                where=where_filter,
                include=["documents", "metadatas", "distances"]
            )
        except Exception as e:
            logger.error(f"Error querying examples: {e}")
            return []
        
        if not results["ids"] or not results["ids"][0]:
            return []
        
        output = []
        for i, example_id in enumerate(results["ids"][0]):
            metadata = results["metadatas"][0][i] if results["metadatas"] else {}
            distance = results["distances"][0][i] if results["distances"] else 1.0
            
            # Get full example from cache
            full_example = self._examples_cache.get(example_id, {})
            
            before_code = full_example.get("before", {}).get("code", "")
            after_code = full_example.get("after", {}).get("code", "")
            
            output.append({
                "id": example_id,
                "title": metadata.get("title", ""),
                "before": before_code,
                "after": after_code,
                "key_insight": metadata.get("key_insight", ""),
                "taxonomy_id": metadata.get("taxonomy_id", ""),
                "energy_impact": metadata.get("energy_impact", ""),
                "similarity": 1 - distance, 
            })
        
        return output
    
    def load_all_examples(self, examples_dir: str = "examples") -> int:
        """
        Load all example JSON files from a directory into the store.
        
        Args:
            examples_dir: Path to the examples directory
            
        Returns:
            Number of examples loaded
        """
        examples_path = Path(examples_dir)
        if not examples_path.exists():
            logger.warning(f"Examples directory not found: {examples_dir}")
            return 0
        
        count = 0
        for json_file in examples_path.rglob("*.json"):
            try:
                with open(json_file, "r", encoding="utf-8") as f:
                    example = json.load(f)
                
                # Validate required fields
                if not all(key in example for key in ["id", "before", "after"]):
                    logger.warning(f"Skipping invalid example file: {json_file}")
                    continue
                
                self.add_example(example)
                count += 1
                
            except json.JSONDecodeError as e:
                logger.error(f"Error parsing {json_file}: {e}")
            except Exception as e:
                logger.error(f"Error loading {json_file}: {e}")
        
        logger.info(f"Loaded {count} examples from {examples_dir}")
        return count
    
    def get_example(self, example_id: str) -> Optional[dict]:
        """Get a specific example by ID."""
        return self._examples_cache.get(example_id)
    
    def list_examples(self) -> list[str]:
        """List all example IDs in the store."""
        collection = self._get_collection()
        result = collection.get()
        return result["ids"] if result else []
    
    def clear(self) -> None:
        """Clear all examples from the store."""
        client = self._get_client()
        try:
            client.delete_collection("green_code_examples")
        except Exception:
            pass
        self._collection = None
        self._examples_cache.clear()
        logger.info("Cleared example store")


def format_examples_for_prompt(examples: list[dict], max_examples: int = 2) -> str:
    """
    Format retrieved examples for inclusion in an LLM prompt.
    
    Args:
        examples: List of example dicts from find_similar()
        max_examples: Maximum number of examples to include
        
    Returns:
        Formatted string ready for prompt injection
    """
    if not examples:
        return "No similar examples found."
    
    parts = []
    for i, ex in enumerate(examples[:max_examples], 1):
        example_id = ex.get('id', f'example_{i}')
        parts.append(f"""### Example (ID: `{example_id}`): {ex.get('title', 'Untitled')}
**Example ID to reference**: `{example_id}`
**Category**: `{ex.get('taxonomy_id', 'unknown')}`
**Key Insight**: {ex.get('key_insight', 'N/A')}

**Before (Inefficient)**:
```python
{ex.get('before', '# No before code')}
```

**After (Optimized)**:
```python
{ex.get('after', '# No after code')}
```

**Energy Impact**: {ex.get('energy_impact', 'N/A')}

If you find a similar pattern, set `similar_to_example` to `"{example_id}"` in your response.
""")
    
    return "\n---\n".join(parts)


# Singleton instance for the application
_store_instance: Optional[ExampleStore] = None


def get_example_store(examples_dir: str = "examples") -> ExampleStore:
    """
    Get or create the singleton ExampleStore instance.
    
    Args:
        examples_dir: Path to load examples from on first initialization
        
    Returns:
        The ExampleStore instance
    """
    global _store_instance
    
    if _store_instance is None:
        _store_instance = ExampleStore()
        _store_instance.load_all_examples(examples_dir)
    
    return _store_instance
