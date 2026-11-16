import unittest
from tests.base import BaseTestCase
import storage
import notification_service


class TestNotificationServiceAndAPIs(BaseTestCase):
    def test_in_app_notification_lifecycle_hr(self):
        # Seed an unread notification for HR
        storage.add_notification(
            recipient_type="hr",
            recipient_id="hr_admin",
            title="New Application Received",
            message="Jane submitted a resume for Backend Engineer.",
            link="/candidate",
            notification_type="application"
        )

        self.login_hr()
        resp = self.client.get("/api/notifications")
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertTrue(data.get("success"))
        self.assertEqual(len(data.get("notifications")), 1)
        self.assertEqual(data.get("unread_count"), 1)
        notif_id = data["notifications"][0]["id"]
        self.assertFalse(data["notifications"][0]["read"])

        # Mark single notification read
        resp_read = self.client.post(f"/api/notifications/{notif_id}/read")
        self.assertEqual(resp_read.status_code, 200)
        self.assertTrue(resp_read.get_json().get("success"))

        resp_after = self.client.get("/api/notifications")
        self.assertEqual(resp_after.get_json().get("unread_count"), 0)
        self.assertTrue(resp_after.get_json()["notifications"][0]["read"])

    def test_in_app_notification_mark_all_read_employee_and_applicant(self):
        # Add notifications for employee EMP-1001
        storage.add_notification(
            recipient_type="employee",
            recipient_id="EMP-1001",
            title="Leave Approved",
            message="Your leave for Nov 20 has been approved.",
            link="/employee_dashboard",
            notification_type="leave"
        )
        storage.add_notification(
            recipient_type="employee",
            recipient_id="EMP-1001",
            title="Company Announcement",
            message="All-hands meeting on Friday.",
            link="/employee_dashboard",
            notification_type="announcement"
        )

        self.login_employee("EMP-1001")
        resp = self.client.get("/api/notifications?scope=employee")
        self.assertEqual(resp.get_json()["unread_count"], 2)

        # Mark all read
        resp_all = self.client.post("/api/notifications/mark_all_read?scope=employee")
        self.assertEqual(resp_all.status_code, 200)
        self.assertTrue(resp_all.get_json()["success"])

        resp_check = self.client.get("/api/notifications?scope=employee")
        self.assertEqual(resp_check.get_json()["unread_count"], 0)

    def test_unauthenticated_notification_api_returns_empty(self):
        resp = self.client.get("/api/notifications")
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertTrue(data.get("success"))
        self.assertEqual(data.get("notifications"), [])
        self.assertEqual(data.get("unread_count"), 0)

    def test_notification_service_send_email_outbox(self):
        # Empty recipient
        res_empty = notification_service.send_email("", "Subject", "Body")
        self.assertFalse(res_empty["success"])
        self.assertEqual(res_empty["reason"], "No recipient email provided")

        # Simulated send
        res_sim = notification_service.send_email(
            "candidate@test.local",
            "Welcome to TalentAI",
            "<p>Your application is received.</p>",
            "Your application is received."
        )
        self.assertTrue(res_sim["success"])
        self.assertEqual(res_sim["mode"], "simulated")

        # Verify entry appended to EMAIL_OUTBOX
        self.assertTrue(any(e["to"] == "candidate@test.local" for e in notification_service.EMAIL_OUTBOX))

    def test_notification_service_email_formatters(self):
        # 1. Interview invitation
        inv_res = notification_service.send_interview_invitation(
            "test@corp.local",
            "Alex Test",
            "Senior Engineer",
            {"date": "2026-12-01", "time": "10:00 AM", "meeting_link": "https://meet.test", "round_title": "Round 1"}
        )
        self.assertTrue(inv_res["success"])
        last_outbox = notification_service.EMAIL_OUTBOX[-1]
        self.assertIn("Interview Invitation", last_outbox["subject"])
        self.assertIn("Alex Test", last_outbox["text_content"])

        # 2. Candidate response alert to HR
        alert_res = notification_service.send_candidate_response_alert_to_hr(
            "hr@corp.local",
            "Alex Test",
            "Senior Engineer",
            "reschedule",
            {"proposed_date": "2026-12-02", "proposed_time": "2:00 PM", "reason": "Conflict"}
        )
        self.assertTrue(alert_res["success"])
        self.assertIn("Reschedule", notification_service.EMAIL_OUTBOX[-1]["subject"])

        # 3. Reschedule resolution to candidate
        res_approved = notification_service.send_reschedule_resolution_to_candidate(
            "test@corp.local",
            "Alex Test",
            "Senior Engineer",
            is_approved=True,
            interview_data={"date": "2026-12-02", "time": "2:00 PM"}
        )
        self.assertTrue(res_approved["success"])
        self.assertIn("Approved", notification_service.EMAIL_OUTBOX[-1]["subject"])

        # 4. Direct message email
        dm_res = notification_service.send_direct_message_email(
            "test@corp.local",
            "Alex Test",
            "HR Team",
            "Senior Engineer",
            "Please check the attachment.",
            attachment_name="specs.pdf"
        )
        self.assertTrue(dm_res["success"])
        self.assertIn("specs.pdf", notification_service.EMAIL_OUTBOX[-1]["text_content"])

        # 5. Stage update email
        stage_res = notification_service.send_stage_update_email(
            "test@corp.local",
            "Alex Test",
            "Senior Engineer",
            "Offer"
        )
        self.assertTrue(stage_res["success"])
        self.assertIn("Offer", notification_service.EMAIL_OUTBOX[-1]["subject"])


if __name__ == "__main__":
    unittest.main()
