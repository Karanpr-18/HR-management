"""
AI Agent for Resume Analysis and Ranking - Enterprise Edition
"""

import json
from typing import Dict, Any, List, Optional
from google import genai
from google.genai import types
from groq import Groq
import os
import re
from dotenv import load_dotenv
from pydantic import ValidationError
from models import CandidateResult

# Load environment variables
load_dotenv()

class ResumeRankingAgent:
    """AI Agent for technical recruitment - resume analysis"""

    # University Tier Database
    TOP_TIER_UNIVERSITIES = {
        "stanford", "mit", "harvard", "caltech", "oxford", "cambridge",
        "princeton", "yale", "columbia", "cornell", "upenn", "berkeley",
        "iit bombay", "iit delhi", "iit madras", "iit kanpur", "iit kharagpur",
        "iit roorkee", "iit guwahati", "iit hyderabad", "iisc",
        "brown", "dartmouth", "penn", "california institute of technology",
    }

    LEADING_NATIONAL_UNIVERSITIES = {
        "nit trichy", "nit warangal", "nit surathkal", "nit calicut",
        "nit durgapur", "nit jamshedpur", "nit allahabad", "nit bhopal",
        "university of michigan", "university of texas", "carnegie mellon",
        "georgia tech", "eth zurich", "ethz", "nus", "national university of singapore",
    }

    def __init__(self, api_key: str = None):
        """Initialize with best available Flash model and Groq fallback"""
        # Initialize Gemini
        self.gemini_key = api_key or os.getenv("GEMINI_API_KEY")
        if self.gemini_key:
            self.gemini_client = genai.Client(api_key=self.gemini_key)
        else:
            self.gemini_client = None
            print("Warning: No API Key found for Gemini.")

        # Initialize Groq
        self.groq_key = os.getenv("GROQ_API_KEY")
        if self.groq_key:
            self.groq_client = Groq(api_key=self.groq_key)
        else:
            self.groq_client = None
            print("Warning: No API Key found for Groq.")

    def _get_university_tier(self, university: str) -> tuple:
        uni_lower = university.lower().strip()
        if any(top in uni_lower for top in self.TOP_TIER_UNIVERSITIES):
            return 10, "Global Top Tier University detected."
        if any(lead in uni_lower for lead in self.LEADING_NATIONAL_UNIVERSITIES):
            return 8, "Leading National University detected."
        return 5, "Standard University tier."

    # Skills Keywords Database for extraction
    SKILL_KEYWORDS = [
        "python", "java", "javascript", "typescript", "c++", "c#", "go", "rust", "ruby", "php",
        "react", "angular", "vue", "node.js", "django", "flask", "fastapi", "spring",
        "sql", "postgresql", "mysql", "mongodb", "redis", "elasticsearch",
        "aws", "azure", "gcp", "docker", "kubernetes", "terraform",
        "machine learning", "deep learning", "tensorflow", "pytorch", "scikit-learn",
        "pandas", "numpy", "data science", "nlp", "computer vision",
        "git", "ci/cd", "agile", "scrum", "rest api", "graphql"
    ]

    def _extract_skills(self, resume_text: str) -> List[str]:
        """Extract skills from resume text using keyword matching."""
        text_lower = resume_text.lower()
        found_skills = []
        for skill in self.SKILL_KEYWORDS:
            if skill in text_lower:
                found_skills.append(skill.title() if len(skill) > 3 else skill.upper())
        return found_skills

    def _calculate_python_score(self, resume_text: str) -> tuple:
        python_keywords = ["python", "pandas", "numpy", "tensorflow", "pytorch", "scikit-learn", "keras", "ml", "ai", "fastapi", "django"]
        text_lower = resume_text.lower()
        keyword_count = sum(1 for kw in python_keywords if kw in text_lower)
        
        match = re.search(r'(\d+(?:\.\d+)?)\+?\s*years?', text_lower)
        years = float(match.group(1)) if match else 0.0

        if keyword_count >= 8 and years >= 4: score = 9
        elif keyword_count >= 4 and years >= 2: score = 7
        elif keyword_count >= 1: score = 5
        else: score = 2

        evidence = f"Found {keyword_count} Python-related keywords and {years} years experience context."
        return score, years, evidence

    def _calculate_experience_score(self, resume_text: str) -> tuple:
        match = re.search(r'(\d+)\+?\s*years?', resume_text.lower())
        years = int(match.group(1)) if match else 0
        impact_keywords = ["led", "managed", "scaled", "optimized", "architected", "impact", "delivered"]
        impact_count = sum(1 for kw in impact_keywords if kw in resume_text.lower())
        
        score = min(10, years * 1.0 + impact_count * 0.5)
        evidence = f"Detected {years} years total experience and {impact_count} impact verbs."
        return score, evidence, years

    def analyze_resume(self, resume_text: str, job_description: str = "") -> Dict[str, Any]:
        """Manual Rule-Based Analysis (High-Quality Fallback)"""
        lines = [l.strip() for l in resume_text.strip().split('\n') if l.strip()]
        name = lines[0] if lines else "Unknown Candidate"
        
        university = "Unknown Institution"
        for line in lines:
            if any(kw in line for kw in ["University", "Institute", "IIT", "NIT", "College"]):
                university = line
                break

        python_score, python_years, python_evidence = self._calculate_python_score(resume_text)
        uni_tier, uni_evidence = self._get_university_tier(university)
        exp_score, exp_evidence, total_years = self._calculate_experience_score(resume_text)
        skills = self._extract_skills(resume_text)

        # NEW FORMULA: (Python * 0.5) + (Experience * 0.3) + (UniTier * 0.2)
        final_rank = (python_score * 0.5) + (exp_score * 0.3) + (uni_tier * 0.2)

        return {
            "name": name,
            "university": university,
            "skills": skills,
            "uni_tier_score": uni_tier,
            "uni_evidence": uni_evidence,
            "python_score": python_score,
            "python_evidence": python_evidence,
            "evidence_quote": python_evidence, # Backward compatibility for UI
            "experience_score": round(exp_score, 1),
            "experience_evidence": exp_evidence,
            "python_experience_years": python_years,
            "final_rank_score": round(final_rank, 2),
            "analysis_method": "Rule-Based (Fallback)"
        }

    def analyze_resume_with_ai(self, resume_text: str, job_description: str) -> Dict[str, Any]:
        """AI-powered Analysis with Pydantic validation and self-correction."""
        
        system_prompt = f"""Role: Expert Technical Recruiter and Data Entry Specialist.
Task: Extract candidate information and analyze resume against Job Description.
Constraint: Evidence-Based. If skill is missing, score 0.

Extraction:
- name: Full name of the candidate
- university: Educational institution name. Extract the exact name as written in the resume.  
- skills: List of technical skills found in resume (e.g. ["Python", "React", "AWS"])

Scoring:
- python_score (0-10): libs, complexity, years
- uni_tier_score (0-10): 10=Top Global, 7-9=Top National, 4-6=Regional, 1-3=Unknown
- experience_score (0-10): Score from 0 to 10 based on quality and years.
IMPORTANT: ALL scores must be between 0 and 10. DO NOT exceed 10.

Output JSON ONLY:
{{
  "name": "Candidate Name",
  "university": "University Name",
  "skills": ["Skill1", "Skill2", "Skill3"],
  "python_score": 0-10,
  "python_evidence": "1-sentence justification",
  "uni_tier_score": 0-10,
  "uni_evidence": "1-sentence justification",
  "experience_score": 0-10,
  "experience_evidence": "1-sentence justification",
  "python_experience_years": float
}}
"""
        
        
        user_content = f"Resume: {resume_text[:12000]}\nJob Description: {job_description[:2000]}"

        # Helper to process JSON response
        def process_json_response(raw_text_input: str) -> Dict[str, Any]:
             # Clean markdown code blocks if present
            raw_text_clean = raw_text_input.strip()
            if raw_text_clean.startswith("```"):
                raw_text_clean = raw_text_clean.split("\n", 1)[1]
                if raw_text_clean.endswith("```"):
                    raw_text_clean = raw_text_clean.rsplit("\n", 1)[0]
            if raw_text_clean.startswith("json"):
                raw_text_clean = raw_text_clean[4:].strip()
                
            data = json.loads(raw_text_clean)
            
            # Sanitize scores (handle LLM hallucinations > 10)
            score_fields = ['python_score', 'uni_tier_score', 'experience_score']
            for field in score_fields:
                if field in data:
                    try:
                        val = int(data[field])
                        data[field] = max(0, min(10, val))
                    except (ValueError, TypeError):
                        data[field] = 0
            
            validated = CandidateResult.model_validate(data)
            return validated.to_storage_dict()

        # Primary: Groq Llama 3.1
        if self.groq_client:
            try:
                print("Using Groq Llama-3.1-8b-instant...")
                chat_completion = self.groq_client.chat.completions.create(
                    messages=[
                        {
                            "role": "system",
                            "content": system_prompt + "\nIMPORTANT: Return ONLY the JSON object. No markdown formatting."
                        },
                        {
                            "role": "user",
                            "content": user_content,
                        }
                    ],
                    model="llama-3.1-8b-instant",
                    temperature=0.1,
                    stream=False,
                    response_format={"type": "json_object"}
                )
                
                content = chat_completion.choices[0].message.content
                if content:
                    result = process_json_response(content)
                    result["analysis_method"] = "Groq Llama-3.1"
                    return result
                    
            except Exception as e:
                print(f"Groq Analysis Failed ({e}). Attempting Gemini fallback...")

        # Fallback/Secondary: Gemini Flash
        if self.gemini_client:
            try:
                # Using gemini-flash-latest as a stable fallback
                model_name = 'gemini-flash-latest' 
                
                print(f"Using Gemini fallback ({model_name})...")
                response = self.gemini_client.models.generate_content(
                    model=model_name,
                    contents=f"{system_prompt}\n{user_content}",
                    config=types.GenerateContentConfig(
                        temperature=0.1,
                        response_mime_type="application/json"
                    )
                )
                
                if response.text:
                    try:
                        result = process_json_response(response.text)
                        result["analysis_method"] = "Gemini Flash (Fallback)"
                        return result
                    except ValidationError as ve:
                         # Gemini Self-correction
                        print(f"Gemini Validation failed, attempting self-correction: {ve}")
                        fix_prompt = f"Fix this invalid JSON based on schema:\n{response.text}\nError: {ve}\nReturn ONLY valid JSON."
                        retry_resp = self.gemini_client.models.generate_content(
                            model=model_name,
                            contents=fix_prompt,
                            config=types.GenerateContentConfig(response_mime_type="application/json")
                        )
                        if retry_resp.text:
                            result = process_json_response(retry_resp.text)
                            result["analysis_method"] = "Gemini Flash (Corrected Fallback)"
                            return result
                        
            except Exception as e:
                print(f"Gemini Analysis Failed ({e}). Using rule-based fallback.")

        # Final Fallback
        return self.analyze_resume(resume_text, job_description)

def analyze_resume(resume_text: str, job_description: str = "", use_ai: bool = False) -> Dict[str, Any]:
    agent = ResumeRankingAgent()
    if use_ai:
        return agent.analyze_resume_with_ai(resume_text, job_description)
    return agent.analyze_resume(resume_text, job_description)

if __name__ == "__main__":
    sample = "Alice White\nData Scientist\nHarvard University\n6 years experience in Python and AI."
    print(json.dumps(analyze_resume(sample, use_ai=False), indent=2))
