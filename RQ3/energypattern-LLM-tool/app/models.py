from pydantic import BaseModel
from typing import Optional

class Finding(BaseModel):
    file: str
    function_name: Optional[str] = None
    start_line: Optional[int] = None
    end_line: Optional[int] = None
    complexity: Optional[int] = None
    issue: str
    explanation: str
    patch: Optional[str] = None
    problematic_code: Optional[str] = None
    # Taxonomy-aware fields
    taxonomy_category: Optional[str] = None  
    similar_to_example: Optional[str] = None 
    
    def to_dict(self):
        """Convert finding to dictionary for JSON serialization."""
        return {
            "file": self.file,
            "function_name": self.function_name,
            "start_line": self.start_line,
            "end_line": self.end_line,
            "complexity": self.complexity,
            "issue": self.issue,
            "explanation": self.explanation,
            "patch": self.patch,
            "problematic_code": self.problematic_code,
            "taxonomy_category": self.taxonomy_category,
            "similar_to_example": self.similar_to_example,
        }