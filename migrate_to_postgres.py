"""
TalentAI HR Platform - PostgreSQL Migration Script
Migrates existing data from data.json into PostgreSQL database tables,
preserving all candidate CVs (raw text, scores, skills, parsed fields),
chat threads & timeline events, employees, leave balances, positions, users,
attendance, and notifications.
"""

import os
import sys
import json
import logging
import argparse
from datetime import datetime
from typing import Dict, Any, Optional

import database

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [%(levelname)s] [migration] %(message)s"
)
logger = logging.getLogger("talentai.migration")


def load_json_data(file_path: str) -> Dict[str, Any]:
    """Loads and validates JSON data from the specified file."""
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"Source JSON file not found at {file_path}")

    with open(file_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    if not isinstance(data, dict):
        raise ValueError(f"Invalid JSON data in {file_path}: expected dictionary root")

    return data


def migrate_positions(positions: list, cur) -> int:
    """Migrates positions records into PostgreSQL."""
    count = 0
    query = """
        INSERT INTO positions (id, title, description, created_at, updated_at)
        VALUES (%s, %s, %s, %s, %s)
        ON CONFLICT (id) DO UPDATE SET
            title = EXCLUDED.title,
            description = EXCLUDED.description,
            updated_at = EXCLUDED.updated_at;
    """
    now = datetime.now().isoformat()
    for pos in positions:
        pos_id = pos.get("id")
        if not pos_id:
            continue
        created_at = pos.get("created_at") or now
        updated_at = pos.get("updated_at") or now
        cur.execute(query, (
            pos_id,
            pos.get("title", "Untitled Position"),
            pos.get("description", ""),
            created_at,
            updated_at
        ))
        count += 1
    return count


def migrate_users(users: list, cur) -> int:
    """Migrates user accounts into PostgreSQL."""
    count = 0
    query = """
        INSERT INTO users (id, username, password, name, email, created_at, updated_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (id) DO UPDATE SET
            username = EXCLUDED.username,
            password = EXCLUDED.password,
            name = EXCLUDED.name,
            email = EXCLUDED.email,
            updated_at = EXCLUDED.updated_at;
    """
    now = datetime.now().isoformat()
    for u in users:
        u_id = u.get("id")
        if not u_id:
            continue
        created_at = u.get("created_at") or now
        updated_at = u.get("updated_at") or now
        cur.execute(query, (
            u_id,
            u.get("username", ""),
            u.get("password", ""),
            u.get("name", ""),
            u.get("email", ""),
            created_at,
            updated_at
        ))
        count += 1
    return count


def migrate_candidates_and_timeline(candidates: list, cur) -> tuple[int, int]:
    """
    Migrates candidate CVs, raw resume texts, scores, skills, and
    conversational timeline / chat threads into candidates and candidate_timeline tables.
    """
    cand_count = 0
    timeline_count = 0

    cand_query = """
        INSERT INTO candidates (
            id, position_id, user_id, employee_id, name, email, phone, university,
            status, stage, job_role, position, raw_resume_text, source_file, analysis_method,
            python_score, experience_score, uni_tier_score, final_rank_score, python_experience_years,
            scores, skills, parsed_data, attachments, interview, interview_rounds,
            created_at, updated_at
        ) VALUES (
            %s, %s, %s, %s, %s, %s, %s, %s,
            %s, %s, %s, %s, %s, %s, %s,
            %s, %s, %s, %s, %s,
            %s, %s, %s, %s, %s, %s,
            %s, %s
        )
        ON CONFLICT (id) DO UPDATE SET
            position_id = EXCLUDED.position_id,
            user_id = EXCLUDED.user_id,
            employee_id = EXCLUDED.employee_id,
            name = EXCLUDED.name,
            email = EXCLUDED.email,
            phone = EXCLUDED.phone,
            university = EXCLUDED.university,
            status = EXCLUDED.status,
            stage = EXCLUDED.stage,
            job_role = EXCLUDED.job_role,
            position = EXCLUDED.position,
            raw_resume_text = COALESCE(EXCLUDED.raw_resume_text, candidates.raw_resume_text),
            source_file = COALESCE(EXCLUDED.source_file, candidates.source_file),
            analysis_method = EXCLUDED.analysis_method,
            python_score = EXCLUDED.python_score,
            experience_score = EXCLUDED.experience_score,
            uni_tier_score = EXCLUDED.uni_tier_score,
            final_rank_score = EXCLUDED.final_rank_score,
            python_experience_years = EXCLUDED.python_experience_years,
            scores = EXCLUDED.scores,
            skills = EXCLUDED.skills,
            parsed_data = EXCLUDED.parsed_data,
            attachments = EXCLUDED.attachments,
            interview = EXCLUDED.interview,
            interview_rounds = EXCLUDED.interview_rounds,
            updated_at = EXCLUDED.updated_at;
    """

    timeline_query = """
        INSERT INTO candidate_timeline (
            id, candidate_id, sender, sender_name, type, content, metadata, attachments, timestamp, created_at
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (id) DO UPDATE SET
            sender = EXCLUDED.sender,
            sender_name = EXCLUDED.sender_name,
            type = EXCLUDED.type,
            content = EXCLUDED.content,
            metadata = EXCLUDED.metadata,
            attachments = EXCLUDED.attachments,
            timestamp = EXCLUDED.timestamp;
    """

    now = datetime.now().isoformat()

    for c in candidates:
        cand_id = c.get("id")
        if not cand_id:
            continue

        raw_resume = c.get("raw_resume_text") or c.get("resume_text") or ""
        skills = c.get("skills") or []
        if isinstance(skills, str):
            skills = [s.strip() for s in skills.split(",") if s.strip()]

        scores = c.get("scores")
        if not scores or not isinstance(scores, dict):
            scores = {
                "python_score": c.get("python_score", 0.0),
                "python_evidence": c.get("python_evidence") or c.get("evidence_quote") or "",
                "experience_score": c.get("experience_score", 0.0),
                "experience_evidence": c.get("experience_evidence") or "",
                "uni_tier_score": c.get("uni_tier_score", 0.0),
                "uni_evidence": c.get("uni_evidence") or "",
                "python_experience_years": c.get("python_experience_years", 0.0),
                "final_rank_score": c.get("final_rank_score", 0.0),
            }

        # Any extra fields to preserve in parsed_data
        known_keys = {
            "id", "position_id", "user_id", "employee_id", "name", "email", "phone", "university",
            "status", "stage", "job_role", "position", "raw_resume_text", "resume_text", "source_file",
            "analysis_method", "python_score", "experience_score", "uni_tier_score", "final_rank_score",
            "python_experience_years", "scores", "skills", "parsed_data", "attachments", "interview",
            "interview_rounds", "created_at", "updated_at", "timeline"
        }
        extra_data = {k: v for k, v in c.items() if k not in known_keys}
        parsed_data = c.get("parsed_data") or {}
        if extra_data:
            parsed_data.update(extra_data)

        attachments = c.get("attachments") or []
        interview = c.get("interview") or {}
        interview_rounds = c.get("interview_rounds") or []

        created_at = c.get("created_at") or now
        updated_at = c.get("updated_at") or now

        cur.execute(cand_query, (
            cand_id,
            c.get("position_id"),
            c.get("user_id"),
            c.get("employee_id"),
            c.get("name", "Unnamed Candidate"),
            c.get("email"),
            c.get("phone"),
            c.get("university"),
            c.get("status", "pending"),
            c.get("stage", "Screening"),
            c.get("job_role"),
            c.get("position"),
            raw_resume,
            c.get("source_file"),
            c.get("analysis_method", "AI Analysis"),
            float(c.get("python_score") or 0.0),
            float(c.get("experience_score") or 0.0),
            float(c.get("uni_tier_score") or 0.0),
            float(c.get("final_rank_score") or 0.0),
            float(c.get("python_experience_years") or 0.0),
            database.to_json(scores),
            database.to_json(skills),
            database.to_json(parsed_data),
            database.to_json(attachments),
            database.to_json(interview),
            database.to_json(interview_rounds),
            created_at,
            updated_at
        ))
        cand_count += 1

        # Migrate timeline events / messages
        for event in c.get("timeline", []):
            event_id = event.get("id")
            if not event_id:
                import uuid
                event_id = str(uuid.uuid4())

            ts = event.get("timestamp") or created_at
            event_meta = event.get("metadata") or {}
            event_att = event.get("attachments") or event_meta.get("attachments") or []

            cur.execute(timeline_query, (
                event_id,
                cand_id,
                event.get("sender", "system"),
                event.get("sender_name", "System"),
                event.get("type", "system"),
                event.get("content", ""),
                database.to_json(event_meta),
                database.to_json(event_att),
                ts,
                ts
            ))
            timeline_count += 1

    return cand_count, timeline_count


def migrate_employees(employees: list, cur) -> int:
    """
    Migrates employee directory, access roles, compensation, and leave quotas.
    Handles team_lead_id in two passes to prevent self-referencing foreign key violations.
    """
    count = 0
    query = """
        INSERT INTO employees (
            id, candidate_id, user_id, name, email, phone, role, department,
            date_of_joining, status, password, access_role, team_lead_id,
            salary, leave_quota, leave_balance, created_at, updated_at
        ) VALUES (
            %s, %s, %s, %s, %s, %s, %s, %s,
            %s, %s, %s, %s, %s,
            %s, %s, %s, %s, %s
        )
        ON CONFLICT (id) DO UPDATE SET
            candidate_id = EXCLUDED.candidate_id,
            user_id = EXCLUDED.user_id,
            name = EXCLUDED.name,
            email = EXCLUDED.email,
            phone = EXCLUDED.phone,
            role = EXCLUDED.role,
            department = EXCLUDED.department,
            date_of_joining = EXCLUDED.date_of_joining,
            status = EXCLUDED.status,
            password = EXCLUDED.password,
            access_role = EXCLUDED.access_role,
            team_lead_id = EXCLUDED.team_lead_id,
            salary = EXCLUDED.salary,
            leave_quota = EXCLUDED.leave_quota,
            leave_balance = EXCLUDED.leave_balance,
            updated_at = EXCLUDED.updated_at;
    """
    now = datetime.now().isoformat()
    # Pass 1: Insert all employees with NULL team_lead_id to satisfy FK
    for emp in employees:
        emp_id = emp.get("id")
        if not emp_id:
            continue
        created_at = emp.get("created_at") or now
        updated_at = emp.get("updated_at") or now

        salary = emp.get("salary") or {
            "base": 0, "allowances": 0, "deductions": 0, "net": 0,
            "currency": "$", "payment_cycle": "Monthly", "status": "Paid"
        }
        leave_quota = emp.get("leave_quota") or {"casual": 12, "yearly": 15}
        leave_balance = emp.get("leave_balance") or {
            "casual": leave_quota.get("casual", 12),
            "yearly": leave_quota.get("yearly", 15),
            "casual_used": 0, "yearly_used": 0,
            "casual_pending": 0, "yearly_pending": 0
        }

        cur.execute(query, (
            emp_id,
            emp.get("candidate_id"),
            emp.get("user_id"),
            emp.get("name", "Unnamed Employee"),
            emp.get("email", f"{emp_id.lower()}@corp.local"),
            emp.get("phone", ""),
            emp.get("role", "Staff"),
            emp.get("department", "Engineering"),
            emp.get("date_of_joining"),
            emp.get("status", "Active"),
            emp.get("password", "emp123"),
            emp.get("access_role", "employee"),
            None,  # Set team_lead_id in pass 2
            database.to_json(salary),
            database.to_json(leave_quota),
            database.to_json(leave_balance),
            created_at,
            updated_at
        ))
        count += 1

    # Pass 2: Update team_lead_id now that all employee records exist
    lead_update_query = "UPDATE employees SET team_lead_id = %s WHERE id = %s;"
    for emp in employees:
        emp_id = emp.get("id")
        lead_id = emp.get("team_lead_id")
        if emp_id and lead_id:
            cur.execute(lead_update_query, (lead_id, emp_id))

    return count


def migrate_attendance(attendance: list, cur) -> int:
    """Migrates attendance logs into PostgreSQL."""
    count = 0
    query = """
        INSERT INTO attendance (
            id, employee_id, employee_name, date, clock_in, clock_out,
            total_hours, status, notes, created_at
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (employee_id, date) DO UPDATE SET
            clock_in = EXCLUDED.clock_in,
            clock_out = EXCLUDED.clock_out,
            total_hours = EXCLUDED.total_hours,
            status = EXCLUDED.status,
            notes = EXCLUDED.notes;
    """
    now = datetime.now().isoformat()
    for att in attendance:
        att_id = att.get("id")
        emp_id = att.get("employee_id")
        att_date = att.get("date")
        if not att_id or not emp_id or not att_date:
            continue

        created_at = att.get("created_at") or now
        cur.execute(query, (
            att_id,
            emp_id,
            att.get("employee_name", ""),
            att_date,
            att.get("clock_in"),
            att.get("clock_out"),
            float(att.get("total_hours") or 0.0),
            att.get("status", "Present"),
            att.get("notes"),
            created_at
        ))
        count += 1
    return count


def migrate_leave_requests(leave_requests: list, cur) -> int:
    """Migrates leave requests and approval histories."""
    count = 0
    query = """
        INSERT INTO leave_requests (
            id, employee_id, employee_name, employee_role, department, leave_type,
            start_date, end_date, days, reason, status, allocation_year,
            assigned_team_lead_id, assigned_team_lead_name, casual_days, yearly_days,
            lead_reviewer_id, lead_reviewed_by, lead_reviewed_at, lead_remarks,
            reviewed_by, reviewed_at, remarks, hr_type_override, conversion_history,
            submitted_at, created_at
        ) VALUES (
            %s, %s, %s, %s, %s, %s,
            %s, %s, %s, %s, %s, %s,
            %s, %s, %s, %s,
            %s, %s, %s, %s,
            %s, %s, %s, %s, %s,
            %s, %s
        )
        ON CONFLICT (id) DO UPDATE SET
            status = EXCLUDED.status,
            leave_type = EXCLUDED.leave_type,
            casual_days = EXCLUDED.casual_days,
            yearly_days = EXCLUDED.yearly_days,
            lead_reviewer_id = EXCLUDED.lead_reviewer_id,
            lead_reviewed_by = EXCLUDED.lead_reviewed_by,
            lead_reviewed_at = EXCLUDED.lead_reviewed_at,
            lead_remarks = EXCLUDED.lead_remarks,
            reviewed_by = EXCLUDED.reviewed_by,
            reviewed_at = EXCLUDED.reviewed_at,
            remarks = EXCLUDED.remarks,
            hr_type_override = EXCLUDED.hr_type_override,
            conversion_history = EXCLUDED.conversion_history;
    """
    now = datetime.now().isoformat()
    for lr in leave_requests:
        lr_id = lr.get("id")
        emp_id = lr.get("employee_id")
        if not lr_id or not emp_id:
            continue

        alloc_year = lr.get("allocation_year")
        if alloc_year is None:
            try:
                alloc_year = int(str(lr.get("start_date", ""))[:4])
            except (ValueError, TypeError):
                alloc_year = datetime.now().year

        conversion_history = lr.get("conversion_history") or []

        cur.execute(query, (
            lr_id,
            emp_id,
            lr.get("employee_name", ""),
            lr.get("employee_role", ""),
            lr.get("department", ""),
            lr.get("leave_type", "Casual Leave"),
            lr.get("start_date"),
            lr.get("end_date"),
            int(lr.get("days") or 1),
            lr.get("reason", ""),
            lr.get("status", "pending_lead"),
            alloc_year,
            lr.get("assigned_team_lead_id"),
            lr.get("assigned_team_lead_name"),
            int(lr.get("casual_days") or 0),
            int(lr.get("yearly_days") or 0),
            lr.get("lead_reviewer_id"),
            lr.get("lead_reviewed_by"),
            lr.get("lead_reviewed_at"),
            lr.get("lead_remarks"),
            lr.get("reviewed_by"),
            lr.get("reviewed_at"),
            lr.get("remarks"),
            bool(lr.get("hr_type_override", False)),
            database.to_json(conversion_history),
            lr.get("submitted_at") or now,
            lr.get("created_at") or now
        ))
        count += 1
    return count


def migrate_notifications(notifications: list, cur) -> int:
    """Migrates notifications into PostgreSQL."""
    count = 0
    query = """
        INSERT INTO notifications (
            id, recipient_type, recipient_id, title, message, link, notification_type, read, created_at
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (id) DO UPDATE SET
            title = EXCLUDED.title,
            message = EXCLUDED.message,
            link = EXCLUDED.link,
            notification_type = EXCLUDED.notification_type,
            read = EXCLUDED.read;
    """
    now = datetime.now().isoformat()
    for n in notifications:
        n_id = n.get("id")
        if not n_id:
            continue
        cur.execute(query, (
            n_id,
            n.get("recipient_type", "hr"),
            n.get("recipient_id", "hr_admin"),
            n.get("title", ""),
            n.get("message", ""),
            n.get("link", ""),
            n.get("notification_type", "info"),
            bool(n.get("read", False)),
            n.get("created_at") or now
        ))
        count += 1
    return count


def migrate_app_settings(data: Dict[str, Any], cur) -> int:
    """Migrates global settings such as default job description text."""
    count = 0
    jd = data.get("job_description_text")
    if jd is not None:
        query = """
            INSERT INTO app_settings (key, value, updated_at)
            VALUES (%s, %s, CURRENT_TIMESTAMP)
            ON CONFLICT (key) DO UPDATE SET
                value = EXCLUDED.value,
                updated_at = CURRENT_TIMESTAMP;
        """
        cur.execute(query, ("job_description_text", str(jd)))
        count += 1
    return count


def migrate_data(json_path: Optional[str] = None) -> Dict[str, int]:
    """
    Executes full migration from data.json to PostgreSQL.
    Initializes database schema and populates all tables transactionally.
    """
    target_file = json_path or os.environ.get("DATA_FILE", "data.json")
    logger.info(f"Starting PostgreSQL migration from {target_file}...")

    # Step 1: Ensure database schema exists
    database.init_db()

    # Step 2: Load source JSON
    data = load_json_data(target_file)

    # Step 3: Run migration in a single atomic transaction
    stats: Dict[str, int] = {}
    with database.transaction() as cur:
        # 1. Positions & Users
        stats["positions"] = migrate_positions(data.get("positions", []), cur)
        stats["users"] = migrate_users(data.get("users", []), cur)

        # 2. Candidates & Timeline
        cands, events = migrate_candidates_and_timeline(data.get("candidates", []), cur)
        stats["candidates"] = cands
        stats["timeline_events"] = events

        # 3. Employees & Attendance
        stats["employees"] = migrate_employees(data.get("employees", []), cur)
        stats["attendance"] = migrate_attendance(data.get("attendance", []), cur)

        # 4. Leave Requests & Notifications
        stats["leave_requests"] = migrate_leave_requests(data.get("leave_requests", []), cur)
        stats["notifications"] = migrate_notifications(data.get("notifications", []), cur)

        # 5. App Settings
        stats["app_settings"] = migrate_app_settings(data, cur)

    logger.info("Migration finished successfully:")
    for entity, total in stats.items():
        logger.info(f"  - {entity}: {total} record(s)")

    return stats


def main():
    parser = argparse.ArgumentParser(description="Migrate TalentAI HR data from JSON into PostgreSQL")
    parser.add_argument("--data-file", "-f", default=None, help="Path to source data.json")
    args = parser.parse_args()

    try:
        stats = migrate_data(args.data_file)
        print("\n" + "=" * 50)
        print("✅ Migration completed successfully!")
        print("=" * 50)
        for entity, total in stats.items():
            print(f"  {entity.replace('_', ' ').title():<20}: {total}")
        print("=" * 50 + "\n")
    except Exception as e:
        logger.error(f"Migration failed: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
