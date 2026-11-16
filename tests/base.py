import json
import os
import shutil
import tempfile
import unittest
from werkzeug.security import generate_password_hash

import app as hr_app
import storage
import notification_service


class BaseTestCase(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.orig_data_file = storage.DATA_FILE
        self.test_data_file = os.path.join(self.tmpdir, "test_data.json")
        storage.DATA_FILE = self.test_data_file

        # Configure upload folder to point to temp uploads
        self.orig_upload_folder = hr_app.app.config.get("UPLOAD_FOLDER")
        self.test_upload_folder = os.path.join(self.tmpdir, "uploads")
        os.makedirs(os.path.join(self.test_upload_folder, "attachments"), exist_ok=True)
        hr_app.app.config["UPLOAD_FOLDER"] = self.test_upload_folder

        hr_app.app.config["TESTING"] = True
        hr_app.app.config["WTF_CSRF_ENABLED"] = False
        self.client = hr_app.app.test_client()

        # Reset email outbox
        notification_service.EMAIL_OUTBOX.clear()

        # Default seed data
        self.seed_data = {
            "positions": [
                {
                    "id": "POS-001",
                    "title": "Senior Backend Engineer",
                    "description": "Python, Flask, PostgreSQL, Docker, CI/CD experience required.",
                    "created_at": "2026-01-01T10:00:00"
                }
            ],
            "candidates": [
                {
                    "id": "CAND-001",
                    "name": "Jordan Smith",
                    "email": "jordan@example.com",
                    "phone": "+1-555-0199",
                    "position_id": "POS-001",
                    "university": "Stanford University",
                    "experience_score": 8.0,
                    "python_score": 9,
                    "uni_tier_score": 10,
                    "final_rank_score": 8.7,
                    "skills": ["Python", "Flask", "Docker"],
                    "stage": "Screening",
                    "status": "pending",
                    "user_id": "USR-001",
                    "timeline": [],
                    "interview": {},
                    "source_file": "jordan_resume.pdf"
                }
            ],
            "users": [
                {
                    "id": "USR-001",
                    "username": "jobseeker",
                    "password": generate_password_hash("password123"),
                    "name": "Job Seeker",
                    "email": "jobseeker@example.com",
                    "created_at": "2026-01-01T10:00:00"
                }
            ],
            "notifications": [],
            "employees": [
                {
                    "id": "EMP-1001",
                    "name": "Alex Rivera",
                    "email": "alex@corp.test",
                    "role": "Full Stack Engineer",
                    "department": "Engineering",
                    "access_role": "employee",
                    "team_lead_id": "EMP-1004",
                    "password": "emp123",
                    "leave_quota": {"casual": 12, "yearly": 15},
                    "salary": {"base": 80000, "allowances": 10000, "deductions": 5000, "net": 85000},
                },
                {
                    "id": "EMP-1002",
                    "name": "Priya Sharma",
                    "email": "priya@corp.test",
                    "role": "Lead Designer",
                    "department": "Product & Design",
                    "access_role": "team_lead",
                    "team_lead_id": None,
                    "password": "emp123",
                    "leave_quota": {"casual": 12, "yearly": 15},
                    "salary": {"base": 90000, "allowances": 10000, "deductions": 5000, "net": 95000},
                },
                {
                    "id": "EMP-1003",
                    "name": "Sarah Jenkins",
                    "email": "sarah@corp.test",
                    "role": "Python Engineer",
                    "department": "Engineering",
                    "access_role": "employee",
                    "team_lead_id": None,
                    "password": "emp123",
                    "leave_quota": {"casual": 12, "yearly": 15},
                    "salary": {"base": 75000, "allowances": 10000, "deductions": 5000, "net": 80000},
                },
                {
                    "id": "EMP-1004",
                    "name": "Marcus Vance",
                    "email": "marcus@corp.test",
                    "role": "Engineering Lead",
                    "department": "Engineering",
                    "access_role": "team_lead",
                    "team_lead_id": None,
                    "password": "emp123",
                    "leave_quota": {"casual": 12, "yearly": 15},
                    "salary": {"base": 100000, "allowances": 15000, "deductions": 8000, "net": 107000},
                },
            ],
            "attendance": [],
            "leave_requests": [],
        }
        with open(self.test_data_file, "w") as f:
            json.dump(self.seed_data, f)

    def tearDown(self):
        storage.DATA_FILE = self.orig_data_file
        if self.orig_upload_folder:
            hr_app.app.config["UPLOAD_FOLDER"] = self.orig_upload_folder
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def login_hr(self):
        with self.client.session_transaction() as sess:
            sess.clear()
        return self.client.post(
            "/hr_login",
            data={"username": "hr_admin", "password": "admin123"},
            follow_redirects=True,
        )

    def login_employee(self, identifier="EMP-1001", password="emp123"):
        with self.client.session_transaction() as sess:
            sess.clear()
        return self.client.post(
            "/employee_login",
            data={"identifier": identifier, "password": password},
            follow_redirects=True,
        )

    def login_applicant(self, username="jobseeker", password="password123"):
        with self.client.session_transaction() as sess:
            sess.clear()
        return self.client.post(
            "/applicant_login",
            data={"username": username, "password": password},
            follow_redirects=True,
        )

    def logout(self):
        return self.client.get("/logout", follow_redirects=True)
