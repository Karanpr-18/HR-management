import unittest
from agent import ResumeRankingAgent, analyze_resume


class TestAgentAnalysis(unittest.TestCase):
    def setUp(self):
        self.agent = ResumeRankingAgent()

    def test_extract_skills(self):
        sample = "Proficient in Python, Flask, Docker, Kubernetes, and PostgreSQL with experience in Git and CI/CD."
        skills = self.agent._extract_skills(sample)
        # Skills are formatted as Title case or Upper case for short acronyms
        skills_lower = [s.lower() for s in skills]
        self.assertIn("python", skills_lower)
        self.assertIn("flask", skills_lower)
        self.assertIn("docker", skills_lower)
        self.assertIn("kubernetes", skills_lower)
        self.assertIn("postgresql", skills_lower)
        self.assertIn("git", skills_lower)
        self.assertIn("ci/cd", skills_lower)

    def test_university_tier(self):
        score_stanford, _ = self.agent._get_university_tier("Stanford University")
        self.assertEqual(score_stanford, 10)

        score_mit, _ = self.agent._get_university_tier("MIT")
        self.assertEqual(score_mit, 10)

        score_iit, _ = self.agent._get_university_tier("IIT Bombay")
        self.assertEqual(score_iit, 10)

        score_cmu, _ = self.agent._get_university_tier("Carnegie Mellon University")
        self.assertEqual(score_cmu, 8)

        score_other, _ = self.agent._get_university_tier("State College")
        self.assertEqual(score_other, 5)

    def test_rule_based_analysis_structure(self):
        sample_resume = """Jane Doe
Education: Master of Science, Stanford University
Experience: 5 years software engineer specializing in Python, Django, Docker, and AWS.
"""
        jd = "Looking for a Python Developer with Docker and AWS experience."
        result = analyze_resume(sample_resume, job_description=jd, use_ai=False)

        self.assertIsInstance(result, dict)
        self.assertEqual(result["name"], "Jane Doe")
        self.assertIn("Stanford University", result["university"])
        self.assertIn("skills", result)
        skills_lower = [s.lower() for s in result["skills"]]
        self.assertIn("python", skills_lower)
        self.assertEqual(result["uni_tier_score"], 10)
        self.assertGreater(result["final_rank_score"], 0)
        self.assertEqual(result["analysis_method"], "Rule-Based (Fallback)")

    def test_empty_resume_handling(self):
        result = analyze_resume("", job_description="Test JD", use_ai=False)
        self.assertIsInstance(result, dict)
        self.assertEqual(result["name"], "Unknown Candidate")
        self.assertEqual(result["university"], "Unknown Institution")
        self.assertIn("final_rank_score", result)
        self.assertEqual(result["final_rank_score"], 2.0)


if __name__ == "__main__":
    unittest.main()
