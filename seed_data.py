"""
TalentAI HR Platform - Seed Data Script
Directly seeds production/dummy data into PostgreSQL database tables:
Positions, Users, Candidates (CVs & scores), Chat Threads / Timeline events,
Employees, Attendance, Leave Requests, and Application Settings.
"""

import os
import logging
from datetime import datetime, date, timedelta
from werkzeug.security import generate_password_hash
import database

logger = logging.getLogger("talentai.seed")
if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("[%(asctime)s] [%(levelname)s] [seed] %(message)s"))
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)


def seed_database() -> dict:
    """Seeds comprehensive initial dummy data directly into PostgreSQL tables."""
    logger.info("Starting direct PostgreSQL dummy data seeding...")
    now = datetime.now().isoformat()
    today_str = date.today().isoformat()
    current_year = date.today().year

    summary = {
        "positions": 0,
        "users": 0,
        "candidates": 0,
        "timeline_events": 0,
        "employees": 0,
        "attendance": 0,
        "leave_requests": 0,
        "app_settings": 0
    }

    # =========================================================================
    # 1. POSITIONS
    # =========================================================================
    positions = [
        (
            "POS-101",
            "Senior Python Backend Engineer",
            "Develop high-performance microservices, REST/GraphQL APIs, and database models using Python, FastAPI/Flask, PostgreSQL, and Redis.",
            now, now
        ),
        (
            "POS-102",
            "Fullstack Developer",
            "Build modern web interfaces and scalable backend services with React, TypeScript, Python, Flask, and SQL.",
            now, now
        ),
        (
            "POS-103",
            "AI & Machine Learning Engineer",
            "Design and deploy LLM applications, retrieval-augmented pipelines, and automated screening workflows using Python, PyTorch, and Google Gemini.",
            now, now
        )
    ]

    for p in positions:
        database.execute_query(
            """
            INSERT INTO positions (id, title, description, created_at, updated_at)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (id) DO UPDATE SET title = EXCLUDED.title, description = EXCLUDED.description;
            """,
            p
        )
        summary["positions"] += 1

    # =========================================================================
    # 2. USERS
    # =========================================================================
    users = [
        ("USR-101", "hr_admin", generate_password_hash("admin123"), "Priya Sharma (HR)", "priya@corp.test", now, now),
        ("USR-102", "lead_marcus", generate_password_hash("lead123"), "Marcus Vance", "marcus@corp.test", now, now),
        ("USR-103", "candidate_jordan", generate_password_hash("pass123"), "Jordan Smith", "jordan@example.com", now, now),
    ]

    for u in users:
        database.execute_query(
            """
            INSERT INTO users (id, username, password, name, email, created_at, updated_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (id) DO UPDATE SET name = EXCLUDED.name, email = EXCLUDED.email;
            """,
            u
        )
        summary["users"] += 1

    # =========================================================================
    # 3. EMPLOYEES & HIERARCHY
    # =========================================================================
    employees = [
        {
            "id": "EMP-1001",
            "candidate_id": None,
            "user_id": "USR-102",
            "name": "Marcus Vance",
            "email": "marcus@corp.test",
            "phone": "+1-555-0101",
            "role": "Engineering Team Lead",
            "department": "Engineering",
            "access_role": "team_lead",
            "team_lead_id": None,
            "password": "emp123",
            "salary": {
                "base": 110000, "allowances": 20000, "deductions": 8000,
                "net": 122000, "currency": "$", "payment_cycle": "Monthly",
                "status": "Paid", "last_paid_date": f"{current_year}-11-01"
            },
            "leave_quota": {"casual": 12, "yearly": 15},
            "leave_balance": {
                "casual": 12, "yearly": 15,
                "casual_used": 0, "yearly_used": 0,
                "casual_pending": 0, "yearly_pending": 0,
                "casual_quota": 12, "yearly_quota": 15
            }
        },
        {
            "id": "EMP-1002",
            "candidate_id": None,
            "user_id": None,
            "name": "Alex Rivera",
            "email": "alex@corp.test",
            "phone": "+1-555-0102",
            "role": "Senior Software Engineer",
            "department": "Engineering",
            "access_role": "employee",
            "team_lead_id": "EMP-1001",
            "password": "emp123",
            "salary": {
                "base": 90000, "allowances": 15000, "deductions": 5000,
                "net": 100000, "currency": "$", "payment_cycle": "Monthly",
                "status": "Paid", "last_paid_date": f"{current_year}-11-01"
            },
            "leave_quota": {"casual": 12, "yearly": 15},
            "leave_balance": {
                "casual": 9, "yearly": 15,
                "casual_used": 3, "yearly_used": 0,
                "casual_pending": 2, "yearly_pending": 0,
                "casual_quota": 12, "yearly_quota": 15
            }
        },
        {
            "id": "EMP-1003",
            "candidate_id": None,
            "user_id": "USR-101",
            "name": "Priya Sharma",
            "email": "priya@corp.test",
            "phone": "+1-555-0103",
            "role": "HR Operations Lead",
            "department": "Human Resources",
            "access_role": "hr_admin",
            "team_lead_id": None,
            "password": "emp123",
            "salary": {
                "base": 95000, "allowances": 15000, "deductions": 6000,
                "net": 104000, "currency": "$", "payment_cycle": "Monthly",
                "status": "Paid", "last_paid_date": f"{current_year}-11-01"
            },
            "leave_quota": {"casual": 12, "yearly": 15},
            "leave_balance": {
                "casual": 12, "yearly": 15,
                "casual_used": 0, "yearly_used": 0,
                "casual_pending": 0, "yearly_pending": 0,
                "casual_quota": 12, "yearly_quota": 15
            }
        }
    ]

    emp_query = """
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
            name = EXCLUDED.name,
            email = EXCLUDED.email,
            role = EXCLUDED.role,
            access_role = EXCLUDED.access_role,
            team_lead_id = EXCLUDED.team_lead_id,
            salary = EXCLUDED.salary,
            leave_quota = EXCLUDED.leave_quota,
            leave_balance = EXCLUDED.leave_balance;
    """

    for emp in employees:
        database.execute_query(
            emp_query,
            (
                emp["id"], emp["candidate_id"], emp["user_id"], emp["name"], emp["email"], emp["phone"],
                emp["role"], emp["department"], f"{current_year}-01-15", "Active", emp["password"],
                emp["access_role"], emp["team_lead_id"],
                database.to_json(emp["salary"]),
                database.to_json(emp["leave_quota"]),
                database.to_json(emp["leave_balance"]),
                now, now
            )
        )
        summary["employees"] += 1

    # =========================================================================
    # 4. CANDIDATES (APPLICANT CVS, SCORES, ATTACHMENTS)
    # =========================================================================
    candidates = [
        {
            "id": "CAND-101",
            "position_id": "POS-101",
            "user_id": "USR-103",
            "name": "Jordan Smith",
            "email": "jordan@example.com",
            "phone": "+1-555-0199",
            "university": "Stanford University",
            "status": "accepted",
            "stage": "Interview",
            "job_role": "Senior Backend Engineer",
            "position": "Senior Python Backend Engineer",
            "raw_resume_text": (
                "Jordan Smith - Senior Backend Engineer\n"
                "Email: jordan@example.com | Phone: +1-555-0199 | San Francisco, CA\n\n"
                "Summary:\n"
                "Senior Python Engineer with 6+ years building high-concurrency microservices, "
                "RESTful APIs, and distributed architectures in PostgreSQL and Redis. Expert in FastAPI, "
                "Flask, async IO, Docker, and AWS.\n\n"
                "Experience:\n"
                "- Senior Backend Engineer, Nexus Cloud Inc. (2021 - Present)\n"
                "  * Scaled streaming pipelines handling 50k req/s using Python & PostgreSQL.\n"
                "  * Decreased query response times by 45% via indexing and connection pooling.\n"
                "- Software Engineer, DataPulse Corp. (2018 - 2021)\n"
                "  * Built core REST APIs using Flask, SQLAlchemy, and PostgreSQL.\n\n"
                "Education:\n"
                "- B.S. in Computer Science, Stanford University (GPA: 3.85)\n\n"
                "Skills: Python, PostgreSQL, FastAPI, Flask, Docker, Kubernetes, AWS, Redis, SQL"
            ),
            "source_file": "jordan_smith_resume.pdf",
            "analysis_method": "AI Analysis",
            "python_score": 9.5,
            "experience_score": 9.0,
            "uni_tier_score": 8.5,
            "final_rank_score": 9.2,
            "python_experience_years": 6.0,
            "scores": {
                "python_score": 9.5, "python_evidence": "6+ years production Python and AsyncIO microservices",
                "experience_score": 9.0, "experience_evidence": "Led backend engineering at Nexus Cloud Inc.",
                "uni_tier_score": 8.5, "uni_evidence": "Stanford University Computer Science B.S.",
                "final_rank_score": 9.2, "python_experience_years": 6.0
            },
            "skills": ["Python", "PostgreSQL", "FastAPI", "Flask", "Docker", "Kubernetes", "AWS", "Redis"],
            "attachments": [
                {"filename": "jordan_smith_resume.pdf", "url": "/uploads/attachments/jordan_smith_resume.pdf"}
            ],
            "interview": {
                "status": "scheduled",
                "date": f"{current_year}-12-01",
                "time": "14:00",
                "round_title": "System Design & Architecture Round",
                "meeting_link": "https://meet.talentai.local/interview/jordan-smith",
                "hr_note": "Please have your webcam ready and camera on.",
                "scheduled_at": now
            }
        },
        {
            "id": "CAND-102",
            "position_id": "POS-103",
            "user_id": None,
            "name": "Maya Lin",
            "email": "maya@example.com",
            "phone": "+1-555-0244",
            "university": "Massachusetts Institute of Technology (MIT)",
            "status": "pending",
            "stage": "Screening",
            "job_role": "AI & Machine Learning Engineer",
            "position": "AI & Machine Learning Engineer",
            "raw_resume_text": (
                "Maya Lin - AI / Machine Learning Engineer\n"
                "Email: maya@example.com | Boston, MA\n\n"
                "Education:\n"
                "- M.S. in Artificial Intelligence, Massachusetts Institute of Technology (MIT)\n\n"
                "Skills & Expertise:\n"
                "PyTorch, Transformers, LLM fine-tuning, Gemini API, Vector Databases (pgvector), Python, MLOps"
            ),
            "source_file": "maya_lin_cv.pdf",
            "analysis_method": "AI Analysis",
            "python_score": 9.6,
            "experience_score": 9.2,
            "uni_tier_score": 9.5,
            "final_rank_score": 9.4,
            "python_experience_years": 5.0,
            "scores": {
                "python_score": 9.6, "python_evidence": "Advanced PyTorch and LLM inference engine development",
                "experience_score": 9.2, "experience_evidence": "Deployed LLM production pipelines",
                "uni_tier_score": 9.5, "uni_evidence": "MIT Artificial Intelligence M.S.",
                "final_rank_score": 9.4, "python_experience_years": 5.0
            },
            "skills": ["Python", "PyTorch", "Transformers", "PostgreSQL", "MLOps", "LLMs"],
            "attachments": [
                {"filename": "maya_lin_cv.pdf", "url": "/uploads/attachments/maya_lin_cv.pdf"}
            ],
            "interview": {}
        },
        {
            "id": "CAND-103",
            "position_id": "POS-102",
            "user_id": None,
            "name": "Liam Connor",
            "email": "liam@example.com",
            "phone": "+1-555-0388",
            "university": "UC Berkeley",
            "status": "pending",
            "stage": "Technical Review",
            "job_role": "Fullstack Developer",
            "position": "Fullstack Developer",
            "raw_resume_text": (
                "Liam Connor - Fullstack Developer\n"
                "Email: liam@example.com | San Jose, CA\n\n"
                "Experience:\n"
                "4+ years building fullstack web apps using Python, Django, React, TypeScript, and PostgreSQL."
            ),
            "source_file": "liam_connor_cv.pdf",
            "analysis_method": "AI Analysis",
            "python_score": 8.7,
            "experience_score": 8.9,
            "uni_tier_score": 8.8,
            "final_rank_score": 8.8,
            "python_experience_years": 4.0,
            "scores": {
                "python_score": 8.7, "python_evidence": "Fullstack Django and REST APIs",
                "experience_score": 8.9, "experience_evidence": "4 years fullstack web development",
                "uni_tier_score": 8.8, "uni_evidence": "UC Berkeley",
                "final_rank_score": 8.8, "python_experience_years": 4.0
            },
            "skills": ["Python", "React", "TypeScript", "Django", "Flask", "PostgreSQL"],
            "attachments": [
                {"filename": "liam_connor_cv.pdf", "url": "/uploads/attachments/liam_connor_cv.pdf"}
            ],
            "interview": {}
        }
    ]

    cand_query = """
        INSERT INTO candidates (
            id, position_id, user_id, name, email, phone, university,
            status, stage, job_role, position, raw_resume_text, source_file, analysis_method,
            python_score, experience_score, uni_tier_score, final_rank_score, python_experience_years,
            scores, skills, attachments, interview, created_at, updated_at
        ) VALUES (
            %s, %s, %s, %s, %s, %s, %s,
            %s, %s, %s, %s, %s, %s, %s,
            %s, %s, %s, %s, %s,
            %s, %s, %s, %s, %s, %s
        )
        ON CONFLICT (id) DO UPDATE SET
            name = EXCLUDED.name,
            email = EXCLUDED.email,
            status = EXCLUDED.status,
            stage = EXCLUDED.stage,
            raw_resume_text = EXCLUDED.raw_resume_text,
            final_rank_score = EXCLUDED.final_rank_score,
            scores = EXCLUDED.scores,
            skills = EXCLUDED.skills,
            attachments = EXCLUDED.attachments,
            interview = EXCLUDED.interview;
    """

    for c in candidates:
        database.execute_query(
            cand_query,
            (
                c["id"], c["position_id"], c["user_id"], c["name"], c["email"], c["phone"], c["university"],
                c["status"], c["stage"], c["job_role"], c["position"], c["raw_resume_text"], c["source_file"],
                c["analysis_method"], c["python_score"], c["experience_score"], c["uni_tier_score"],
                c["final_rank_score"], c["python_experience_years"],
                database.to_json(c["scores"]),
                database.to_json(c["skills"]),
                database.to_json(c["attachments"]),
                database.to_json(c["interview"]),
                now, now
            )
        )
        summary["candidates"] += 1

    # =========================================================================
    # 5. CHAT THREADS & CANDIDATE TIMELINE
    # =========================================================================
    timeline_events = [
        # Jordan Smith Thread
        (
            "TL-101", "CAND-101", "system", "TalentAI Screening Engine", "system",
            "Application received and screened. Candidate match score: 9.2/10.0 (Python 9.5, Experience 9.0).",
            database.to_json({"scores": {"final_rank_score": 9.2}}), database.to_json([]),
            (datetime.now() - timedelta(days=3)).isoformat()
        ),
        (
            "TL-102", "CAND-101", "hr", "Priya Sharma (HR)", "message",
            "Hello Jordan, your application has progressed to the Technical Interview stage! Please confirm attendance.",
            database.to_json({}), database.to_json([]),
            (datetime.now() - timedelta(days=2)).isoformat()
        ),
        (
            "TL-103", "CAND-101", "candidate", "Jordan Smith", "message",
            "Thank you! I am delighted to confirm attendance for the System Design round on Friday at 2:00 PM.",
            database.to_json({}), database.to_json([]),
            (datetime.now() - timedelta(days=1)).isoformat()
        ),
        (
            "TL-104", "CAND-101", "hr", "Priya Sharma (HR)", "message",
            "Wonderful. Here is the preliminary architecture prompt file for you to review before Friday.",
            database.to_json({}),
            database.to_json([{"filename": "system_design_prompt.pdf", "url": "/uploads/attachments/system_design_prompt.pdf"}]),
            now
        ),

        # Maya Lin Thread
        (
            "TL-105", "CAND-102", "system", "TalentAI Screening Engine", "system",
            "Application received and screened. Candidate match score: 9.4/10.0 (Top Tier MIT AI background).",
            database.to_json({"scores": {"final_rank_score": 9.4}}), database.to_json([]),
            (datetime.now() - timedelta(days=2)).isoformat()
        ),
        (
            "TL-106", "CAND-102", "hr", "Priya Sharma (HR)", "internal_note",
            "Exceptional candidate profile for the AI & Machine Learning position. Prioritize screening call.",
            database.to_json({}), database.to_json([]),
            (datetime.now() - timedelta(days=1)).isoformat()
        ),

        # Liam Connor Thread
        (
            "TL-107", "CAND-103", "system", "TalentAI Screening Engine", "system",
            "Application received and screened. Candidate match score: 8.8/10.0.",
            database.to_json({"scores": {"final_rank_score": 8.8}}), database.to_json([]),
            (datetime.now() - timedelta(days=2)).isoformat()
        ),
        (
            "TL-108", "CAND-103", "candidate", "Liam Connor", "message",
            "Attached is my portfolio document highlighting recent React and Django projects.",
            database.to_json({}),
            database.to_json([{"filename": "portfolio_showcase.pdf", "url": "/uploads/attachments/portfolio_showcase.pdf"}]),
            now
        )
    ]

    timeline_query = """
        INSERT INTO candidate_timeline (
            id, candidate_id, sender, sender_name, type, content, metadata, attachments, timestamp, created_at
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (id) DO UPDATE SET
            content = EXCLUDED.content,
            metadata = EXCLUDED.metadata,
            attachments = EXCLUDED.attachments;
    """

    for tl in timeline_events:
        database.execute_query(
            timeline_query,
            (tl[0], tl[1], tl[2], tl[3], tl[4], tl[5], tl[6], tl[7], tl[8], tl[8])
        )
        summary["timeline_events"] += 1

    # =========================================================================
    # 6. ATTENDANCE
    # =========================================================================
    attendance_records = [
        ("ATT-101", "EMP-1001", "Marcus Vance", today_str, "08:55 AM", None, 0.0, "Present", "On time"),
        ("ATT-102", "EMP-1002", "Alex Rivera", today_str, "09:05 AM", None, 0.0, "Present", "On time")
    ]

    for att in attendance_records:
        database.execute_query(
            """
            INSERT INTO attendance (
                id, employee_id, employee_name, date, clock_in, clock_out, total_hours, status, notes, created_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (employee_id, date) DO UPDATE SET
                clock_in = EXCLUDED.clock_in,
                status = EXCLUDED.status;
            """,
            (att[0], att[1], att[2], att[3], att[4], att[5], att[6], att[7], att[8], now)
        )
        summary["attendance"] += 1

    # =========================================================================
    # 7. LEAVE REQUESTS (CASUAL-FIRST 12-DAY CAP DEMONSTRATION)
    # =========================================================================
    leave_requests = [
        # Approved 3-day casual leave
        (
            "LR-101", "EMP-1002", "Alex Rivera", "Senior Software Engineer", "Engineering",
            "Casual Leave", f"{current_year}-11-10", f"{current_year}-11-12", 3,
            "Family visit", "approved", current_year, "EMP-1001", "Marcus Vance",
            3, 0, "EMP-1001", "Marcus Vance", (datetime.now() - timedelta(days=12)).isoformat(),
            "Approved by team lead", "Priya Sharma (HR)", (datetime.now() - timedelta(days=11)).isoformat(),
            "Approved by HR", False, database.to_json([]), (datetime.now() - timedelta(days=13)).isoformat(), now
        ),
        # Pending 2-day casual leave awaiting Team Lead approval
        (
            "LR-102", "EMP-1002", "Alex Rivera", "Senior Software Engineer", "Engineering",
            "Casual Leave", f"{current_year}-12-05", f"{current_year}-12-06", 2,
            "Doctor checkup and personal appointment", "pending_lead", current_year, "EMP-1001", "Marcus Vance",
            2, 0, None, None, None, None, None, None, None, False, database.to_json([]),
            now, now
        )
    ]

    leave_query = """
        INSERT INTO leave_requests (
            id, employee_id, employee_name, employee_role, department,
            leave_type, start_date, end_date, days, reason,
            status, allocation_year, assigned_team_lead_id, assigned_team_lead_name,
            casual_days, yearly_days, lead_reviewer_id, lead_reviewed_by,
            lead_reviewed_at, lead_remarks, reviewed_by, reviewed_at,
            remarks, hr_type_override, conversion_history, submitted_at, created_at
        ) VALUES (
            %s, %s, %s, %s, %s,
            %s, %s, %s, %s, %s,
            %s, %s, %s, %s,
            %s, %s, %s, %s,
            %s, %s, %s, %s,
            %s, %s, %s, %s, %s
        )
        ON CONFLICT (id) DO UPDATE SET
            status = EXCLUDED.status,
            casual_days = EXCLUDED.casual_days,
            yearly_days = EXCLUDED.yearly_days;
    """

    for lr in leave_requests:
        database.execute_query(leave_query, lr)
        summary["leave_requests"] += 1

    # =========================================================================
    # 8. APP SETTINGS (DEFAULT JOB DESCRIPTION)
    # =========================================================================
    default_jd = (
        "TalentAI is looking for an exceptional Senior Backend Engineer to join our core distributed team. "
        "Required Qualifications: 5+ years building backend systems in Python, FastAPI, and PostgreSQL. "
        "Experience with Docker, Kubernetes, and AWS cloud architectures. Strong communication and problem solving skills."
    )
    database.execute_query(
        """
        INSERT INTO app_settings (key, value, updated_at)
        VALUES ('job_description', %s, CURRENT_TIMESTAMP)
        ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = CURRENT_TIMESTAMP;
        """,
        (default_jd,)
    )
    summary["app_settings"] += 1

    logger.info(f"Direct PostgreSQL dummy data seeding finished successfully: {summary}")
    return summary


if __name__ == "__main__":
    seed_database()
