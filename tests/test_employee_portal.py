import unittest
from tests.base import BaseTestCase
import storage


class TestEmployeePortal(BaseTestCase):
    def test_employees_panel_as_hr(self):
        self.login_hr()
        resp = self.client.get("/employees")
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"Alex Rivera", resp.data)
        self.assertIn(b"Marcus Vance", resp.data)

        # Tab navigation
        resp_att = self.client.get("/employees?tab=attendance")
        self.assertEqual(resp_att.status_code, 200)
        resp_leaves = self.client.get("/employees?tab=leaves")
        self.assertEqual(resp_leaves.status_code, 200)

    def test_add_employee_valid_and_invalid_quotas(self):
        self.login_hr()

        # Invalid quota: casual > 12
        resp = self.client.post(
            "/employee/add",
            data={
                "name": "Devin Cole",
                "email": "devin@corp.test",
                "phone": "555-1234",
                "role": "QA Engineer",
                "department": "Engineering",
                "access_role": "employee",
                "team_lead_id": "EMP-1004",
                "base_salary": "70000",
                "allowances": "8000",
                "deductions": "3000",
                "casual_quota": "20",  # Exceeds cap 12
                "yearly_quota": "15"
            },
            follow_redirects=True,
        )
        self.assertIn(b"Casual leave cannot exceed 12 days per year", resp.data)

        # Valid employee creation
        resp = self.client.post(
            "/employee/add",
            data={
                "name": "Devin Cole",
                "email": "devin@corp.test",
                "phone": "555-1234",
                "role": "QA Engineer",
                "department": "Engineering",
                "access_role": "employee",
                "team_lead_id": "EMP-1004",
                "base_salary": "70000",
                "allowances": "8000",
                "deductions": "3000",
                "casual_quota": "10",
                "yearly_quota": "15"
            },
            follow_redirects=True,
        )
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"added to directory!", resp.data)

        emps = storage.get_all_employees()
        new_emp = next((e for e in emps if e["email"] == "devin@corp.test"), None)
        self.assertIsNotNone(new_emp)
        self.assertEqual(new_emp["leave_quota"]["casual"], 10)
        self.assertEqual(new_emp["leave_quota"]["yearly"], 15)
        self.assertEqual(new_emp["salary"]["net"], 75000)

    def test_edit_and_delete_employee(self):
        self.login_hr()

        # Edit employee EMP-1001
        resp = self.client.post(
            "/employee/EMP-1001/edit",
            data={
                "role": "Lead Architect",
                "department": "Core Platform",
                "status": "Active",
                "access_role": "team_lead",
                "team_lead_id": "",
                "base_salary": "120000",
                "allowances": "20000",
                "deductions": "10000",
                "casual_quota": "12",
                "yearly_quota": "20"
            },
            follow_redirects=True,
        )
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"updated successfully", resp.data)

        updated_emp = storage.get_employee("EMP-1001")
        self.assertEqual(updated_emp["role"], "Lead Architect")
        self.assertEqual(updated_emp["access_role"], "team_lead")
        self.assertEqual(updated_emp["department"], "Core Platform")
        self.assertEqual(updated_emp["salary"]["net"], 130000)

        # Delete employee EMP-1003
        resp = self.client.post("/employee/EMP-1003/delete", follow_redirects=True)
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"Employee removed from directory.", resp.data)
        self.assertIsNone(storage.get_employee("EMP-1003"))

    def test_employee_dashboard_views(self):
        # 1. Standard employee view
        self.login_employee("EMP-1001")
        resp = self.client.get("/employee_dashboard")
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"Alex Rivera", resp.data)
        self.assertIn(b"Marcus Vance", resp.data)  # Assigned Team Lead

        # 2. Team lead view with approvals tab
        self.login_employee("EMP-1004")
        resp = self.client.get("/employee_dashboard?tab=team_approvals")
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"Marcus Vance", resp.data)
        self.assertIn(b"Team Leave Approvals", resp.data)

    def test_clock_in_and_clock_out(self):
        self.login_employee("EMP-1001")

        # HTML clock-in
        resp = self.client.post("/employee/clock_in", follow_redirects=True)
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"Clocked in successfully", resp.data)

        # JSON clock-out
        resp_json = self.client.post(
            "/employee/clock_out",
            headers={"Content-Type": "application/json"}
        )
        self.assertEqual(resp_json.status_code, 200)
        data = resp_json.get_json()
        self.assertTrue(data.get("success"))
        self.assertIsNotNone(data.get("attendance", {}).get("clock_out"))
        self.assertIn("total_hours", data.get("attendance", {}))

    def test_attendance_apis(self):
        # Employee checks own attendance
        self.login_employee("EMP-1001")
        resp = self.client.get("/api/employee/my_attendance")
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertTrue(data.get("success"))
        self.assertIsInstance(data.get("attendance"), list)

        # Unauthenticated attendance access returns 401 for JSON, 302 for HTML
        self.client.get("/employee_logout")
        resp_unauth = self.client.get("/api/employee/my_attendance", headers={"Content-Type": "application/json"})
        self.assertEqual(resp_unauth.status_code, 401)
        resp_unauth_html = self.client.get("/api/employee/my_attendance")
        self.assertEqual(resp_unauth_html.status_code, 302)

        # HR checks employee attendance
        self.login_hr()
        resp_hr = self.client.get("/api/employee/EMP-1001/attendance")
        self.assertEqual(resp_hr.status_code, 200)
        data_hr = resp_hr.get_json()
        self.assertTrue(data_hr.get("success"))


if __name__ == "__main__":
    unittest.main()
