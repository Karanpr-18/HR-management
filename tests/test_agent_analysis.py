import io
import unittest
from unittest.mock import patch
from tests.base import BaseTestCase
import storage


class TestAgentAnalysisRoutes(BaseTestCase):
    def test_analyze_page_flow(self):
        # Position exists in seed data
        resp = self.client.get("/analyze")
        self.assertEqual(resp.status_code, 200)

        resp_pos = self.client.get("/analyze/POS-001")
        self.assertEqual(resp_pos.status_code, 200)

    def test_setup_job_legacy(self):
        resp = self.client.post(
            "/setup_job",
            data={"job_description": "We are seeking a senior Flask Python engineer."},
            follow_redirects=False,
        )
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/analyze", resp.headers["Location"])
        self.assertEqual(storage.get_job_description(), "We are seeking a senior Flask Python engineer.")

    def test_process_analysis_fallback_text_and_errors(self):
        # Empty input returns 400
        resp_empty = self.client.post("/process_analysis", data={})
        self.assertEqual(resp_empty.status_code, 400)

        # Valid text input analyzes and saves candidate
        sample_text = """Morgan Blake
Stanford University
5 years software engineering experience in Python, Flask, Docker, and PostgreSQL.
"""
        resp = self.client.post(
            "/process_analysis",
            data={"resume_text": sample_text, "position_id": "POS-001"},
            follow_redirects=False,
        )
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/candidate/", resp.headers["Location"])

        # Check candidate was saved in storage
        candidates = storage.get_all_candidates()
        saved = next((c for c in candidates if c.get("name") == "Morgan Blake"), None)
        self.assertIsNotNone(saved)
        self.assertEqual(saved["position_id"], "POS-001")
        self.assertGreater(saved["final_rank_score"], 0)

    def test_api_analyze_endpoint(self):
        # Missing resume_text returns 400
        resp_bad = self.client.post("/api/analyze", json={})
        self.assertEqual(resp_bad.status_code, 400)
        self.assertFalse(resp_bad.get_json().get("success"))

        # Valid JSON payload
        sample_text = "Taylor Reed\nMIT graduate\n4 years experience with Python, React, and AWS."
        resp = self.client.post(
            "/api/analyze",
            json={
                "resume_text": sample_text,
                "job_description": "Python, React and AWS skills needed",
                "use_ai": False
            }
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertTrue(data.get("success"))
        candidate_data = data.get("data")
        self.assertIsNotNone(candidate_data.get("id"))
        self.assertEqual(candidate_data.get("name"), "Taylor Reed")
        self.assertIn("Python", candidate_data.get("skills"))


if __name__ == "__main__":
    unittest.main()
