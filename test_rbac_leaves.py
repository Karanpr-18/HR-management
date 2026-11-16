import json
import os
import shutil
import tempfile
import unittest

import app as hr_app
import storage


class TestRBACAndTwoTierLeaves(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.orig_data_file = storage.DATA_FILE
        self.test_data_file = os.path.join(self.tmpdir, "test_data.json")
        storage.DATA_FILE = self.test_data_file

        seed = {
            "positions": [],
            "candidates": [],
            "users": [],
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
                    "team_lead_id": None,  # Unassigned intentionally
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
            json.dump(seed, f)

        hr_app.app.config["TESTING"] = True
        self.client = hr_app.app.test_client()

    def tearDown(self):
        storage.DATA_FILE = self.orig_data_file
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _login_employee(self, identifier):
        with self.client.session_transaction() as sess:
            sess.clear()
        return self.client.post(
            "/employee_login",
            data={"identifier": identifier, "password": "emp123"},
            follow_redirects=True,
        )

    def _login_hr(self):
        with self.client.session_transaction() as sess:
            sess.clear()
        return self.client.post(
            "/hr_login",
            data={"username": "hr_admin", "password": "admin123"},
            follow_redirects=True,
        )

    def test_legacy_migration_enforces_casual_cap_and_roles(self):
        legacy_file = os.path.join(self.tmpdir, "legacy.json")
        real_data_path = os.path.join(os.path.dirname(__file__), "data.json")
        if os.path.exists(real_data_path):
            shutil.copy2(real_data_path, legacy_file)
            storage.DATA_FILE = legacy_file
            employees = storage.get_all_employees()
            self.assertTrue(any(e.get("access_role") == "team_lead" for e in employees))
            for emp in employees:
                stats = storage.get_employee_year_leave_stats(emp["id"], year=2026)
                self.assertLessEqual(stats["approved_casual"], 12)
                self.assertNotIn("sick", emp.get("leave_balance", {}))
                self.assertNotIn("paid", emp.get("leave_balance", {}))
            leaves = storage.get_all_leave_requests()
            self.assertFalse(any(l.get("status") == "pending" for l in leaves))

    def test_no_direct_employee_to_hr_routing_and_guards(self):
        # Unassigned employee cannot submit leave
        self._login_employee("EMP-1003")
        resp = self.client.post(
            "/employee/apply_leave",
            data={"start_date": "2026-11-16", "end_date": "2026-11-17", "reason": "Vacation"},
            follow_redirects=True,
        )
        self.assertIn(b"No Team Lead is assigned", resp.data)
        self.assertEqual(len(storage.get_all_leave_requests()), 0)

        # Assigned employee submits leave -> goes to Team Lead (pending_lead), not HR
        self._login_employee("EMP-1001")
        resp = self.client.post(
            "/employee/apply_leave",
            data={"start_date": "2026-11-16", "end_date": "2026-11-17", "reason": "Family trip"},
            follow_redirects=True,
        )
        self.assertIn(b"Team Lead Marcus Vance", resp.data)
        leaves = storage.get_all_leave_requests()
        self.assertEqual(len(leaves), 1)
        leave = leaves[0]
        self.assertEqual(leave["status"], "pending_lead")

        # HR must not receive a new leave notification yet
        hr_notifs = storage.get_notifications(recipient_type="hr", recipient_id="hr_admin")
        self.assertEqual(len(hr_notifs), 0)

        # Standard employee cannot call Team Lead or HR review routes
        resp_tl = self.client.post(
            f"/team_lead/leave/{leave['id']}/review",
            data={"decision": "approve"},
            follow_redirects=True,
        )
        self.assertIn(b"Team Lead permissions required", resp_tl.data)
        self.assertEqual(storage.get_all_leave_requests()[0]["status"], "pending_lead")

        # HR cannot directly approve a pending_lead leave
        self._login_hr()
        resp_hr = self.client.post(
            f"/hr/leave/{leave['id']}/review",
            data={"decision": "approved"},
            follow_redirects=True,
        )
        self.assertIn(b"must be approved by their Team Lead before HR review", resp_hr.data)
        self.assertEqual(storage.get_all_leave_requests()[0]["status"], "pending_lead")

    def test_cross_team_lead_rejection_and_live_demotion_guard(self):
        self._login_employee("EMP-1001")
        self.client.post(
            "/employee/apply_leave",
            data={"start_date": "2026-11-18", "end_date": "2026-11-19", "reason": "Rest"},
        )
        leave_id = storage.get_all_leave_requests()[0]["id"]

        # Wrong Team Lead (EMP-1002 Priya) cannot review EMP-1001 (reports to EMP-1004 Marcus)
        self._login_employee("EMP-1002")
        resp = self.client.post(
            f"/team_lead/leave/{leave_id}/review",
            data={"decision": "approve"},
            follow_redirects=True,
        )
        self.assertIn(b"employees assigned to your team", resp.data)
        self.assertEqual(storage.get_all_leave_requests()[0]["status"], "pending_lead")

        # Correct Team Lead (EMP-1004 Marcus) rejects -> stops at rejected_by_lead
        self._login_employee("EMP-1004")
        resp = self.client.post(
            f"/team_lead/leave/{leave_id}/review",
            data={"decision": "reject", "remarks": "Release sprint conflict"},
            follow_redirects=True,
        )
        self.assertIn(b"Rejected", resp.data)
        self.assertEqual(storage.get_all_leave_requests()[0]["status"], "rejected_by_lead")

        # Live role revocation: demote EMP-1004 while still logged in
        storage.update_employee("EMP-1004", {"access_role": "employee"})
        resp_demoted = self.client.post(
            f"/team_lead/leave/{leave_id}/review",
            data={"decision": "approve"},
            follow_redirects=True,
        )
        self.assertIn(b"Team Lead permissions required", resp_demoted.data)
        # Direct report EMP-1001 should have been cleared when EMP-1004 was demoted
        self.assertIsNone(storage.get_employee("EMP-1001").get("team_lead_id"))

    def test_casual_first_12_cap_auto_spill_and_hr_approval(self):
        # 1) Submit 5 days (2026-11-02 to 2026-11-06, Mon-Fri) -> 5 Casual, 0 Yearly
        self._login_employee("EMP-1001")
        self.client.post(
            "/employee/apply_leave",
            data={"start_date": "2026-11-02", "end_date": "2026-11-06", "reason": "Trip 1"},
        )
        l1 = storage.get_all_leave_requests()[0]
        self.assertEqual((l1["casual_days"], l1["yearly_days"]), (5, 0))

        # Team Lead approves & forwards -> still NOT deducted until HR approves
        self._login_employee("EMP-1004")
        self.client.post(f"/team_lead/leave/{l1['id']}/review", data={"decision": "approve"})
        self.assertEqual(storage.get_all_leave_requests()[0]["status"], "pending_hr")
        self.assertEqual(storage.get_employee("EMP-1001")["leave_balance"]["casual"], 12)

        # HR approves l1 -> casual drops to 7 (5 used) and attendance marked On Leave
        self._login_hr()
        self.client.post(f"/hr/leave/{l1['id']}/review", data={"decision": "approved", "remarks": "OK"})
        bal = storage.get_employee("EMP-1001")["leave_balance"]
        self.assertEqual(bal["casual"], 7)
        self.assertEqual(bal["yearly"], 15)
        att_days = [a for a in storage.get_employee_attendance("EMP-1001", "2026-11") if a["status"] == "On Leave"]
        self.assertEqual(len(att_days), 5)

        # 2) Submit 10 days (2026-11-09 to 2026-11-18) -> 7 Casual + 3 Yearly auto-split
        self._login_employee("EMP-1001")
        self.client.post(
            "/employee/apply_leave",
            data={"start_date": "2026-11-09", "end_date": "2026-11-18", "reason": "Trip 2"},
        )
        l2 = storage.get_all_leave_requests()[0]
        self.assertEqual((l2["casual_days"], l2["yearly_days"]), (7, 3))
        self.assertIn("Mixed", l2["leave_type"])

        self._login_employee("EMP-1004")
        self.client.post(f"/team_lead/leave/{l2['id']}/review", data={"decision": "approve"})
        self._login_hr()
        self.client.post(f"/hr/leave/{l2['id']}/review", data={"decision": "approved"})

        bal2 = storage.get_employee("EMP-1001")["leave_balance"]
        self.assertEqual(bal2["casual"], 0)
        self.assertEqual(bal2["casual_used"], 12)
        self.assertEqual(bal2["yearly"], 12)
        self.assertEqual(bal2["yearly_used"], 3)

        # 3) Submit 2 more days -> strictly 0 Casual + 2 Yearly
        self._login_employee("EMP-1001")
        self.client.post(
            "/employee/apply_leave",
            data={"start_date": "2026-12-01", "end_date": "2026-12-02", "reason": "Trip 3"},
        )
        l3 = storage.get_all_leave_requests()[0]
        self.assertEqual((l3["casual_days"], l3["yearly_days"]), (0, 2))
        self.assertEqual(l3["leave_type"], "Yearly Leave")

        # 4) Overlapping dates rejected
        resp_overlap = self.client.post(
            "/employee/apply_leave",
            data={"start_date": "2026-12-02", "end_date": "2026-12-03", "reason": "Overlap"},
            follow_redirects=True,
        )
        self.assertIn(b"overlap", resp_overlap.data.lower())

        # 5) Cross-year dates rejected
        resp_cross = self.client.post(
            "/employee/apply_leave",
            data={"start_date": "2026-12-30", "end_date": "2027-01-02", "reason": "NYE"},
            follow_redirects=True,
        )
        self.assertIn(b"calendar years", resp_cross.data)

    def test_team_lead_own_leave_goes_direct_to_hr(self):
        self._login_employee("EMP-1004")
        resp = self.client.post(
            "/employee/apply_leave",
            data={"start_date": "2026-11-23", "end_date": "2026-11-24", "reason": "Personal"},
            follow_redirects=True,
        )
        self.assertIn(b"sent to HR Admin", resp.data)
        leave = storage.get_all_leave_requests()[0]
        self.assertEqual(leave["status"], "pending_hr")

        # Team Lead cannot self-review their own leave
        with self.assertRaises(PermissionError):
            storage.team_lead_review_leave(leave["id"], "EMP-1004", "approve")

        self._login_hr()
        self.client.post(f"/hr/leave/{leave['id']}/review", data={"decision": "approved"})
        self.assertEqual(storage.get_employee("EMP-1004")["leave_balance"]["casual"], 10)

    def test_hr_only_casual_yearly_conversion_and_12_cap_enforcement(self):
        # Create two approved Casual leaves (5 + 5 = 10 casual) and one approved Yearly leave (4 yearly)
        l1 = storage.submit_leave_request("EMP-1001", "2026-06-01", "2026-06-05", "L1")
        storage.team_lead_review_leave(l1["id"], "EMP-1004", "approve")
        storage.hr_review_leave_request(l1["id"], "approved")

        l2 = storage.submit_leave_request("EMP-1001", "2026-07-01", "2026-07-05", "L2")
        storage.team_lead_review_leave(l2["id"], "EMP-1004", "approve")
        storage.hr_review_leave_request(l2["id"], "approved")

        # Pending HR leave of 4 days -> HR overrides to Yearly during approval
        l3 = storage.submit_leave_request("EMP-1001", "2026-08-03", "2026-08-06", "L3")
        storage.team_lead_review_leave(l3["id"], "EMP-1004", "approve")
        storage.hr_review_leave_request(l3["id"], "approved", override_mode="yearly")

        bal = storage.get_employee("EMP-1001")["leave_balance"]
        self.assertEqual(bal["casual_used"], 10)
        self.assertEqual(bal["yearly_used"], 4)

        # Non-HR cannot call convert_type
        self._login_employee("EMP-1004")
        resp_unauth = self.client.post(
            f"/hr/leave/{l3['id']}/convert_type",
            data={"target_mode": "casual"},
            follow_redirects=True,
        )
        self.assertIn(b"login as HR", resp_unauth.data)

        # HR tries converting 4-day Yearly -> Casual when 10 already used (10 + 4 = 14 > 12) -> blocked!
        self._login_hr()
        resp_cap = self.client.post(
            f"/hr/leave/{l3['id']}/convert_type",
            data={"target_mode": "casual"},
            follow_redirects=True,
        )
        self.assertIn(b"Casual leave cannot exceed 12 days per year", resp_cap.data)
        self.assertEqual(storage.get_employee("EMP-1001")["leave_balance"]["casual_used"], 10)

        # HR converts 5-day l2 Casual -> Yearly -> succeeds (casual_used=5, yearly_used=9)
        resp_ok1 = self.client.post(
            f"/hr/leave/{l2['id']}/convert_type",
            data={"target_mode": "yearly", "reason": "Reclassified by HR"},
            follow_redirects=True,
        )
        self.assertIn(b"reclassified to Yearly Leave", resp_ok1.data)
        bal_after_1 = storage.get_employee("EMP-1001")["leave_balance"]
        self.assertEqual(bal_after_1["casual_used"], 5)
        self.assertEqual(bal_after_1["casual"], 7)
        self.assertEqual(bal_after_1["yearly_used"], 9)

        # Attendance note for l2 dates updated
        att_july = [a for a in storage.get_employee_attendance("EMP-1001", "2026-07") if a["date"] == "2026-07-01"]
        self.assertEqual(att_july[0]["notes"], "Approved Yearly Leave")

        # Now converting 4-day l3 Yearly -> Casual succeeds (5 + 4 = 9 <= 12)
        resp_ok2 = self.client.post(
            f"/hr/leave/{l3['id']}/convert_type",
            data={"target_mode": "casual"},
            follow_redirects=True,
        )
        self.assertIn(b"reclassified to Casual Leave", resp_ok2.data)
        bal_after_2 = storage.get_employee("EMP-1001")["leave_balance"]
        self.assertEqual(bal_after_2["casual_used"], 9)
        self.assertEqual(bal_after_2["yearly_used"], 5)

    def test_ui_rendering_and_hr_employee_role_management(self):
        # 1) Employee login page shows Team Lead and Employee demo badges
        resp_login = self.client.get("/employee_login")
        self.assertEqual(resp_login.status_code, 200)
        self.assertIn(b"Team Lead", resp_login.data)
        self.assertIn(b"Employee", resp_login.data)

        # 2) Standard employee dashboard shows 2 leave cards & NO Team Leave Approvals tab
        self._login_employee("EMP-1001")
        resp_emp = self.client.get("/employee_dashboard")
        self.assertEqual(resp_emp.status_code, 200)
        self.assertIn(b"Casual Leave Remaining", resp_emp.data)
        self.assertIn(b"Yearly Leave Remaining", resp_emp.data)
        self.assertNotIn(b"portal-tab-team_approvals", resp_emp.data)

        # Submit leave -> check Team Lead sees it in UI and HR sees read-only monitor
        self.client.post(
            "/employee/apply_leave",
            data={"start_date": "2026-11-25", "end_date": "2026-11-26", "reason": "Medical check"},
        )

        self._login_employee("EMP-1004")
        resp_lead = self.client.get("/employee_dashboard?tab=team_approvals")
        self.assertEqual(resp_lead.status_code, 200)
        self.assertIn(b"portal-tab-team_approvals", resp_lead.data)
        self.assertIn(b"Approve &amp; Forward to HR", resp_lead.data)
        resp_team = self.client.get("/employee_dashboard?tab=my_team")
        self.assertEqual(resp_team.status_code, 200)
        self.assertIn(b"Alex Rivera", resp_team.data)

        # Employee notifications API with scope=employee
        notif_resp = self.client.get("/api/notifications?scope=employee").get_json()
        self.assertTrue(notif_resp["success"])
        self.assertGreaterEqual(notif_resp["unread_count"], 1)
        mark_resp = self.client.post("/api/notifications/mark_all_read?scope=employee").get_json()
        self.assertTrue(mark_resp["success"])
        notif_after = self.client.get("/api/notifications?scope=employee").get_json()
        self.assertEqual(notif_after["unread_count"], 0)

        # 3) HR panel shows pending_lead in read-only monitor (no HR approve button yet)
        self._login_hr()
        resp_hr_leaves = self.client.get("/employees?tab=leaves")
        self.assertEqual(resp_hr_leaves.status_code, 200)
        self.assertIn(b"Awaiting Team Lead Approval", resp_hr_leaves.data)

        # 4) HR adds a new employee assigned to EMP-1002 and edits yearly quota
        resp_add = self.client.post(
            "/employee/add",
            data={
                "name": "Maya Lin",
                "email": "maya@corp.test",
                "role": "UI Engineer",
                "department": "Product & Design",
                "access_role": "employee",
                "team_lead_id": "EMP-1002",
                "yearly_quota": "20",
                "base_salary": "82000",
                "allowances": "10000",
            },
            follow_redirects=True,
        )
        self.assertEqual(resp_add.status_code, 200)
        self.assertIn(b"Maya Lin", resp_add.data)
        maya = storage.get_employee_by_email("maya@corp.test")
        self.assertIsNotNone(maya)
        self.assertEqual(maya["team_lead_id"], "EMP-1002")
        self.assertEqual(maya["leave_quota"]["casual"], 12)
        self.assertEqual(maya["leave_quota"]["yearly"], 20)

        # Edit employee to Team Lead
        resp_edit = self.client.post(
            f"/employee/{maya['id']}/edit",
            data={
                "role": "Lead UI Engineer",
                "department": "Product & Design",
                "access_role": "team_lead",
                "team_lead_id": "",
                "yearly_quota": "18",
                "base_salary": "90000",
                "allowances": "10000",
                "deductions": "4000",
                "status": "Active",
            },
            follow_redirects=True,
        )
        self.assertEqual(resp_edit.status_code, 200)
        maya_updated = storage.get_employee(maya["id"])
        self.assertEqual(maya_updated["access_role"], "team_lead")
        self.assertIsNone(maya_updated["team_lead_id"])
        self.assertEqual(maya_updated["leave_quota"]["yearly"], 18)

    def test_edit_casual_leave_quota_reduce_and_max_12_cap(self):
        self._login_hr()

        # 1) Cannot create employee with casual_quota > 12
        resp_add_over = self.client.post(
            "/employee/add",
            data={
                "name": "Over Cap",
                "email": "overcap@corp.test",
                "role": "QA",
                "department": "Engineering",
                "access_role": "employee",
                "team_lead_id": "EMP-1004",
                "casual_quota": "15",
                "yearly_quota": "15",
            },
            follow_redirects=True,
        )
        self.assertIn(b"Casual leave cannot exceed 12 days per year", resp_add_over.data)
        self.assertIsNone(storage.get_employee_by_email("overcap@corp.test"))

        # 2) EMP-1001 starts at 12 casual quota -> HR cannot edit casual_quota > 12 (e.g. 13)
        resp_edit_over = self.client.post(
            "/employee/EMP-1001/edit",
            data={
                "role": "Full Stack Engineer",
                "department": "Engineering",
                "access_role": "employee",
                "team_lead_id": "EMP-1004",
                "casual_quota": "13",
                "yearly_quota": "15",
                "base_salary": "80000",
                "allowances": "10000",
                "deductions": "5000",
                "status": "Active",
            },
            follow_redirects=True,
        )
        self.assertIn(b"Casual leave cannot exceed 12 days per year", resp_edit_over.data)
        self.assertEqual(storage.get_employee("EMP-1001")["leave_quota"]["casual"], 12)

        # 3) HR CAN reduce EMP-1001 casual_quota from 12 down to 7
        resp_reduce = self.client.post(
            "/employee/EMP-1001/edit",
            data={
                "role": "Full Stack Engineer",
                "department": "Engineering",
                "access_role": "employee",
                "team_lead_id": "EMP-1004",
                "casual_quota": "7",
                "yearly_quota": "15",
                "base_salary": "80000",
                "allowances": "10000",
                "deductions": "5000",
                "status": "Active",
            },
            follow_redirects=True,
        )
        self.assertEqual(resp_reduce.status_code, 200)
        emp = storage.get_employee("EMP-1001")
        self.assertEqual(emp["leave_quota"]["casual"], 7)
        self.assertEqual(emp["leave_balance"]["casual"], 7)

        # 4) Submitting 10-day leave now auto-splits 7 Casual + 3 Yearly (respecting reduced quota 7)
        self._login_employee("EMP-1001")
        self.client.post(
            "/employee/apply_leave",
            data={"start_date": "2026-09-01", "end_date": "2026-09-10", "reason": "Long trip"},
        )
        l1 = storage.get_all_leave_requests()[0]
        self.assertEqual((l1["casual_days"], l1["yearly_days"]), (7, 3))

        self._login_employee("EMP-1004")
        self.client.post(f"/team_lead/leave/{l1['id']}/review", data={"decision": "approve"})
        self._login_hr()
        self.client.post(f"/hr/leave/{l1['id']}/review", data={"decision": "approved"})

        # 5) HR cannot convert all 10 days to Casual since reduced quota is 7
        resp_conv = self.client.post(
            f"/hr/leave/{l1['id']}/convert_type",
            data={"target_mode": "casual"},
            follow_redirects=True,
        )
        self.assertIn(b"Casual leave cannot exceed 7 days per year", resp_conv.data)

        # 6) HR can also reduce casual_quota down to 0
        resp_zero = self.client.post(
            "/employee/EMP-1001/edit",
            data={
                "role": "Full Stack Engineer",
                "department": "Engineering",
                "access_role": "employee",
                "team_lead_id": "EMP-1004",
                "casual_quota": "0",
                "yearly_quota": "15",
                "base_salary": "80000",
                "allowances": "10000",
                "deductions": "5000",
                "status": "Active",
            },
            follow_redirects=True,
        )
        self.assertEqual(resp_zero.status_code, 200)
        emp_zero = storage.get_employee("EMP-1001")
        self.assertEqual(emp_zero["leave_quota"]["casual"], 0)
        self.assertEqual(emp_zero["leave_balance"]["casual"], 0)


if __name__ == "__main__":
    unittest.main()
