"""
Notification Service for TalentAI
Handles email dispatch via SMTP with graceful local fallback/preview logging,
as well as notification formatting.
"""

import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

# SMTP Configuration from Environment Variables
SMTP_HOST = os.getenv("SMTP_HOST", "")
SMTP_PORT = int(os.getenv("SMTP_PORT", 587))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
SMTP_FROM_EMAIL = os.getenv("SMTP_FROM_EMAIL", SMTP_USER or "recruitment@talentai.local")
SMTP_USE_TLS = os.getenv("SMTP_USE_TLS", "true").lower() in ("true", "1", "yes")

# In-memory email outbox log for inspection/preview in UI or debugging
EMAIL_OUTBOX = []

def is_smtp_configured() -> bool:
    """Check if real SMTP credentials are provided."""
    return bool(SMTP_HOST and SMTP_USER and SMTP_PASSWORD)

def send_email(to_email: str, subject: str, html_content: str, text_content: str = "") -> dict:
    """
    Sends an email using configured SMTP settings.
    If SMTP is not configured or fails, logs to console and in-memory outbox gracefully.
    """
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    outbox_entry = {
        "to": to_email,
        "subject": subject,
        "html_content": html_content,
        "text_content": text_content or html_content,
        "timestamp": timestamp,
        "status": "sent"
    }

    if not to_email:
        print(f"[Email Notification Skipped] No recipient email provided for subject: {subject}")
        outbox_entry["status"] = "skipped_no_email"
        EMAIL_OUTBOX.append(outbox_entry)
        return {"success": False, "reason": "No recipient email provided"}

    if not is_smtp_configured():
        # Fallback mode: Print preview and record to outbox
        print("=" * 65)
        print(f"📧 [EMAIL NOTIFICATION PREVIEW] - {timestamp}")
        print(f"To:      {to_email}")
        print(f"From:    {SMTP_FROM_EMAIL}")
        print(f"Subject: {subject}")
        print("-" * 65)
        print(text_content or "(HTML Content provided)")
        print("=" * 65)
        outbox_entry["status"] = "simulated"
        EMAIL_OUTBOX.append(outbox_entry)
        return {"success": True, "mode": "simulated", "message": "Email logged to simulation outbox"}

    # Attempt real SMTP transmission
    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = SMTP_FROM_EMAIL
        msg["To"] = to_email

        if text_content:
            msg.attach(MIMEText(text_content, "plain"))
        if html_content:
            msg.attach(MIMEText(html_content, "html"))

        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=10) as server:
            if SMTP_USE_TLS:
                server.starttls()
            server.login(SMTP_USER, SMTP_PASSWORD)
            server.sendmail(SMTP_FROM_EMAIL, [to_email], msg.as_string())

        print(f"✅ [EMAIL SENT] Successfully delivered to {to_email}")
        outbox_entry["status"] = "delivered"
        EMAIL_OUTBOX.append(outbox_entry)
        return {"success": True, "mode": "smtp", "message": "Email delivered"}

    except Exception as e:
        print(f"⚠️ [EMAIL SMTP FAILED] {e}. Falling back to simulation record.")
        outbox_entry["status"] = "failed_recorded"
        outbox_entry["error"] = str(e)
        EMAIL_OUTBOX.append(outbox_entry)
        return {"success": False, "mode": "error", "error": str(e)}


