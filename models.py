"""
Pydantic Models for Resume Analysis
Provides structured validation for LLM outputs.
"""

from pydantic import BaseModel, Field, field_validator
from typing import List, Optional


class CandidateResult(BaseModel):
    """Validated structure for candidate analysis results."""
    
    name: str = Field(..., description="Candidate's full name")
    university: str = Field(..., description="Educational institution")
    skills: List[str] = Field(default_factory=list, description="List of technical skills")
    
    python_score: int = Field(..., ge=0, le=10, description="Python proficiency score 0-10")
    python_evidence: str = Field(default="", description="Evidence for Python score")
    
    uni_tier_score: int = Field(..., ge=0, le=10, description="University tier score 0-10")
    uni_evidence: str = Field(default="", description="Evidence for university tier")
    
    experience_score: int = Field(..., ge=0, le=10, description="Experience score 0-10")
    experience_evidence: str = Field(default="", description="Evidence for experience")
    
    python_experience_years: float = Field(default=0.0, ge=0, description="Years of Python experience")
    
    @field_validator('name', 'university')
    @classmethod
    def not_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError('Field cannot be empty')
        return v.strip()
    
    @field_validator('skills', mode='before')
    @classmethod
    def ensure_list(cls, v):
        if v is None:
            return []
        if isinstance(v, str):
            return [s.strip() for s in v.split(',') if s.strip()]
        return v
    
    def calculate_final_score(self) -> float:
        """Calculate weighted final score: Python 50% + Experience 30% + Uni 20%"""
        return round(
            (self.python_score * 0.5) + 
            (self.experience_score * 0.3) + 
            (self.uni_tier_score * 0.2), 
            2
        )
    
    def to_storage_dict(self) -> dict:
        """Convert to dictionary format for storage."""
        return {
            "name": self.name,
            "university": self.university,
            "skills": self.skills,
            "python_score": self.python_score,
            "python_evidence": self.python_evidence,
            "evidence_quote": self.python_evidence,  # Backward compatibility
            "uni_tier_score": self.uni_tier_score,
            "uni_evidence": self.uni_evidence,
            "experience_score": self.experience_score,
            "experience_evidence": self.experience_evidence,
            "python_experience_years": self.python_experience_years,
            "final_rank_score": self.calculate_final_score(),
            "analysis_method": "AI Analysis" # Default, can be overridden
        }
