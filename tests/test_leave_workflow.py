import unittest
from tests.base import BaseTestCase
import storage


class TestLeaveWorkflow(BaseTestCase):
    def _get_leave(self, leave_id):
        return next((l for l in storage.get_all_leave_requests() if l["id"] == leave_id), None)

    def test_full_two_tier_leave_lifecycle_approval(self):
        # 1. Employee Alex (EMP-1001) applies for 2 days leave (Thursday - Friday)
        self.login_employee("EMP-1001")
        resp = self.client.post(
            "/employee/apply_leave",
            data={
                "start_date": "2026-11-19",
                "end_date": "2026-11-20",
                "reason": "Family gathering"
            },
            follow_redirects=True,
        )
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"sent to Team Lead Marcus Vance for approval", resp.data)

        leaves = storage.get_all_leave_requests()
        self.assertEqual(len(leaves), 1)
        leave = leaves[0]
        self.assertEqual(leave["status"], "pending_lead")
        self.assertEqual(leave["days"], 2)
        self.assertEqual(leave["leave_type"], "Casual Leave")
        self.assertEqual(leave["assigned_team_lead_id"], "EMP-1004")

        # 2. Team Lead Marcus Vance (EMP-1004) approves and forwards to HR
        self.login_employee("EMP-1004")
        resp = self.client.post(
            f"/team_lead/leave/{leave['id']}/review",
            data={"decision": "approve", "remarks": "Approved, enjoy your time!"},
            follow_redirects=True,
        )
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"forwarded it to HR for final approval", resp.data)

        leave = self._get_leave(leave["id"])
        self.assertEqual(leave["status"], "pending_hr")
        self.assertEqual(leave["lead_reviewer_id"], "EMP-1004")

        # 3. HR Admin reviews and gives final approval
        self.login_hr()
        resp = self.client.post(
            f"/hr/leave/{leave['id']}/review",
            data={"decision": "approved", "remarks": "All good from HR."},
            follow_redirects=True,
        )
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"APPROVED", resp.data)

        leave = self._get_leave(leave["id"])
        self.assertEqual(leave["status"], "approved")

        # Check attendance calendar marked with 'On Leave'
        attendance = storage.get_employee_attendance("EMP-1001")
        leave_dates = [a["date"] for a in attendance if a["status"] == "On Leave"]
        self.assertIn("2026-11-19", leave_dates)
        self.assertIn("2026-11-20", leave_dates)

        # Check quota balance deducted
        stats = storage.get_employee_year_leave_stats("EMP-1001", year=2026)
        self.assertEqual(stats["approved_casual"], 2)
        self.assertEqual(stats["casual_available"], 10)

    def test_team_lead_rejection_workflow(self):
        # Employee applies
        self.login_employee("EMP-1001")
        self.client.post(
            "/employee/apply_leave",
            data={
                "start_date": "2026-11-25",
                "end_date": "2026-11-26",
                "reason": "Short break"
            },
            follow_redirects=True,
        )
        leave = storage.get_all_leave_requests()[0]

        # Team Lead rejects
        self.login_employee("EMP-1004")
        resp = self.client.post(
            f"/team_lead/leave/{leave['id']}/review",
            data={"decision": "reject", "remarks": "High workload sprint."},
            follow_redirects=True,
        )
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"Rejected", resp.data)

        leave = self._get_leave(leave["id"])
        self.assertEqual(leave["status"], "rejected_by_lead")

        # HR never received any pending review
        hr_leaves = storage.get_all_leave_requests()
        self.assertFalse(any(l["status"] == "pending_hr" for l in hr_leaves))

    def test_hr_rejection_workflow(self):
        # Submit and TL approve
        self.login_employee("EMP-1001")
        self.client.post(
            "/employee/apply_leave",
            data={"start_date": "2026-11-20", "end_date": "2026-11-21", "reason": "Trip"},
            follow_redirects=True,
        )
        leave = storage.get_all_leave_requests()[0]
        self.login_employee("EMP-1004")
        self.client.post(
            f"/team_lead/leave/{leave['id']}/review",
            data={"decision": "approve"},
            follow_redirects=True,
        )

        # HR rejects
        self.login_hr()
        resp = self.client.post(
            f"/hr/leave/{leave['id']}/review",
            data={"decision": "rejected", "remarks": "Policy violation."},
            follow_redirects=True,
        )
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"REJECTED by HR", resp.data)

        leave = self._get_leave(leave["id"])
        self.assertEqual(leave["status"], "rejected_by_hr")

    def test_team_lead_own_leave_skips_lead_tier(self):
        # Marcus Vance (EMP-1004, Team Lead) applies for leave
        self.login_employee("EMP-1004")
        resp = self.client.post(
            "/employee/apply_leave",
            data={"start_date": "2026-11-16", "end_date": "2026-11-17", "reason": "Conference"},
            follow_redirects=True,
        )
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"sent to HR Admin for approval", resp.data)

        leave = storage.get_all_leave_requests()[0]
        self.assertEqual(leave["status"], "pending_hr")

    def test_employee_without_team_lead_blocked(self):
        # Sarah Jenkins (EMP-1003) has team_lead_id=None
        self.login_employee("EMP-1003")
        resp = self.client.post(
            "/employee/apply_leave",
            data={"start_date": "2026-11-16", "end_date": "2026-11-17", "reason": "Rest"},
            follow_redirects=True,
        )
        self.assertIn(b"No Team Lead is assigned", resp.data)
        self.assertEqual(len(storage.get_all_leave_requests()), 0)

    def test_cross_team_lead_access_denied(self):
        # EMP-1001 is assigned to EMP-1004 (Marcus Vance)
        self.login_employee("EMP-1001")
        self.client.post(
            "/employee/apply_leave",
            data={"start_date": "2026-11-16", "end_date": "2026-11-17", "reason": "Trip"},
            follow_redirects=True,
        )
        leave = storage.get_all_leave_requests()[0]

        # Priya Sharma (EMP-1002, another team lead) attempts to review leave
        self.login_employee("EMP-1002")
        resp = self.client.post(
            f"/team_lead/leave/{leave['id']}/review",
            data={"decision": "approve"},
            follow_redirects=True,
        )
        self.assertIn(b"employees assigned to your team", resp.data)

    def test_auto_spill_over_casual_12_days_cap(self):
        # Alex applies for 15 days (available: 12 casual + 15 yearly)
        # Should allocate: 12 casual + 3 yearly = Mixed
        self.login_employee("EMP-1001")
        resp = self.client.post(
            "/employee/apply_leave",
            data={"start_date": "2026-11-01", "end_date": "2026-11-15", "reason": "Long holiday"},
            follow_redirects=True,
        )
        self.assertEqual(resp.status_code, 200)

        leave = storage.get_all_leave_requests()[0]
        self.assertEqual(leave["casual_days"], 12)
        self.assertEqual(leave["yearly_days"], 3)
        self.assertIn("Mixed (12 Casual + 3 Yearly)", leave["leave_type"])

    def test_hr_reclassify_leave_type(self):
        # Create an approved casual leave
        self.login_employee("EMP-1001")
        self.client.post(
            "/employee/apply_leave",
            data={"start_date": "2026-11-01", "end_date": "2026-11-03", "reason": "Short break"},
            follow_redirects=True,
        )
        leave = storage.get_all_leave_requests()[0]
        self.login_employee("EMP-1004")
        self.client.post(f"/team_lead/leave/{leave['id']}/review", data={"decision": "approve"}, follow_redirects=True)
        self.login_hr()
        self.client.post(f"/hr/leave/{leave['id']}/review", data={"decision": "approved"}, follow_redirects=True)

        # HR converts to Yearly
        resp = self.client.post(
            f"/hr/leave/{leave['id']}/convert_type",
            data={"target_mode": "yearly", "reason": "Reclassified upon employee request"},
            follow_redirects=True,
        )
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"reclassified to Yearly Leave", resp.data)

        updated_leave = self._get_leave(leave["id"])
        self.assertEqual(updated_leave["casual_days"], 0)
        self.assertEqual(updated_leave["yearly_days"], 3)
        self.assertEqual(updated_leave["leave_type"], "Yearly Leave")


if __name__ == "__main__":
    unittest.main()
