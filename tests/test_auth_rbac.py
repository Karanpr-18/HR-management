import unittest
from tests.base import BaseTestCase
import storage


class TestAuthAndRBAC(BaseTestCase):
    def test_hr_login_success_and_logout(self):
        # GET hr_login
        resp = self.client.get("/hr_login")
        self.assertEqual(resp.status_code, 200)

        # POST hr_login with valid credentials
        resp = self.login_hr()
        self.assertEqual(resp.status_code, 200)
        with self.client.session_transaction() as sess:
            self.assertTrue(sess.get("is_hr"))

        # Logout clears session
        resp = self.client.get("/logout", follow_redirects=True)
        self.assertEqual(resp.status_code, 200)
        with self.client.session_transaction() as sess:
            self.assertFalse(sess.get("is_hr"))

    def test_hr_login_failure(self):
        resp = self.client.post(
            "/hr_login",
            data={"username": "hr_admin", "password": "wrongpassword"},
            follow_redirects=True,
        )
        self.assertIn(b"Invalid credentials.", resp.data)
        with self.client.session_transaction() as sess:
            self.assertFalse(sess.get("is_hr"))

    def test_hr_protected_routes_require_auth(self):
        # HTML redirects to hr_login
        for path in ["/overview", "/employer", "/employees", "/candidate"]:
            resp = self.client.get(path, follow_redirects=False)
            self.assertEqual(resp.status_code, 302)
            self.assertIn("/hr_login", resp.headers["Location"])

        # JSON request returns 403
        resp = self.client.get("/overview", headers={"Accept": "application/json", "X-Requested-With": "XMLHttpRequest"})
        # app.py hr_required checks request.is_json
        resp_json = self.client.post(
            "/position/add",
            json={"title": "Test"},
            headers={"Content-Type": "application/json"}
        )
        self.assertEqual(resp_json.status_code, 403)
        data = resp_json.get_json()
        self.assertFalse(data.get("success"))
        self.assertIn("HR authentication required", data.get("error"))

    def test_applicant_register_and_login(self):
        # Missing fields validation
        resp = self.client.post(
            "/applicant_register",
            data={"username": "newuser", "password": "", "name": ""},
            follow_redirects=True
        )
        self.assertIn(b"Please fill in all required fields.", resp.data)

        # Successful registration
        resp = self.client.post(
            "/applicant_register",
            data={
                "username": "newuser",
                "password": "mypassword",
                "name": "New User",
                "email": "newuser@example.com"
            },
            follow_redirects=True
        )
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"Account created successfully!", resp.data)
        with self.client.session_transaction() as sess:
            self.assertIsNotNone(sess.get("user_id"))
            self.assertEqual(sess.get("user_name"), "New User")

        # Duplicate registration fails
        resp = self.client.post(
            "/applicant_register",
            data={
                "username": "newuser",
                "password": "mypassword2",
                "name": "New User 2",
                "email": "newuser2@example.com"
            },
            follow_redirects=True
        )
        self.assertIn(b"Username already exists.", resp.data)

        # Logout then login
        self.client.get("/logout")
        resp = self.client.post(
            "/applicant_login",
            data={"username": "newuser", "password": "wrongpassword"},
            follow_redirects=True
        )
        self.assertIn(b"Invalid username or password.", resp.data)

        resp = self.client.post(
            "/applicant_login",
            data={"username": "newuser", "password": "mypassword"},
            follow_redirects=True
        )
        self.assertIn(b"Welcome back, New User!", resp.data)

    def test_applicant_protected_route_guard(self):
        # Logged out access redirects to applicant_login
        resp = self.client.get("/applicant_dashboard", follow_redirects=False)
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/applicant_login", resp.headers["Location"])

        # Logged in access succeeds
        self.login_applicant()
        resp = self.client.get("/applicant_dashboard")
        self.assertEqual(resp.status_code, 200)

    def test_employee_login_via_id_and_email(self):
        # Login with Employee ID
        resp = self.login_employee("EMP-1001", "emp123")
        self.assertEqual(resp.status_code, 200)
        with self.client.session_transaction() as sess:
            self.assertEqual(sess.get("employee_id"), "EMP-1001")
            self.assertEqual(sess.get("access_role"), "employee")

        # Logout
        resp = self.client.get("/employee_logout", follow_redirects=True)
        self.assertEqual(resp.status_code, 200)
        with self.client.session_transaction() as sess:
            self.assertIsNone(sess.get("employee_id"))

        # Login with Employee Email
        resp = self.login_employee("alex@corp.test", "emp123")
        self.assertEqual(resp.status_code, 200)
        with self.client.session_transaction() as sess:
            self.assertEqual(sess.get("employee_id"), "EMP-1001")

        # Login with invalid password
        resp = self.login_employee("EMP-1001", "wrongpass")
        self.assertIn(b"Invalid Employee ID / Email or password", resp.data)

        # Login with nonexistent identifier
        resp = self.login_employee("NONEXISTENT", "emp123")
        self.assertIn(b"Invalid Employee ID / Email or password", resp.data)

    def test_employee_protected_route_guard(self):
        # Unauthenticated HTML redirect
        resp = self.client.get("/employee_dashboard", follow_redirects=False)
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/employee_login", resp.headers["Location"])

        # Unauthenticated JSON returns 401
        resp_json = self.client.post(
            "/employee/clock_in",
            json={},
            headers={"Content-Type": "application/json"}
        )
        self.assertEqual(resp_json.status_code, 401)
        data = resp_json.get_json()
        self.assertFalse(data.get("success"))
        self.assertIn("Employee authentication required", data.get("error"))

    def test_team_lead_role_guard(self):
        # Standard employee EMP-1001 attempting to review leave as team lead
        self.login_employee("EMP-1001")

        # JSON request returns 403
        resp_json = self.client.post(
            "/team_lead/leave/fake-id/review",
            json={"decision": "approve"},
            headers={"Content-Type": "application/json"}
        )
        self.assertEqual(resp_json.status_code, 403)
        self.assertIn("Team Lead role required", resp_json.get_json().get("error"))

        # HTML request redirects with error flash
        resp = self.client.post(
            "/team_lead/leave/fake-id/review",
            data={"decision": "approve"},
            follow_redirects=True
        )
        self.assertIn(b"Access denied: Team Lead permissions required", resp.data)


if __name__ == "__main__":
    unittest.main()