def send_interview_invitation(candidate_email: str, candidate_name: str, position_title: str, interview_data: dict) -> dict:
    """Send interview invitation to candidate."""
    date = interview_data.get("date", "To be announced")
    time = interview_data.get("time", "To be announced")
    round_title = interview_data.get("round_title", "Interview Round")
    meeting_link = interview_data.get("meeting_link", "")
    hr_note = interview_data.get("hr_note", "")

    subject = f"🎉 Interview Invitation: {position_title} at TalentAI"

    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
      <meta charset="utf-8">
      <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background-color: #0f172a; color: #f8fafc; padding: 20px; }}
        .card {{ max-width: 600px; margin: 0 auto; background: #1e293b; border-radius: 12px; border: 1px solid #334155; padding: 30px; }}
        .header {{ text-align: center; border-bottom: 1px solid #334155; padding-bottom: 20px; }}
        .badge {{ background: #6366f1; color: white; padding: 4px 12px; border-radius: 999px; font-size: 13px; font-weight: 600; display: inline-block; }}
        h1 {{ color: #ffffff; font-size: 22px; margin: 15px 0 5px 0; }}
        .details {{ background: #0f172a; border-radius: 8px; padding: 20px; margin: 25px 0; }}
        .detail-row {{ margin-bottom: 12px; font-size: 15px; }}
        .detail-label {{ color: #94a3b8; font-weight: 500; display: inline-block; width: 130px; }}
        .detail-value {{ color: #f8fafc; font-weight: 600; }}
        .btn {{ display: inline-block; padding: 12px 24px; border-radius: 8px; font-weight: 600; text-decoration: none; margin: 8px 6px; }}
        .btn-confirm {{ background: #10b981; color: white; }}
        .btn-reschedule {{ background: #f59e0b; color: white; }}
        .footer {{ text-align: center; color: #64748b; font-size: 12px; margin-top: 25px; }}
      </style>
    </head>
    <body>
      <div class="card">
        <div class="header">
          <span class="badge">Interview Scheduled</span>
          <h1>Great News, {candidate_name}!</h1>
          <p style="color: #94a3b8; margin: 5px 0;">Your application for <strong>{position_title}</strong> has progressed to the interview stage.</p>
        </div>
        <div class="details">
          <div class="detail-row"><span class="detail-label">📅 Date:</span> <span class="detail-value">{date}</span></div>
          <div class="detail-row"><span class="detail-label">⏰ Time:</span> <span class="detail-value">{time}</span></div>
          <div class="detail-row"><span class="detail-label">📋 Round:</span> <span class="detail-value">{round_title}</span></div>
          {f'<div class="detail-row"><span class="detail-label">🔗 Meeting Link:</span> <span class="detail-value"><a href="{meeting_link}" style="color: #6366f1;">{meeting_link}</a></span></div>' if meeting_link else ''}
          {f'<div class="detail-row"><span class="detail-label">📝 Notes:</span> <span class="detail-value">{hr_note}</span></div>' if hr_note else ''}
        </div>
        <p style="color: #cbd5e1; font-size: 14px; line-height: 1.5;">
          Please log in to your TalentAI Applicant Portal to <strong>Confirm</strong> your attendance or <strong>Propose a Different Time/Date</strong> if you are not available.
        </p>
        <div class="footer">
          TalentAI Automated Recruitment System • Please do not reply directly to this automated email.
        </div>
      </div>
    </body>
    </html>
    """

    text = f"""
    Interview Invitation - TalentAI
    ======================================
    Hello {candidate_name},

    Your application for '{position_title}' has progressed to the interview stage!

    Interview Details:
    - Date: {date}
    - Time: {time}
    - Round: {round_title}
    {f"- Meeting Link: {meeting_link}" if meeting_link else ""}
    {f"- Notes: {hr_note}" if hr_note else ""}

    Please log in to your TalentAI Candidate Dashboard or Status Tracker to confirm attendance or request a different date/time.

    Best regards,
    TalentAI Recruitment Team
    """

    return send_email(candidate_email, subject, html, text)


def send_candidate_response_alert_to_hr(hr_email: str, candidate_name: str, position_title: str, action: str, details: dict = None) -> dict:
    """Send alert to HR when candidate responds (Accepts, Declines, or Reschedules)."""
    details = details or {}
    action_upper = action.replace("_", " ").title()
    subject = f"Candidate Update: {candidate_name} has {action_upper} the interview"

    if action == "reschedule_requested":
        action_text = f"requested to reschedule their interview to <strong>{details.get('proposed_date')} at {details.get('proposed_time')}</strong>."
        reason_text = f"<p><strong>Reason:</strong> {details.get('reason', 'None provided')}</p>"
    elif action == "confirmed":
        action_text = "confirmed their attendance for the scheduled interview."
        reason_text = ""
    else:
        action_text = "declined the interview invitation."
        reason_text = f"<p><strong>Note:</strong> {details.get('reason', 'None provided')}</p>" if details.get('reason') else ""

    html = f"""
    <!DOCTYPE html>
    <html>
    <body style="font-family: sans-serif; background: #0f172a; color: #f8fafc; padding: 20px;">
      <div style="max-width: 600px; margin: 0 auto; background: #1e293b; padding: 25px; border-radius: 12px; border: 1px solid #334155;">
        <h2 style="color: #6366f1; margin-top: 0;">Candidate Response Notification</h2>
        <p>Candidate <strong>{candidate_name}</strong> for position <strong>{position_title}</strong> has {action_text}</p>
        {reason_text}
        <p style="margin-top: 20px; font-size: 14px; color: #94a3b8;">
          Log in to the HR Employer Portal to review candidates and take action.
        </p>
      </div>
    </body>
    </html>
    """

    text = f"""
    Candidate Response Notification
    Candidate: {candidate_name}
    Position: {position_title}
    Action: {action_upper}
    Details: {details}
    """

    target_email = hr_email or SMTP_FROM_EMAIL
    return send_email(target_email, subject, html, text)


def send_reschedule_resolution_to_candidate(candidate_email: str, candidate_name: str, position_title: str, is_approved: bool, interview_data: dict) -> dict:
    """Send email to candidate when HR approves or updates their reschedule request."""
    date = interview_data.get("date", "")
    time = interview_data.get("time", "")
    notes = interview_data.get("hr_note", "")

    if is_approved:
        subject = f"✅ Reschedule Approved: Interview for {position_title}"
        status_msg = f"Your request to reschedule has been <strong>approved</strong>! Your new interview is confirmed for <strong>{date} at {time}</strong>."
    else:
        subject = f"🔄 Interview Time Updated: {position_title}"
        status_msg = f"The recruitment team has proposed a new interview slot: <strong>{date} at {time}</strong>."

    html = f"""
    <!DOCTYPE html>
    <html>
    <body style="font-family: sans-serif; background: #0f172a; color: #f8fafc; padding: 20px;">
      <div style="max-width: 600px; margin: 0 auto; background: #1e293b; padding: 25px; border-radius: 12px; border: 1px solid #334155;">
        <h2 style="color: {'#10b981' if is_approved else '#6366f1'}; margin-top: 0;">{subject}</h2>
        <p>Hello {candidate_name},</p>
        <p>{status_msg}</p>
        {f'<p style="color: #94a3b8;">Note from HR: {notes}</p>' if notes else ''}
        <p style="margin-top: 25px; font-size: 14px; color: #94a3b8;">
          View details and meeting information in your Applicant Portal.
        </p>
      </div>
    </body>
    </html>
    """

    text = f"""
    Interview Schedule Update
    Candidate: {candidate_name}
    Position: {position_title}
    Status: {'Approved' if is_approved else 'Updated by HR'}
    New Date & Time: {date} at {time}
    Notes: {notes}
    """

    return send_email(candidate_email, subject, html, text)


def send_direct_message_email(to_email: str, recipient_name: str, sender_name: str, position_title: str, message_text: str, attachment_name: str = "") -> dict:
    """Send an email notification when a new chat message/update is posted."""
    subject = f"💬 New Message from {sender_name} regarding {position_title}"
    attachment_html = f'<div style="margin-top: 12px; padding: 8px 12px; background: rgba(99, 102, 241, 0.2); border-radius: 6px; font-size: 13px; color: #c4b5fd;">📎 <strong>Attachment:</strong> {attachment_name}</div>' if attachment_name else ''
    attachment_text = f"\n[Attachment: {attachment_name}]" if attachment_name else ""

    html = f"""
    <!DOCTYPE html>
    <html>
    <body style="font-family: sans-serif; background: #0f172a; color: #f8fafc; padding: 20px;">
      <div style="max-width: 600px; margin: 0 auto; background: #1e293b; padding: 25px; border-radius: 12px; border: 1px solid #334155;">
        <h3 style="color: #6366f1; margin-top: 0;">New Message from {sender_name}</h3>
        <p style="color: #94a3b8; font-size: 14px;">Regarding Position: <strong>{position_title}</strong></p>
        <div style="background: #0f172a; border-left: 4px solid #6366f1; padding: 15px; border-radius: 4px; margin: 20px 0; font-size: 15px; line-height: 1.5;">
          {message_text}
          {attachment_html}
        </div>
        <p style="font-size: 13px; color: #94a3b8;">
          You can reply and track all updates directly inside your TalentAI portal.
        </p>
      </div>
    </body>
    </html>
    """
    text = f"""
    New Message from {sender_name} ({position_title})
    --------------------------------------------------
    {message_text}
    {attachment_text}

    Log in to TalentAI to view the full conversation and reply.
    """
    return send_email(to_email, subject, html, text)


def send_stage_update_email(candidate_email: str, candidate_name: str, position_title: str, new_stage: str) -> dict:
    """Send an email notification when candidate's stage advances."""
    subject = f"🚀 Application Update: {new_stage} - {position_title}"
    html = f"""
    <!DOCTYPE html>
    <html>
    <body style="font-family: sans-serif; background: #0f172a; color: #f8fafc; padding: 20px;">
      <div style="max-width: 600px; margin: 0 auto; background: #1e293b; padding: 25px; border-radius: 12px; border: 1px solid #334155;">
        <span style="background: #10b981; color: white; padding: 4px 12px; border-radius: 999px; font-size: 12px; font-weight: 600;">Stage Advanced</span>
        <h2 style="color: #ffffff; margin-top: 15px;">Application Progress Update</h2>
        <p>Hello {candidate_name},</p>
        <p>Great news! Your application for <strong>{position_title}</strong> has progressed to the next stage:</p>
        <div style="background: #0f172a; border-left: 4px solid #10b981; padding: 15px; border-radius: 6px; margin: 20px 0; font-size: 18px; font-weight: 700; color: #34d399;">
          🎯 {new_stage}
        </div>
        <p style="font-size: 14px; color: #94a3b8;">
          Our recruitment team will follow up shortly with subsequent steps or schedule details.
        </p>
      </div>
    </body>
    </html>
    """
    text = f"""
    Application Stage Update: {position_title}
    --------------------------------------------------
    Hello {candidate_name},
    Your application for {position_title} has advanced to: {new_stage}.
    Log in to TalentAI to view your application status.
    """
    return send_email(candidate_email, subject, html, text)


def _send_leave_workflow_email(to_email: str, subject: str, heading: str, accent: str, body_html: str, body_text: str) -> dict:
    """Shared HTML/text builder for RBAC leave workflow email notifications."""
    html = f"""
    <!DOCTYPE html>
    <html>
    <body style="font-family: sans-serif; background: #0f172a; color: #f8fafc; padding: 20px;">
      <div style="max-width: 600px; margin: 0 auto; background: #1e293b; padding: 25px; border-radius: 12px; border: 1px solid #334155;">
        <h2 style="color: {accent}; margin-top: 0;">{heading}</h2>
        {body_html}
        <p style="margin-top: 20px; font-size: 13px; color: #94a3b8;">
          TalentAI Leave Management System • Open your portal to review details.
        </p>
      </div>
    </body>
    </html>
    """
    return send_email(to_email, subject, html, body_text)


def send_leave_submitted_to_lead_email(lead_email: str, lead_name: str, emp_name: str, leave_record: dict) -> dict:
    """Notifies the assigned Team Lead when an employee submits a leave request."""
    days = leave_record.get("days", 1)
    l_type = leave_record.get("leave_type", "Casual Leave")
    start_d = leave_record.get("start_date", "")
    end_d = leave_record.get("end_date", "")
    reason = leave_record.get("reason", "") or "No reason provided"
    subject = f"📋 Leave Approval Needed: {emp_name} ({days} day(s))"
    body_html = (
        f"<p>Hello <strong>{lead_name}</strong>,</p>"
        f"<p><strong>{emp_name}</strong> has submitted a leave request requiring your Team Lead approval before it can be forwarded to HR:</p>"
        f"<div style='background:#0f172a;padding:14px;border-radius:8px;border-left:4px solid #6366f1;'>"
        f"<div><strong>Dates:</strong> {start_d} to {end_d} ({days} day(s))</div>"
        f"<div><strong>Allocation:</strong> {l_type}</div>"
        f"<div><strong>Reason:</strong> {reason}</div></div>"
    )
    body_text = (
        f"Leave Approval Needed - {emp_name}\n"
        f"Dates: {start_d} to {end_d} ({days} day(s))\nAllocation: {l_type}\nReason: {reason}"
    )
    return _send_leave_workflow_email(lead_email, subject, "Team Lead Leave Review Needed", "#818cf8", body_html, body_text)


def send_leave_forwarded_to_hr_email(hr_email: str, lead_name: str, emp_name: str, leave_record: dict) -> dict:
    """Notifies HR when a Team Lead approves & forwards a leave request (or submits their own)."""
    days = leave_record.get("days", 1)
    l_type = leave_record.get("leave_type", "Casual Leave")
    start_d = leave_record.get("start_date", "")
    end_d = leave_record.get("end_date", "")
    subject = f"📬 Leave Forwarded to HR: {emp_name} ({days} day(s))"
    body_html = (
        f"<p><strong>{emp_name}</strong>'s leave request has been approved by Team Lead <strong>{lead_name}</strong> "
        f"and is now ready for final HR approval:</p>"
        f"<div style='background:#0f172a;padding:14px;border-radius:8px;border-left:4px solid #10b981;'>"
        f"<div><strong>Dates:</strong> {start_d} to {end_d} ({days} day(s))</div>"
        f"<div><strong>Allocation:</strong> {l_type}</div></div>"
    )
    body_text = (
        f"Leave Forwarded to HR: {emp_name}\nApproved by Team Lead: {lead_name}\n"
        f"Dates: {start_d} to {end_d} ({days} day(s))\nAllocation: {l_type}"
    )
    target = hr_email or SMTP_FROM_EMAIL
    return _send_leave_workflow_email(target, subject, "Leave Ready for HR Approval", "#34d399", body_html, body_text)


def send_leave_status_update_email(emp_email: str, emp_name: str, leave_record: dict, actor_name: str, action_label: str, remarks: str = "") -> dict:
    """Notifies an employee when their leave is rejected, HR-approved, or reclassified by HR."""
    start_d = leave_record.get("start_date", "")
    end_d = leave_record.get("end_date", "")
    l_type = leave_record.get("leave_type", "")
    is_error = "reject" in action_label.lower()
    accent = "#fb7185" if is_error else "#34d399"
    subject = f"Leave Update ({action_label}): {start_d} to {end_d}"
    body_html = (
        f"<p>Hello <strong>{emp_name}</strong>,</p>"
        f"<p>Your leave request (<strong>{start_d} to {end_d}</strong>, {l_type}) status update: <strong>{action_label}</strong> by {actor_name}.</p>"
        f"{f'<p><strong>Remarks:</strong> {remarks}</p>' if remarks else ''}"
    )
    body_text = f"Leave Update: {action_label} by {actor_name}\nDates: {start_d} to {end_d}\nType: {l_type}\nRemarks: {remarks or 'None'}"
    return _send_leave_workflow_email(emp_email, subject, f"Leave {action_label}", accent, body_html, body_text)

