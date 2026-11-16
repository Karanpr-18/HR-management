import io
import unittest
from unittest.mock import patch
from tests.base import BaseTestCase
import storage


class TestRecruitmentPortal(BaseTestCase):
    def test_landing_and_applicant_portal(self):
        # Landing page
        resp = self.client.get("/")
        self.assertEqual(resp.status_code, 200)

        # Applicant portal (anonymous)
        resp = self.client.get("/applicant")
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"Senior Backend Engineer", resp.data)

        # Applicant portal (logged in)
        self.login_applicant()
        resp = self.client.get("/applicant")
        self.assertEqual(resp.status_code, 200)

    def test_position_crud(self):
        self.login_hr()

        # Add position
        resp = self.client.post(
            "/position/add",
            data={"title": "DevOps Architect", "description": "Kubernetes & Terraform lead."},
            follow_redirects=True,
        )
        self.assertEqual(resp.status_code, 200)
        positions = storage.get_all_positions()
        devops_pos = next((p for p in positions if p["title"] == "DevOps Architect"), None)
        self.assertIsNotNone(devops_pos)
        pos_id = devops_pos["id"]

        # Edit position
        resp = self.client.post(
            f"/position/{pos_id}/edit",
            data={"title": "Lead DevOps Architect", "description": "Kubernetes, Terraform & AWS."},
            follow_redirects=True,
        )
        self.assertEqual(resp.status_code, 200)
        updated_pos = storage.get_position(pos_id)
        self.assertEqual(updated_pos["title"], "Lead DevOps Architect")

        # Delete position
        resp = self.client.post(f"/position/{pos_id}/delete", follow_redirects=True)
        self.assertEqual(resp.status_code, 200)
        self.assertIsNone(storage.get_position(pos_id))

    @patch("app.extract_text_from_pdf")
    def test_process_applicant_submission_anonymous_and_logged_in(self, mock_pdf):
        mock_pdf.return_value = "Candidate Taylor\nEmail: taylor@test.local\nStanford University\n5 years Python Flask Docker"

        # Missing file error
        resp = self.client.post("/process_applicant/POS-001", data={}, follow_redirects=True)
        self.assertIn(b"Please upload a resume file.", resp.data)

        # Non-PDF file error
        bad_file = (io.BytesIO(b"bad content"), "resume.txt")
        resp = self.client.post(
            "/process_applicant/POS-001",
            data={"resume_file": bad_file},
            content_type="multipart/form-data",
            follow_redirects=True,
        )
        self.assertIn(b"Only PDF files are allowed.", resp.data)

        # Valid anonymous application
        valid_pdf = (io.BytesIO(b"%PDF-1.4 mock pdf bytes"), "resume.pdf")
        resp = self.client.post(
            "/process_applicant/POS-001",
            data={"resume_file": valid_pdf, "applicant_email": "taylor@test.local"},
            content_type="multipart/form-data",
            follow_redirects=True,
        )
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"Application submitted successfully! Your Application ID is:", resp.data)

        candidates = storage.get_all_candidates()
        cand = next((c for c in candidates if c.get("email") == "taylor@test.local"), None)
        self.assertIsNotNone(cand)
        self.assertEqual(cand["position_id"], "POS-001")

        # Valid application while logged in as applicant
        self.login_applicant()
        valid_pdf_user = (io.BytesIO(b"%PDF-1.4 mock pdf 2"), "resume2.pdf")
        resp = self.client.post(
            "/process_applicant/POS-001",
            data={"resume_file": valid_pdf_user},
            content_type="multipart/form-data",
            follow_redirects=True,
        )
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"Application submitted successfully!", resp.data)

    def test_application_status_check(self):
        # GET page
        resp = self.client.get("/application_status")
        self.assertEqual(resp.status_code, 200)

        # POST with empty ID
        resp = self.client.post("/application_status", data={"application_id": ""})
        self.assertIn(b"Please enter your application ID.", resp.data)

        # POST with nonexistent ID
        resp = self.client.post("/application_status", data={"application_id": "NON-EXISTENT"})
        self.assertIn(b"Application not found. Please check your ID.", resp.data)

        # POST with valid ID
        resp = self.client.post("/application_status", data={"application_id": "CAND-001"})
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"Jordan Smith", resp.data)
        self.assertIn(b"Senior Backend Engineer", resp.data)

    def test_candidate_hub_and_detail(self):
        self.login_hr()

        # Candidate Hub view
        resp = self.client.get("/candidate")
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"Jordan Smith", resp.data)

        # Search filter
        resp = self.client.get("/candidate?q=jordan")
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"Jordan Smith", resp.data)

        # Candidate detail redirect
        resp = self.client.get("/candidate/CAND-001")
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/candidate?id=CAND-001", resp.headers["Location"])

        # Candidate detail scores view
        resp = self.client.get("/candidate/CAND-001?view=scores")
        self.assertEqual(resp.status_code, 200)

    def test_candidate_messaging_and_attachments(self):
        self.login_hr()

        # HR sends message to candidate
        resp = self.client.post(
            "/candidate/CAND-001/message",
            data={"content": "Welcome Jordan! We are scheduling your technical interview."},
            follow_redirects=True,
        )
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"Message and attachment sent to candidate.", resp.data)

        timeline = storage.get_candidate_timeline("CAND-001")
        self.assertTrue(any("scheduling your technical interview" in ev["content"] for ev in timeline))

        # HR posts internal note
        resp = self.client.post(
            "/candidate/CAND-001/message",
            data={"content": "Strong Python score, proceed with lead architect round.", "send_to": "admin"},
            follow_redirects=True,
        )
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"Internal note saved.", resp.data)

        # Candidate replies
        resp = self.client.post(
            "/candidate/CAND-001/applicant_reply",
            data={"content": "Thank you! I am ready for the interview."},
            follow_redirects=True,
        )
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"Your message was sent to the HR recruitment team.", resp.data)

        # Test valid attachment upload
        test_file = (io.BytesIO(b"Candidate assignment answers"), "assignment.pdf")
        resp = self.client.post(
            "/candidate/CAND-001/message",
            data={"content": "Here is the take-home prompt", "attachment": test_file},
            content_type="multipart/form-data",
            follow_redirects=True,
        )
        self.assertEqual(resp.status_code, 200)

        # Test invalid file format attachment
        bad_file = (io.BytesIO(b"executable payload"), "script.exe")
        resp = self.client.post(
            "/candidate/CAND-001/message",
            data={"content": "Invalid file test", "attachment": bad_file},
            content_type="multipart/form-data",
            follow_redirects=True,
        )
        self.assertIn(b"is not supported", resp.data)

    def test_interview_scheduling_and_reschedule_flow(self):
        self.login_hr()

        # 1. HR schedules interview
        resp = self.client.post(
            "/candidate/CAND-001/schedule",
            data={
                "date": "2026-11-20",
                "time": "14:00",
                "round_title": "System Design Round",
                "meeting_link": "https://meet.test/sys-design",
                "hr_note": "Please have your camera on."
            },
            follow_redirects=True,
        )
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"Interview invitation sent to Jordan Smith", resp.data)

        cand = storage.get_candidate("CAND-001")
        self.assertEqual(cand["interview"]["status"], "pending_candidate_response")
        self.assertEqual(cand["interview"]["date"], "2026-11-20")

        # 2. Candidate requests reschedule
        self.login_applicant()
        resp = self.client.post(
            "/candidate/CAND-001/interview_action",
            data={
                "action": "reschedule",
                "proposed_date": "2026-11-21",
                "proposed_time": "16:00",
                "reason": "Prior work commitment at 2pm"
            },
            follow_redirects=True,
        )
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"Reschedule request sent to HR.", resp.data)

        cand = storage.get_candidate("CAND-001")
        self.assertEqual(cand["interview"]["status"], "reschedule_requested")
        self.assertEqual(cand["interview"]["reschedule_request"]["proposed_date"], "2026-11-21")

        # 3. HR approves reschedule
        self.login_hr()
        resp = self.client.post(
            "/candidate/CAND-001/resolve_reschedule",
            data={"decision": "approve"},
            follow_redirects=True,
        )
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"reschedule request approved! Interview confirmed.", resp.data)

        cand = storage.get_candidate("CAND-001")
        self.assertEqual(cand["interview"]["status"], "confirmed")
        self.assertEqual(cand["interview"]["date"], "2026-11-21")
        self.assertEqual(cand["interview"]["time"], "16:00")

    def test_candidate_stage_update_and_conversion_to_employee(self):
        self.login_hr()

        # Update stage to Finished
        resp = self.client.post(
            "/candidate/CAND-001/stage",
            data={"stage": "Finished"},
            follow_redirects=True,
        )
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"Candidate stage advanced", resp.data)
        self.assertIn(b"Finished", resp.data)

        # Convert to employee
        resp = self.client.post(
            "/candidate/CAND-001/convert_to_employee",
            data={
                "department": "Engineering",
                "role": "Senior Backend Engineer",
                "base_salary": "95000",
                "allowances": "12000",
                "deductions": "6000",
                "access_role": "employee",
                "team_lead_id": "EMP-1004",
                "casual_quota": "12",
                "yearly_quota": "15"
            },
            follow_redirects=True,
        )
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"successfully shifted to Current Employees!", resp.data)

        # Check candidate is now mapped
        cand = storage.get_candidate("CAND-001")
        self.assertIsNotNone(cand.get("employee_id"))
        new_emp = storage.get_employee(cand["employee_id"])
        self.assertEqual(new_emp["name"], "Jordan Smith")
        self.assertEqual(new_emp["department"], "Engineering")
        self.assertEqual(new_emp["salary"]["base"], 95000)
        self.assertEqual(new_emp["team_lead_id"], "EMP-1004")

    def test_candidate_deletion(self):
        self.login_hr()
        resp = self.client.post("/delete_candidate/CAND-001", follow_redirects=True)
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"Candidate deleted successfully.", resp.data)
        self.assertIsNone(storage.get_candidate("CAND-001"))


if __name__ == "__main__":
    unittest.main()
