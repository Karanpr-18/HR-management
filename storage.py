import json
import os
import uuid
from datetime import datetime, date, timedelta
from typing import List, Dict, Optional, Tuple, Any

try:
    import database
except ImportError:
    database = None

DATA_FILE = os.environ.get("DATA_FILE", "data.json")
CASUAL_LEAVE_YEARLY_CAP = 12
DEFAULT_YEARLY_LEAVE_QUOTA = 15
VALID_ACCESS_ROLES = ("employee", "team_lead")
ACTIVE_LEAVE_STATUSES = ("pending_lead", "pending_hr", "approved")

def _use_postgres() -> bool:
    """
    Determines if PostgreSQL backend should be used for data operations.
    Returns True when database connection or mock is available and enabled.
    Falls back gracefully to JSON storage otherwise.
    """
    if database is None:
        return False
    if getattr(database, "_mock_connection", None) is not None:
        return True
    explicit = os.environ.get("USE_POSTGRES", "").strip().lower()
    if explicit in ("0", "false", "no"):
        return False
    if explicit in ("1", "true", "yes"):
        try:
            return database.is_database_available()
        except Exception:
            return False
    if database.is_postgres_configured():
        try:
            return database.is_database_available()
        except Exception:
            return False
    return False

def _format_candidate_from_db(row: Dict[str, Any], include_timeline: bool = True) -> Dict[str, Any]:
    """Formats a PostgreSQL candidates row into standard application dictionary."""
    if not row:
        return {}
    cand = dict(row)
    for score_field in ("python_score", "experience_score", "uni_tier_score", "final_rank_score", "python_experience_years"):
        val = cand.get(score_field)
        cand[score_field] = float(val) if val is not None else 0.0

    cand["scores"] = database.from_json(cand.get("scores")) or {}
    cand["skills"] = database.from_json(cand.get("skills")) or []
    cand["attachments"] = database.from_json(cand.get("attachments")) or []
    cand["interview"] = database.from_json(cand.get("interview")) or {}
    cand["interview_rounds"] = database.from_json(cand.get("interview_rounds")) or []

    # Evidence fields unpacked from scores dict if available
    scores_dict = cand["scores"] if isinstance(cand["scores"], dict) else {}
    for k in ("python_evidence", "evidence_quote", "uni_evidence", "experience_evidence"):
        if k in scores_dict and k not in cand:
            cand[k] = scores_dict[k]

    for ts_col in ("created_at", "updated_at"):
        val = cand.get(ts_col)
        if isinstance(val, (datetime, date)):
            cand[ts_col] = val.isoformat()

    # Unpack any additional parsed_data attributes
    parsed = database.from_json(cand.pop("parsed_data", None)) or {}
    if isinstance(parsed, dict):
        for k, v in parsed.items():
            if k not in cand:
                cand[k] = v

    if include_timeline:
        cand["timeline"] = _get_candidate_timeline_from_db(cand["id"], auto_generate=False)
    else:
        cand["timeline"] = []

    return cand

def _format_timeline_from_db(row: Dict[str, Any]) -> Dict[str, Any]:
    """Formats a PostgreSQL candidate_timeline row into a timeline event dictionary."""
    if not row:
        return {}
    event = dict(row)
    event["metadata"] = database.from_json(event.get("metadata")) or {}
    event["attachments"] = database.from_json(event.get("attachments")) or []
    for ts_col in ("timestamp", "created_at"):
        val = event.get(ts_col)
        if isinstance(val, (datetime, date)):
            event[ts_col] = val.isoformat()
    return event

def _save_candidate_to_db(candidate_data: Dict) -> str:
    """Inserts or updates a candidate CV in the PostgreSQL database."""
    cand_id = candidate_data.get("id") or str(uuid.uuid4())
    candidate_data["id"] = cand_id
    created_at = candidate_data.get("created_at") or datetime.now().isoformat()
    candidate_data["created_at"] = created_at
    status = candidate_data.get("status", "pending")
    stage = candidate_data.get("stage", "Screening")

    raw_resume = candidate_data.get("raw_resume_text") or candidate_data.get("resume_text") or ""
    skills = candidate_data.get("skills") or []
    if isinstance(skills, str):
        skills = [s.strip() for s in skills.split(",") if s.strip()]

    scores = candidate_data.get("scores")
    if not scores or not isinstance(scores, dict):
        scores = {
            "python_score": float(candidate_data.get("python_score") or 0.0),
            "python_evidence": candidate_data.get("python_evidence") or candidate_data.get("evidence_quote") or "",
            "experience_score": float(candidate_data.get("experience_score") or 0.0),
            "experience_evidence": candidate_data.get("experience_evidence") or "",
            "uni_tier_score": float(candidate_data.get("uni_tier_score") or 0.0),
            "uni_evidence": candidate_data.get("uni_evidence") or "",
            "python_experience_years": float(candidate_data.get("python_experience_years") or 0.0),
            "final_rank_score": float(candidate_data.get("final_rank_score") or 0.0),
        }

    known_keys = {
        "id", "position_id", "user_id", "employee_id", "name", "email", "phone", "university",
        "status", "stage", "job_role", "position", "raw_resume_text", "resume_text", "source_file",
        "analysis_method", "python_score", "experience_score", "uni_tier_score", "final_rank_score",
        "python_experience_years", "scores", "skills", "parsed_data", "attachments", "interview",
        "interview_rounds", "created_at", "updated_at", "timeline", "python_evidence", "evidence_quote",
        "uni_evidence", "experience_evidence"
    }
    extra_data = {k: v for k, v in candidate_data.items() if k not in known_keys}
    parsed_data = candidate_data.get("parsed_data") or {}
    if extra_data:
        parsed_data = dict(parsed_data)
        parsed_data.update(extra_data)

    attachments = candidate_data.get("attachments") or []
    interview = candidate_data.get("interview") or {}
    interview_rounds = candidate_data.get("interview_rounds") or []

    query = """
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
            %s, CURRENT_TIMESTAMP
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
            updated_at = CURRENT_TIMESTAMP;
    """
    database.execute_query(query, (
        cand_id,
        candidate_data.get("position_id"),
        candidate_data.get("user_id"),
        candidate_data.get("employee_id"),
        candidate_data.get("name", "Unnamed Candidate"),
        candidate_data.get("email"),
        candidate_data.get("phone"),
        candidate_data.get("university"),
        status,
        stage,
        candidate_data.get("job_role"),
        candidate_data.get("position"),
        raw_resume,
        candidate_data.get("source_file"),
        candidate_data.get("analysis_method", "AI Analysis"),
        float(candidate_data.get("python_score") or 0.0),
        float(candidate_data.get("experience_score") or 0.0),
        float(candidate_data.get("uni_tier_score") or 0.0),
        float(candidate_data.get("final_rank_score") or 0.0),
        float(candidate_data.get("python_experience_years") or 0.0),
        database.to_json(scores),
        database.to_json(skills),
        database.to_json(parsed_data),
        database.to_json(attachments),
        database.to_json(interview),
        database.to_json(interview_rounds),
        created_at
    ))

    # Save any timeline events provided in the candidate dict
    for event in candidate_data.get("timeline", []):
        event_id = event.get("id") or str(uuid.uuid4())
        event_ts = event.get("timestamp") or datetime.now().isoformat()
        event_meta = event.get("metadata") or {}
        event_att = event.get("attachments") or event_meta.get("attachments") or []
        t_query = """
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
        database.execute_query(t_query, (
            event_id,
            cand_id,
            event.get("sender", "system"),
            event.get("sender_name", "System"),
            event.get("type", "system"),
            event.get("content", ""),
            database.to_json(event_meta),
            database.to_json(event_att),
            event_ts,
            event_ts
        ))

    return cand_id

def _get_candidate_timeline_from_db(candidate_id: str, auto_generate: bool = True) -> List[Dict]:
    """Retrieves timeline events from candidate_timeline table, auto-generating history if empty."""
    rows = database.execute_query(
        "SELECT * FROM candidate_timeline WHERE candidate_id = %s ORDER BY timestamp ASC, created_at ASC;",
        (candidate_id,),
        fetch="all"
    )
    if rows:
        return [_format_timeline_from_db(r) for r in rows]

    if not auto_generate:
        return []

    # Synthesize timeline from candidate row if empty
    cand_row = database.execute_query("SELECT * FROM candidates WHERE id = %s;", (candidate_id,), fetch="one")
    if not cand_row:
        return []
    candidate = _format_candidate_from_db(cand_row, include_timeline=False)
    synthesized = _synthesize_candidate_timeline(candidate)
    for event in synthesized:
        database.execute_query(
            """
            INSERT INTO candidate_timeline (
                id, candidate_id, sender, sender_name, type, content, metadata, attachments, timestamp, created_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (id) DO NOTHING;
            """,
            (
                event["id"],
                candidate_id,
                event["sender"],
                event["sender_name"],
                event["type"],
                event["content"],
                database.to_json(event.get("metadata") or {}),
                database.to_json(event.get("attachments") or []),
                event["timestamp"],
                event["timestamp"]
            )
        )
    return synthesized

def _synthesize_candidate_timeline(candidate: Dict) -> List[Dict]:
    """Synthesizes initial timeline events from existing candidate application data."""
    synthesized = []
    created_at = candidate.get("created_at") or datetime.now().isoformat()
    pos = get_position(candidate.get("position_id"))
    pos_title = pos.get("title", "Job Position") if pos else "Job Position"
    cand_name = candidate.get("name", "Candidate")

    # 1. Application submission
    synthesized.append({
        "id": str(uuid.uuid4()),
        "sender": "candidate",
        "sender_name": cand_name,
        "type": "system",
        "content": f"Submitted resume application for {pos_title}.",
        "metadata": {"source_file": candidate.get("source_file")},
        "attachments": candidate.get("attachments") or [],
        "timestamp": created_at
    })

    # 2. AI Screening result
    synthesized.append({
        "id": str(uuid.uuid4()),
        "sender": "system",
        "sender_name": "TalentAI Screening Engine",
        "type": "system",
        "content": f"AI Resume screening completed with final rank score {candidate.get('final_rank_score', 0)}/10 (Python: {candidate.get('python_score', 0)}, Exp: {candidate.get('experience_score', 0)}, Uni: {candidate.get('uni_tier_score', 0)}).",
        "metadata": {"score": candidate.get("final_rank_score")},
        "attachments": [],
        "timestamp": created_at
    })

    # 3. Interviews history
    intv = candidate.get("interview")
    if intv and isinstance(intv, dict):
        for h in intv.get("history", []):
            act = h.get("action")
            ts = h.get("timestamp", created_at)
            if act == "scheduled_by_hr":
                synthesized.append({
                    "id": str(uuid.uuid4()),
                    "sender": "hr",
                    "sender_name": "HR Admin",
                    "type": "interview",
                    "content": f"Scheduled interview for {h.get('date')} at {h.get('time')}." + (f" Note: {h.get('note')}" if h.get("note") else ""),
                    "metadata": h,
                    "attachments": [],
                    "timestamp": ts
                })
            elif act == "confirmed_by_candidate":
                synthesized.append({
                    "id": str(uuid.uuid4()),
                    "sender": "candidate",
                    "sender_name": cand_name,
                    "type": "message",
                    "content": "Confirmed attendance for the scheduled interview.",
                    "metadata": h,
                    "attachments": [],
                    "timestamp": ts
                })
            elif act == "reschedule_requested":
                synthesized.append({
                    "id": str(uuid.uuid4()),
                    "sender": "candidate",
                    "sender_name": cand_name,
                    "type": "reschedule",
                    "content": f"Requested reschedule to {h.get('proposed_date')} at {h.get('proposed_time')}." + (f" Reason: {h.get('reason')}" if h.get("reason") else ""),
                    "metadata": h,
                    "attachments": [],
                    "timestamp": ts
                })
            elif act == "reschedule_approved_by_hr":
                synthesized.append({
                    "id": str(uuid.uuid4()),
                    "sender": "hr",
                    "sender_name": "HR Admin",
                    "type": "reschedule",
                    "content": f"Approved candidate's reschedule request for {h.get('date')} at {h.get('time')}." + (f" Note: {h.get('note')}" if h.get("note") else ""),
                    "metadata": h,
                    "attachments": [],
                    "timestamp": ts
                })
            elif act == "declined_by_candidate":
                synthesized.append({
                    "id": str(uuid.uuid4()),
                    "sender": "candidate",
                    "sender_name": cand_name,
                    "type": "message",
                    "content": "Declined interview invitation." + (f" Reason: {h.get('reason')}" if h.get("reason") else ""),
                    "metadata": h,
                    "attachments": [],
                    "timestamp": ts
                })

    return synthesized

def _default_data() -> Dict:
    return {
        "positions": [],
        "candidates": [],
        "users": [],
        "notifications": [],
        "employees": [],
        "attendance": [],
        "leave_requests": [],
    }

def _load_data() -> Dict:
    if not os.path.exists(DATA_FILE):
        return _default_data()
    try:
        with open(DATA_FILE, 'r') as f:
            data = json.load(f)
            # Migration: ensure keys exist
            for key in ("positions", "candidates", "users", "notifications", "employees", "attendance", "leave_requests"):
                if key not in data:
                    data[key] = []
            if _migrate_rbac_and_leave_data(data):
                _save_data(data)
            return data
    except json.JSONDecodeError:
         return _default_data()

def _save_data(data: Dict):
    dir_name = os.path.dirname(DATA_FILE)
    if dir_name:
        os.makedirs(dir_name, exist_ok=True)
    temp_file = f"{DATA_FILE}.tmp.{os.getpid()}"
    with open(temp_file, 'w') as f:
        json.dump(data, f, indent=2)
    os.replace(temp_file, DATA_FILE)

# ============ RBAC & Two-Tier Leave Helpers / Migration ============

def _format_leave_type(casual_days: int, yearly_days: int) -> str:
    """Formats human-readable leave type from casual and yearly day counts."""
    if casual_days > 0 and yearly_days > 0:
        return f"Mixed ({casual_days} Casual + {yearly_days} Yearly)"
    if yearly_days > 0 and casual_days == 0:
        return "Yearly Leave"
    return "Casual Leave"

def _get_emp_leave_quotas(emp: Dict) -> Tuple[int, int]:
    """Returns (casual_quota, yearly_quota) with casual strictly capped at 12."""
    quota = emp.get("leave_quota") or {}
    raw_casual = quota.get("casual", CASUAL_LEAVE_YEARLY_CAP)
    try:
        casual_quota = min(max(int(raw_casual), 0), CASUAL_LEAVE_YEARLY_CAP)
    except (TypeError, ValueError):
        casual_quota = CASUAL_LEAVE_YEARLY_CAP

    raw_yearly = quota.get("yearly", DEFAULT_YEARLY_LEAVE_QUOTA)
    try:
        yearly_quota = max(int(raw_yearly), 0)
    except (TypeError, ValueError):
        yearly_quota = DEFAULT_YEARLY_LEAVE_QUOTA
    return casual_quota, yearly_quota

def _compute_year_leave_stats_in_data(data: Dict, emp: Dict, year: int = None) -> Dict:
    """Computes leave stats for an employee in a calendar year from an in-memory data dict."""
    target_year = int(year or datetime.now().year)
    emp_id = emp.get("id")
    casual_quota, yearly_quota = _get_emp_leave_quotas(emp)

    approved_casual = 0
    approved_yearly = 0
    pending_casual = 0
    pending_yearly = 0

    for leave in data.get("leave_requests", []):
        if leave.get("employee_id") != emp_id:
            continue
        l_year = leave.get("allocation_year")
        if l_year is None:
            try:
                l_year = int(str(leave.get("start_date", ""))[:4])
            except (TypeError, ValueError):
                l_year = target_year
        if int(l_year) != target_year:
            continue

        c_days = int(leave.get("casual_days", 0) or 0)
        y_days = int(leave.get("yearly_days", 0) or 0)
        status = (leave.get("status") or "").lower()

        if status == "approved":
            approved_casual += c_days
            approved_yearly += y_days
        elif status in ("pending_lead", "pending_hr"):
            pending_casual += c_days
            pending_yearly += y_days

    casual_remaining = max(casual_quota - approved_casual, 0)
    yearly_remaining = max(yearly_quota - approved_yearly, 0)
    casual_available = max(casual_quota - approved_casual - pending_casual, 0)
    yearly_available = max(yearly_quota - approved_yearly - pending_yearly, 0)

    return {
        "year": target_year,
        "casual_quota": casual_quota,
        "yearly_quota": yearly_quota,
        "approved_casual": approved_casual,
        "approved_yearly": approved_yearly,
        "pending_casual": pending_casual,
        "pending_yearly": pending_yearly,
        "casual_remaining": casual_remaining,
        "yearly_remaining": yearly_remaining,
        "casual_available": casual_available,
        "yearly_available": yearly_available,
    }

def _recalculate_employee_balance_in_data(data: Dict, employee_id: str, year: int = None) -> Optional[Dict]:
    """Recalculates and updates an employee's leave_balance dict in memory."""
    for emp in data.get("employees", []):
        if emp.get("id") == employee_id:
            stats = _compute_year_leave_stats_in_data(data, emp, year=year)
            emp["leave_balance"] = {
                "casual": stats["casual_remaining"],
                "yearly": stats["yearly_remaining"],
                "casual_used": stats["approved_casual"],
                "yearly_used": stats["approved_yearly"],
                "casual_pending": stats["pending_casual"],
                "yearly_pending": stats["pending_yearly"],
                "casual_quota": stats["casual_quota"],
                "yearly_quota": stats["yearly_quota"],
            }
            return emp["leave_balance"]
    return None

def _append_notification(data: Dict, recipient_type: str, recipient_id: str, title: str, message: str, link: str = "", notification_type: str = "info") -> str:
    """Appends an in-app notification to in-memory data without overwriting pending mutations."""
    if "notifications" not in data:
        data["notifications"] = []
    notif_id = str(uuid.uuid4())
    notif = {
        "id": notif_id,
        "recipient_type": recipient_type,
        "recipient_id": str(recipient_id),
        "title": title,
        "message": message,
        "link": link,
        "notification_type": notification_type,
        "read": False,
        "created_at": datetime.now().isoformat(),
    }
    data["notifications"].insert(0, notif)
    return notif_id

def _migrate_rbac_and_leave_data(data: Dict) -> bool:
    """Idempotently migrates legacy employees and leave_requests to RBAC + 2-type leave schema."""
    changed = False
    employees = data.get("employees", [])
    leaves = data.get("leave_requests", [])

    has_any_role = any("access_role" in e for e in employees)
    emp_ids = {e.get("id") for e in employees}

    for emp in employees:
        if "access_role" not in emp:
            if not has_any_role and emp.get("id") in ("EMP-1002", "EMP-1004"):
                emp["access_role"] = "team_lead"
            else:
                emp["access_role"] = "employee"
            changed = True
        elif emp.get("access_role") not in VALID_ACCESS_ROLES:
            emp["access_role"] = "employee"
            changed = True

        if "team_lead_id" not in emp:
            if emp.get("access_role") == "employee" and not has_any_role:
                dept = (emp.get("department") or "").lower()
                if "product" in dept or "design" in dept:
                    emp["team_lead_id"] = "EMP-1002" if "EMP-1002" in emp_ids else ("EMP-1004" if "EMP-1004" in emp_ids else None)
                else:
                    emp["team_lead_id"] = "EMP-1004" if "EMP-1004" in emp_ids else ("EMP-1002" if "EMP-1002" in emp_ids else None)
            else:
                emp["team_lead_id"] = None
            changed = True

        if "leave_quota" not in emp or not isinstance(emp.get("leave_quota"), dict):
            emp["leave_quota"] = {
                "casual": CASUAL_LEAVE_YEARLY_CAP,
                "yearly": DEFAULT_YEARLY_LEAVE_QUOTA,
            }
            changed = True
        else:
            capped_casual = min(max(int(emp["leave_quota"].get("casual", CASUAL_LEAVE_YEARLY_CAP)), 0), CASUAL_LEAVE_YEARLY_CAP)
            if emp["leave_quota"].get("casual") != capped_casual:
                emp["leave_quota"]["casual"] = capped_casual
                changed = True
            if "yearly" not in emp["leave_quota"]:
                emp["leave_quota"]["yearly"] = DEFAULT_YEARLY_LEAVE_QUOTA
                changed = True

    emp_by_id = {e.get("id"): e for e in employees}

    # Track already-migrated approved casual days per (emp_id, year) to enforce <= 12 cap
    approved_casual_used: Dict[Tuple[str, int], int] = {}
    for leave in leaves:
        if "casual_days" in leave and "yearly_days" in leave and (leave.get("status") or "").lower() == "approved":
            try:
                yr = int(leave.get("allocation_year") or str(leave.get("start_date", ""))[:4] or datetime.now().year)
            except (TypeError, ValueError):
                yr = datetime.now().year
            key = (leave.get("employee_id", ""), yr)
            approved_casual_used[key] = approved_casual_used.get(key, 0) + int(leave.get("casual_days", 0) or 0)

    # Migrate legacy leave requests chronologically (oldest first)
    indexed_leaves = list(enumerate(leaves))
    indexed_leaves.sort(key=lambda item: (item[1].get("submitted_at") or "", item[1].get("start_date") or ""))

    for _, leave in indexed_leaves:
        emp_id = leave.get("employee_id", "")
        emp = emp_by_id.get(emp_id)

        if "allocation_year" not in leave:
            try:
                leave["allocation_year"] = int(str(leave.get("start_date", ""))[:4])
            except (TypeError, ValueError):
                leave["allocation_year"] = datetime.now().year
            changed = True
        yr = int(leave["allocation_year"])

        days = max(int(leave.get("days", 1) or 1), 1)
        if leave.get("days") != days:
            leave["days"] = days
            changed = True

        status = (leave.get("status") or "pending_lead").lower()
        if status == "pending":
            if emp and emp.get("access_role") == "team_lead":
                leave["status"] = "pending_hr"
            else:
                leave["status"] = "pending_lead"
            changed = True

        if "assigned_team_lead_id" not in leave:
            lead_id = emp.get("team_lead_id") if (emp and emp.get("access_role") == "employee") else None
            lead_emp = emp_by_id.get(lead_id) if lead_id else None
            leave["assigned_team_lead_id"] = lead_id
            leave["assigned_team_lead_name"] = lead_emp.get("name") if lead_emp else None
            changed = True

        if "casual_days" not in leave or "yearly_days" not in leave:
            raw_type = (leave.get("leave_type") or "").lower()
            if "casual" in raw_type and "yearly" not in raw_type:
                used_c = approved_casual_used.get((emp_id, yr), 0)
                avail_c = max(CASUAL_LEAVE_YEARLY_CAP - used_c, 0)
                c_days = min(days, avail_c)
                y_days = days - c_days
                if (leave.get("status") or "").lower() == "approved":
                    approved_casual_used[(emp_id, yr)] = used_c + c_days
            else:
                c_days = 0
                y_days = days
            leave["casual_days"] = c_days
            leave["yearly_days"] = y_days
            leave["leave_type"] = _format_leave_type(c_days, y_days)
            changed = True

        for field, default in (
            ("lead_reviewer_id", None),
            ("lead_reviewed_by", None),
            ("lead_reviewed_at", None),
            ("lead_remarks", ""),
            ("hr_type_override", False),
            ("conversion_history", []),
        ):
            if field not in leave:
                leave[field] = default if not isinstance(default, list) else []
                changed = True

    # Ensure every employee has normalized 2-type leave_balance synced with requests
    current_year = datetime.now().year
    for emp in employees:
        bal = emp.get("leave_balance") or {}
        if changed or "yearly" not in bal or "casual_quota" not in bal or "sick" in bal or "paid" in bal:
            _recalculate_employee_balance_in_data(data, emp.get("id"), year=current_year)
            changed = True

    return changed

# ============ Position Functions ============

def save_position(title: str, description: str) -> str:
    """Creates a new position and returns its ID"""
    if _use_postgres():
        pos_id = str(uuid.uuid4())
        now = datetime.now().isoformat()
        database.execute_query(
            "INSERT INTO positions (id, title, description, created_at, updated_at) VALUES (%s, %s, %s, %s, %s);",
            (pos_id, title, description, now, now)
        )
        return pos_id
    data = _load_data()
    position_id = str(uuid.uuid4())
    position = {
        "id": position_id,
        "title": title,
        "description": description
    }
    data["positions"].append(position)
    _save_data(data)
    return position_id

def get_all_positions() -> List[Dict]:
    """Returns all positions"""
    if _use_postgres():
        rows = database.execute_query("SELECT * FROM positions ORDER BY created_at ASC;", fetch="all")
        res = []
        for r in rows:
            d = dict(r)
            if isinstance(d.get("created_at"), (datetime, date)):
                d["created_at"] = d["created_at"].isoformat()
            if isinstance(d.get("updated_at"), (datetime, date)):
                d["updated_at"] = d["updated_at"].isoformat()
            res.append(d)
        return res
    data = _load_data()
    return data.get("positions", [])

def get_position(position_id: str) -> Optional[Dict]:
    """Returns a single position by ID"""
    if not position_id:
        return None
    if _use_postgres():
        row = database.execute_query("SELECT * FROM positions WHERE id = %s;", (position_id,), fetch="one")
        if not row:
            return None
        d = dict(row)
        if isinstance(d.get("created_at"), (datetime, date)):
            d["created_at"] = d["created_at"].isoformat()
        if isinstance(d.get("updated_at"), (datetime, date)):
            d["updated_at"] = d["updated_at"].isoformat()
        return d
    data = _load_data()
    positions = data.get("positions", [])
    return next((p for p in positions if p["id"] == position_id), None)

def update_position(position_id: str, title: str, description: str):
    """Updates an existing position"""
    if _use_postgres():
        database.execute_query(
            "UPDATE positions SET title = %s, description = %s, updated_at = CURRENT_TIMESTAMP WHERE id = %s;",
            (title, description, position_id)
        )
        return
    data = _load_data()
    for p in data["positions"]:
        if p["id"] == position_id:
            p["title"] = title
            p["description"] = description
            break
    _save_data(data)

def delete_position(position_id: str):
    """Deletes a position and all its associated candidates"""
    if _use_postgres():
        database.execute_query("DELETE FROM candidates WHERE position_id = %s;", (position_id,))
        database.execute_query("DELETE FROM positions WHERE id = %s;", (position_id,))
        return
    data = _load_data()
    # Remove position
    data["positions"] = [p for p in data["positions"] if p["id"] != position_id]
    # Cascade delete candidates
    data["candidates"] = [c for c in data["candidates"] if c.get("position_id") != position_id]
    _save_data(data)

def get_candidates_by_position(position_id: str) -> List[Dict]:
    """Returns all candidates for a specific position"""
    if _use_postgres():
        rows = database.execute_query(
            "SELECT * FROM candidates WHERE position_id = %s ORDER BY final_rank_score DESC, created_at DESC;",
            (position_id,),
            fetch="all"
        )
        return [_format_candidate_from_db(r) for r in rows]
    data = _load_data()
    return [c for c in data.get("candidates", []) if c.get("position_id") == position_id]

# ============ Legacy Job Description (for migration) ============

def save_job_description(text: str):
    if _use_postgres():
        database.execute_query(
            "INSERT INTO app_settings (key, value, updated_at) VALUES ('job_description_text', %s, CURRENT_TIMESTAMP) "
            "ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = CURRENT_TIMESTAMP;",
            (text,)
        )
        return
    data = _load_data()
    data["job_description_text"] = text
    _save_data(data)

def get_job_description() -> str:
    if _use_postgres():
        row = database.execute_query("SELECT value FROM app_settings WHERE key = 'job_description_text';", fetch="one")
        return row["value"] if row and row.get("value") else ""
    data = _load_data()
    return data.get("job_description_text", "")

# ============ Candidate Functions ============

def save_candidate(candidate_data: Dict) -> str:
    """Saves a candidate and returns their ID"""
    if _use_postgres():
        return _save_candidate_to_db(candidate_data)
    
    data = _load_data()
    
    # Generate ID if not present
    if "id" not in candidate_data:
        candidate_data["id"] = str(uuid.uuid4())
    
    # Add created_at timestamp for new candidates
    if "created_at" not in candidate_data:
        candidate_data["created_at"] = datetime.now().isoformat()
    
    # Default status to pending if not set
    if "status" not in candidate_data:
        candidate_data["status"] = "pending"
        
    # Check if candidate already exists (update)
    candidates = data.get("candidates", [])
    existing_index = next((index for (index, d) in enumerate(candidates) if d["id"] == candidate_data["id"]), None)
    
    if existing_index is not None:
        candidates[existing_index] = candidate_data
    else:
        candidates.append(candidate_data)
    
    data["candidates"] = candidates
    _save_data(data)
    return candidate_data["id"]

def get_all_candidates() -> List[Dict]:
    if _use_postgres():
        rows = database.execute_query(
            "SELECT * FROM candidates ORDER BY final_rank_score DESC, created_at DESC;",
            fetch="all"
        )
        return [_format_candidate_from_db(r) for r in rows]
    data = _load_data()
    return data.get("candidates", [])

get_candidates = get_all_candidates
get_positions = get_all_positions

def get_candidate(candidate_id: str) -> Optional[Dict]:
    if not candidate_id:
        return None
    if _use_postgres():
        row = database.execute_query("SELECT * FROM candidates WHERE id = %s;", (candidate_id,), fetch="one")
        if not row:
            return None
        return _format_candidate_from_db(row, include_timeline=True)
    data = _load_data()
    candidates = data.get("candidates", [])
    return next((c for c in candidates if c["id"] == candidate_id), None)

def delete_candidate(candidate_id: str):
    """Deletes a candidate by ID"""
    if _use_postgres():
        database.execute_query("DELETE FROM candidates WHERE id = %s;", (candidate_id,))
        return
    data = _load_data()
    candidates = data.get("candidates", [])
    data["candidates"] = [c for c in candidates if c["id"] != candidate_id]
    _save_data(data)

def update_candidate_status(candidate_id: str, status: str):
    """Updates the status of a candidate"""
    if _use_postgres():
        database.execute_query(
            "UPDATE candidates SET status = %s, updated_at = CURRENT_TIMESTAMP WHERE id = %s;",
            (status, candidate_id)
        )
        return
    data = _load_data()
    candidates = data.get("candidates", [])
    for c in candidates:
        if c["id"] == candidate_id:
            c["status"] = status
            break
    _save_data(data)

def get_overview_stats() -> Dict:
    """Returns aggregated stats for the Overview Dashboard"""
    candidates = get_all_candidates()
    positions = get_all_positions()
    
    now = datetime.now()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    
    # Count stats
    total_candidates = len(candidates)
    total_positions = len(positions)
    
    # Status counts
    pending_count = 0
    accepted_count = 0
    rejected_count = 0
    today_applicants = 0
    hires_this_month = 0
    
    for c in candidates:
        status = c.get("status", "pending")
        
        if status == "pending" or status == "":
            pending_count += 1
        elif status == "accepted":
            accepted_count += 1
        elif status == "rejected":
            rejected_count += 1
        
        # Check created_at for today's applicants
        created_at_str = c.get("created_at")
        if created_at_str:
            try:
                if isinstance(created_at_str, str):
                    created_at = datetime.fromisoformat(created_at_str.replace("Z", "+00:00")).replace(tzinfo=None)
                else:
                    created_at = created_at_str
                if created_at >= today_start:
                    today_applicants += 1
                if status == "accepted" and created_at >= month_start:
                    hires_this_month += 1
            except (ValueError, TypeError):
                pass
    
    reschedule_requests_count = sum(1 for c in candidates if c.get("interview", {}).get("status") == "reschedule_requested")
    scheduled_interviews_count = sum(1 for c in candidates if c.get("interview", {}).get("status") in ["confirmed", "pending_candidate_response"])

    return {
        "total_candidates": total_candidates,
        "total_positions": total_positions,
        "today_applicants": today_applicants,
        "hires_this_month": hires_this_month,
        "pending_count": pending_count,
        "accepted_count": accepted_count,
        "rejected_count": rejected_count,
        "reschedule_requests_count": reschedule_requests_count,
        "scheduled_interviews_count": scheduled_interviews_count
    }

# ============ User Functions ============

def create_user(username, password, name, email):
    """Creates a new user"""
    if _use_postgres():
        existing = database.execute_query("SELECT id FROM users WHERE username = %s;", (username,), fetch="one")
        if existing:
            return None
        user_id = str(uuid.uuid4())
        now = datetime.now().isoformat()
        database.execute_query(
            "INSERT INTO users (id, username, password, name, email, created_at, updated_at) VALUES (%s, %s, %s, %s, %s, %s, %s);",
            (user_id, username, password, name, email, now, now)
        )
        return user_id

    data = _load_data()
    # Check if username exists
    if any(u['username'] == username for u in data.get('users', [])):
        return None
    
    user_id = str(uuid.uuid4())
    user = {
        "id": user_id,
        "username": username,
        "password": password,
        "name": name,
        "email": email,
        "created_at": datetime.now().isoformat()
    }
    data["users"].append(user)
    _save_data(data)
    return user_id

def get_user_by_username(username):
    """Returns user by username"""
    if _use_postgres():
        row = database.execute_query("SELECT * FROM users WHERE username = %s;", (username,), fetch="one")
        if not row:
            return None
        d = dict(row)
        for ts_col in ("created_at", "updated_at"):
            if isinstance(d.get(ts_col), (datetime, date)):
                d[ts_col] = d[ts_col].isoformat()
        return d
    data = _load_data()
    return next((u for u in data.get('users', []) if u['username'] == username), None)

def get_user_by_id(user_id):
    """Returns user by ID"""
    if not user_id:
        return None
    if _use_postgres():
        row = database.execute_query("SELECT * FROM users WHERE id = %s;", (user_id,), fetch="one")
        if not row:
            return None
        d = dict(row)
        for ts_col in ("created_at", "updated_at"):
            if isinstance(d.get(ts_col), (datetime, date)):
                d[ts_col] = d[ts_col].isoformat()
        return d
    data = _load_data()
    return next((u for u in data.get('users', []) if u['id'] == user_id), None)

def get_candidates_by_user(user_id):
    """Returns all candidates/applications for a specific user"""
    if not user_id:
        return []
    if _use_postgres():
        rows = database.execute_query(
            "SELECT * FROM candidates WHERE user_id = %s ORDER BY created_at DESC;",
            (user_id,),
            fetch="all"
        )
        return [_format_candidate_from_db(r) for r in rows]
    data = _load_data()
    return [c for c in data.get('candidates', []) if c.get('user_id') == user_id]

# ============ Interview & Scheduling Functions ============

def schedule_interview(candidate_id: str, date: str, time: str, meeting_link: str = "", hr_note: str = "", round_title: str = "Interview Round") -> Optional[Dict]:
    """Sets candidate status to accepted and attaches scheduled interview details."""
    from datetime import datetime
    now_iso = datetime.now().isoformat()

    if _use_postgres():
        candidate = get_candidate(candidate_id)
        if not candidate:
            return None
        candidate["status"] = "accepted"
        interview = {
            "status": "pending_candidate_response",
            "date": date,
            "time": time,
            "round_title": round_title,
            "meeting_link": meeting_link,
            "hr_note": hr_note,
            "scheduled_at": now_iso,
            "reschedule_request": None,
            "history": candidate.get("interview", {}).get("history", []) if isinstance(candidate.get("interview"), dict) else []
        }
        interview["history"].append({
            "action": "scheduled_by_hr",
            "date": date,
            "time": time,
            "timestamp": now_iso,
            "note": hr_note
        })
        candidate["interview"] = interview
        if "interview_rounds" not in candidate or not isinstance(candidate["interview_rounds"], list):
            candidate["interview_rounds"] = []
        candidate["interview_rounds"].append({
            "round_title": round_title,
            "date": date,
            "time": time,
            "meeting_link": meeting_link,
            "hr_note": hr_note,
            "status": "pending_candidate_response",
            "scheduled_at": now_iso
        })
        candidate["stage"] = round_title
        save_candidate(candidate)

        add_candidate_timeline_event(
            candidate_id=candidate_id,
            sender="hr",
            sender_name="HR Admin",
            event_type="interview",
            content=f"Scheduled {round_title} for {date} at {time}." + (f" Meeting link: {meeting_link}" if meeting_link else ""),
            metadata={"date": date, "time": time, "round_title": round_title, "meeting_link": meeting_link, "hr_note": hr_note}
        )

        recip_id = candidate.get("user_id") or candidate["id"]
        pos = get_position(candidate.get("position_id"))
        pos_title = pos.get("title") if pos else "Position"
        add_notification(
            recipient_type="candidate",
            recipient_id=recip_id,
            title="🎉 Interview Invitation",
            message=f"You have been invited for an interview for {pos_title} on {date} at {time}.",
            link="/applicant_dashboard" if candidate.get("user_id") else "/application_status",
            notification_type="interview_invite"
        )
        return candidate

    data = _load_data()
    candidates = data.get("candidates", [])
    candidate = next((c for c in candidates if c["id"] == candidate_id), None)
    if not candidate:
        return None

    candidate["status"] = "accepted"
    
    interview = {
        "status": "pending_candidate_response",
        "date": date,
        "time": time,
        "round_title": round_title,
        "meeting_link": meeting_link,
        "hr_note": hr_note,
        "scheduled_at": now_iso,
        "reschedule_request": None,
        "history": candidate.get("interview", {}).get("history", [])
    }
    interview["history"].append({
        "action": "scheduled_by_hr",
        "date": date,
        "time": time,
        "timestamp": now_iso,
        "note": hr_note
    })
    candidate["interview"] = interview
    if "interview_rounds" not in candidate:
        candidate["interview_rounds"] = []
    candidate["interview_rounds"].append({
        "round_title": round_title,
        "date": date,
        "time": time,
        "meeting_link": meeting_link,
        "hr_note": hr_note,
        "status": "pending_candidate_response",
        "scheduled_at": now_iso
    })
    candidate["stage"] = round_title
    _save_data(data)

    # Add timeline event
    add_candidate_timeline_event(
        candidate_id=candidate_id,
        sender="hr",
        sender_name="HR Admin",
        event_type="interview",
        content=f"Scheduled {round_title} for {date} at {time}." + (f" Meeting link: {meeting_link}" if meeting_link else ""),
        metadata={"date": date, "time": time, "round_title": round_title, "meeting_link": meeting_link, "hr_note": hr_note}
    )

    # In-app notification for candidate
    recip_id = candidate.get("user_id") or candidate["id"]
    pos = get_position(candidate.get("position_id"))
    pos_title = pos.get("title") if pos else "Position"
    add_notification(
        recipient_type="candidate",
        recipient_id=recip_id,
        title="🎉 Interview Invitation",
        message=f"You have been invited for an interview for {pos_title} on {date} at {time}.",
        link="/applicant_dashboard" if candidate.get("user_id") else "/application_status",
        notification_type="interview_invite"
    )

    return candidate

def candidate_respond_interview(candidate_id: str, action: str, proposed_date: str = None, proposed_time: str = None, reason: str = "") -> Optional[Dict]:
    """
    Handles candidate's response to an interview invite.
    action: 'accept' | 'decline' | 'reschedule'
    """
    from datetime import datetime
    now_iso = datetime.now().isoformat()

    if _use_postgres():
        candidate = get_candidate(candidate_id)
        if not candidate or "interview" not in candidate:
            return None

        interview = candidate["interview"]
        pos = get_position(candidate.get("position_id"))
        pos_title = pos.get("title") if pos else "Position"
        cand_name = candidate.get("name", "Candidate")

        if action in ["accept", "confirm"]:
            interview["status"] = "confirmed"
            if "history" not in interview or not isinstance(interview["history"], list):
                interview["history"] = []
            interview["history"].append({
                "action": "confirmed_by_candidate",
                "timestamp": now_iso
            })
            if "interview_rounds" in candidate and candidate["interview_rounds"]:
                candidate["interview_rounds"][-1]["status"] = "confirmed"
            save_candidate(candidate)
            add_candidate_timeline_event(
                candidate_id=candidate_id,
                sender="candidate",
                sender_name=cand_name,
                event_type="message",
                content=f"Accepted and confirmed interview slot for {interview.get('date')} at {interview.get('time')}."
            )
            add_notification(
                recipient_type="hr",
                recipient_id="hr_admin",
                title="✅ Interview Confirmed",
                message=f"{cand_name} confirmed their interview for {pos_title} ({interview.get('date')} at {interview.get('time')}).",
                link=f"/candidate?id={candidate_id}",
                notification_type="confirmed"
            )

        elif action in ["decline", "reject"]:
            interview["status"] = "declined"
            if "history" not in interview or not isinstance(interview["history"], list):
                interview["history"] = []
            interview["history"].append({
                "action": "declined_by_candidate",
                "reason": reason,
                "timestamp": now_iso
            })
            if "interview_rounds" in candidate and candidate["interview_rounds"]:
                candidate["interview_rounds"][-1]["status"] = "declined"
            save_candidate(candidate)
            add_candidate_timeline_event(
                candidate_id=candidate_id,
                sender="candidate",
                sender_name=cand_name,
                event_type="message",
                content=f"Declined interview invitation." + (f" Reason: {reason}" if reason else "")
            )
            add_notification(
                recipient_type="hr",
                recipient_id="hr_admin",
                title="❌ Interview Declined",
                message=f"{cand_name} declined the interview for {pos_title}. Reason: {reason or 'No reason provided'}",
                link=f"/candidate?id={candidate_id}",
                notification_type="declined"
            )

        elif action == "reschedule":
            interview["status"] = "reschedule_requested"
            interview["reschedule_request"] = {
                "proposed_date": proposed_date,
                "proposed_time": proposed_time,
                "reason": reason,
                "requested_at": now_iso
            }
            if "history" not in interview or not isinstance(interview["history"], list):
                interview["history"] = []
            interview["history"].append({
                "action": "reschedule_requested",
                "proposed_date": proposed_date,
                "proposed_time": proposed_time,
                "reason": reason,
                "timestamp": now_iso
            })
            if "interview_rounds" in candidate and candidate["interview_rounds"]:
                candidate["interview_rounds"][-1]["status"] = "reschedule_requested"
            save_candidate(candidate)
            add_candidate_timeline_event(
                candidate_id=candidate_id,
                sender="candidate",
                sender_name=cand_name,
                event_type="reschedule",
                content=f"Requested to reschedule to {proposed_date} at {proposed_time}." + (f" Reason: {reason}" if reason else ""),
                metadata={"proposed_date": proposed_date, "proposed_time": proposed_time, "reason": reason}
            )
            add_notification(
                recipient_type="hr",
                recipient_id="hr_admin",
                title="⚠️ Reschedule Requested",
                message=f"{cand_name} requested to reschedule {pos_title} to {proposed_date} at {proposed_time}. Reason: {reason or 'N/A'}",
                link=f"/candidate?id={candidate_id}",
                notification_type="reschedule_requested"
            )

        return candidate

    data = _load_data()
    candidates = data.get("candidates", [])
    candidate = next((c for c in candidates if c["id"] == candidate_id), None)
    if not candidate or "interview" not in candidate:
        return None

    interview = candidate["interview"]
    pos = get_position(candidate.get("position_id"))
    pos_title = pos.get("title") if pos else "Position"
    cand_name = candidate.get("name", "Candidate")

    if action in ["accept", "confirm"]:
        interview["status"] = "confirmed"
        interview["history"].append({
            "action": "confirmed_by_candidate",
            "timestamp": now_iso
        })
        if "interview_rounds" in candidate and candidate["interview_rounds"]:
            candidate["interview_rounds"][-1]["status"] = "confirmed"
        _save_data(data)
        add_candidate_timeline_event(
            candidate_id=candidate_id,
            sender="candidate",
            sender_name=cand_name,
            event_type="message",
            content=f"Accepted and confirmed interview slot for {interview.get('date')} at {interview.get('time')}."
        )
        add_notification(
            recipient_type="hr",
            recipient_id="hr_admin",
            title="✅ Interview Confirmed",
            message=f"{cand_name} confirmed their interview for {pos_title} ({interview.get('date')} at {interview.get('time')}).",
            link=f"/candidate?id={candidate_id}",
            notification_type="confirmed"
        )

    elif action in ["decline", "reject"]:
        interview["status"] = "declined"
        interview["history"].append({
            "action": "declined_by_candidate",
            "reason": reason,
            "timestamp": now_iso
        })
        if "interview_rounds" in candidate and candidate["interview_rounds"]:
            candidate["interview_rounds"][-1]["status"] = "declined"
        _save_data(data)
        add_candidate_timeline_event(
            candidate_id=candidate_id,
            sender="candidate",
            sender_name=cand_name,
            event_type="message",
            content=f"Declined interview invitation." + (f" Reason: {reason}" if reason else "")
        )
        add_notification(
            recipient_type="hr",
            recipient_id="hr_admin",
            title="❌ Interview Declined",
            message=f"{cand_name} declined the interview for {pos_title}. Reason: {reason or 'No reason provided'}",
            link=f"/candidate?id={candidate_id}",
            notification_type="declined"
        )

    elif action == "reschedule":
        interview["status"] = "reschedule_requested"
        interview["reschedule_request"] = {
            "proposed_date": proposed_date,
            "proposed_time": proposed_time,
            "reason": reason,
            "requested_at": now_iso
        }
        interview["history"].append({
            "action": "reschedule_requested",
            "proposed_date": proposed_date,
            "proposed_time": proposed_time,
            "reason": reason,
            "timestamp": now_iso
        })
        if "interview_rounds" in candidate and candidate["interview_rounds"]:
            candidate["interview_rounds"][-1]["status"] = "reschedule_requested"
        _save_data(data)
        add_candidate_timeline_event(
            candidate_id=candidate_id,
            sender="candidate",
            sender_name=cand_name,
            event_type="reschedule",
            content=f"Requested to reschedule to {proposed_date} at {proposed_time}." + (f" Reason: {reason}" if reason else ""),
            metadata={"proposed_date": proposed_date, "proposed_time": proposed_time, "reason": reason}
        )
        add_notification(
            recipient_type="hr",
            recipient_id="hr_admin",
            title="⚠️ Reschedule Requested",
            message=f"{cand_name} requested to reschedule {pos_title} to {proposed_date} at {proposed_time}. Reason: {reason or 'N/A'}",
            link=f"/candidate?id={candidate_id}",
            notification_type="reschedule_requested"
        )

    return candidate

def hr_resolve_reschedule(candidate_id: str, decision: str, new_date: str = None, new_time: str = None, hr_note: str = "") -> Optional[Dict]:
    """
    HR handles candidate reschedule request:
    decision: 'approve' (accepts candidate's suggested slot) | 'counter' (proposes new slot)
    """
    from datetime import datetime
    now_iso = datetime.now().isoformat()

    if _use_postgres():
        candidate = get_candidate(candidate_id)
        if not candidate or "interview" not in candidate:
            return None

        interview = candidate["interview"]
        pos = get_position(candidate.get("position_id"))
        pos_title = pos.get("title") if pos else "Position"
        recip_id = candidate.get("user_id") or candidate["id"]

        if decision == "approve":
            req = interview.get("reschedule_request") or {}
            proposed_date = req.get("proposed_date", interview.get("date"))
            proposed_time = req.get("proposed_time", interview.get("time"))
            interview["date"] = proposed_date
            interview["time"] = proposed_time
            interview["status"] = "confirmed"
            interview["reschedule_request"] = None
            if "history" not in interview or not isinstance(interview["history"], list):
                interview["history"] = []
            interview["history"].append({
                "action": "reschedule_approved_by_hr",
                "date": proposed_date,
                "time": proposed_time,
                "note": hr_note,
                "timestamp": now_iso
            })
            if "interview_rounds" in candidate and candidate["interview_rounds"]:
                candidate["interview_rounds"][-1]["status"] = "confirmed"
                candidate["interview_rounds"][-1]["date"] = proposed_date
                candidate["interview_rounds"][-1]["time"] = proposed_time
            save_candidate(candidate)

            add_candidate_timeline_event(
                candidate_id=candidate_id,
                sender="hr",
                sender_name="HR Admin",
                event_type="reschedule",
                content=f"Approved reschedule request for {proposed_date} at {proposed_time}." + (f" Note: {hr_note}" if hr_note else "")
            )

            add_notification(
                recipient_type="candidate",
                recipient_id=recip_id,
                title="✅ Reschedule Approved",
                message=f"Your proposed interview time for {pos_title} ({proposed_date} at {proposed_time}) has been approved!",
                link="/applicant_dashboard" if candidate.get("user_id") else "/application_status",
                notification_type="confirmed"
            )

        elif decision == "counter":
            interview["date"] = new_date or interview.get("date")
            interview["time"] = new_time or interview.get("time")
            if hr_note:
                interview["hr_note"] = hr_note
            interview["status"] = "pending_candidate_response"
            interview["reschedule_request"] = None
            if "history" not in interview or not isinstance(interview["history"], list):
                interview["history"] = []
            interview["history"].append({
                "action": "counter_schedule_by_hr",
                "date": interview["date"],
                "time": interview["time"],
                "note": hr_note,
                "timestamp": now_iso
            })
            if "interview_rounds" in candidate and candidate["interview_rounds"]:
                candidate["interview_rounds"][-1]["status"] = "pending_candidate_response"
                candidate["interview_rounds"][-1]["date"] = interview["date"]
                candidate["interview_rounds"][-1]["time"] = interview["time"]
            save_candidate(candidate)

            add_candidate_timeline_event(
                candidate_id=candidate_id,
                sender="hr",
                sender_name="HR Admin",
                event_type="interview",
                content=f"Proposed new interview slot: {new_date} at {new_time}." + (f" Note: {hr_note}" if hr_note else "")
            )

            add_notification(
                recipient_type="candidate",
                recipient_id=recip_id,
                title="🔄 Updated Interview Time",
                message=f"HR suggested a new interview slot for {pos_title}: {interview['date']} at {interview['time']}.",
                link="/applicant_dashboard" if candidate.get("user_id") else "/application_status",
                notification_type="interview_invite"
            )

        return candidate

    data = _load_data()
    candidates = data.get("candidates", [])
    candidate = next((c for c in candidates if c["id"] == candidate_id), None)
    if not candidate or "interview" not in candidate:
        return None

    interview = candidate["interview"]
    pos = get_position(candidate.get("position_id"))
    pos_title = pos.get("title") if pos else "Position"
    recip_id = candidate.get("user_id") or candidate["id"]

    if decision == "approve":
        req = interview.get("reschedule_request") or {}
        proposed_date = req.get("proposed_date", interview.get("date"))
        proposed_time = req.get("proposed_time", interview.get("time"))
        interview["date"] = proposed_date
        interview["time"] = proposed_time
        interview["status"] = "confirmed"
        interview["reschedule_request"] = None
        interview["history"].append({
            "action": "reschedule_approved_by_hr",
            "date": proposed_date,
            "time": proposed_time,
            "note": hr_note,
            "timestamp": now_iso
        })
        if "interview_rounds" in candidate and candidate["interview_rounds"]:
            candidate["interview_rounds"][-1]["status"] = "confirmed"
            candidate["interview_rounds"][-1]["date"] = proposed_date
            candidate["interview_rounds"][-1]["time"] = proposed_time
        _save_data(data)

        add_candidate_timeline_event(
            candidate_id=candidate_id,
            sender="hr",
            sender_name="HR Admin",
            event_type="reschedule",
            content=f"Approved reschedule request for {proposed_date} at {proposed_time}." + (f" Note: {hr_note}" if hr_note else "")
        )

        add_notification(
            recipient_type="candidate",
            recipient_id=recip_id,
            title="✅ Reschedule Approved",
            message=f"Your proposed interview time for {pos_title} ({proposed_date} at {proposed_time}) has been approved!",
            link="/applicant_dashboard" if candidate.get("user_id") else "/application_status",
            notification_type="confirmed"
        )

    elif decision == "counter":
        interview["date"] = new_date or interview.get("date")
        interview["time"] = new_time or interview.get("time")
        if hr_note:
            interview["hr_note"] = hr_note
        interview["status"] = "pending_candidate_response"
        interview["reschedule_request"] = None
        interview["history"].append({
            "action": "counter_schedule_by_hr",
            "date": interview["date"],
            "time": interview["time"],
            "note": hr_note,
            "timestamp": now_iso
        })
        if "interview_rounds" in candidate and candidate["interview_rounds"]:
            candidate["interview_rounds"][-1]["status"] = "pending_candidate_response"
            candidate["interview_rounds"][-1]["date"] = interview["date"]
            candidate["interview_rounds"][-1]["time"] = interview["time"]
        _save_data(data)

        add_candidate_timeline_event(
            candidate_id=candidate_id,
            sender="hr",
            sender_name="HR Admin",
            event_type="interview",
            content=f"Proposed new interview slot: {new_date} at {new_time}." + (f" Note: {hr_note}" if hr_note else "")
        )

        add_notification(
            recipient_type="candidate",
            recipient_id=recip_id,
            title="🔄 Updated Interview Time",
            message=f"HR suggested a new interview slot for {pos_title}: {interview['date']} at {interview['time']}.",
            link="/applicant_dashboard" if candidate.get("user_id") else "/application_status",
            notification_type="interview_invite"
        )

    return candidate

# ============ Candidate Timeline & Stage Tracking Functions ============

def add_candidate_timeline_event(candidate_id: str, sender: str, sender_name: str, event_type: str, content: str, metadata: dict = None) -> Optional[Dict]:
    """Appends an event/message to the candidate's activity and chat timeline."""
    from datetime import datetime
    now_iso = datetime.now().isoformat()

    if _use_postgres():
        cand = database.execute_query("SELECT id FROM candidates WHERE id = %s;", (candidate_id,), fetch="one")
        if not cand:
            return None
        event_id = str(uuid.uuid4())
        meta = metadata or {}
        att = meta.get("attachments") or []
        database.execute_query(
            """
            INSERT INTO candidate_timeline (
                id, candidate_id, sender, sender_name, type, content, metadata, attachments, timestamp, created_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s);
            """,
            (
                event_id,
                candidate_id,
                sender,
                sender_name,
                event_type,
                content,
                database.to_json(meta),
                database.to_json(att),
                now_iso,
                now_iso
            )
        )
        return {
            "id": event_id,
            "sender": sender,
            "sender_name": sender_name,
            "type": event_type,
            "content": content,
            "metadata": meta,
            "attachments": att,
            "timestamp": now_iso
        }

    data = _load_data()
    candidates = data.get("candidates", [])
    candidate = next((c for c in candidates if c["id"] == candidate_id), None)
    if not candidate:
        return None

    if "timeline" not in candidate:
        candidate["timeline"] = []

    event = {
        "id": str(uuid.uuid4()),
        "sender": sender,
        "sender_name": sender_name,
        "type": event_type,
        "content": content,
        "metadata": metadata or {},
        "timestamp": now_iso
    }
    candidate["timeline"].append(event)
    _save_data(data)
    return event

def get_candidate_timeline(candidate_id: str) -> List[Dict]:
    """Retrieves full activity & message thread for a candidate, auto-generating history if empty."""
    if _use_postgres():
        return _get_candidate_timeline_from_db(candidate_id, auto_generate=True)

    data = _load_data()
    candidates = data.get("candidates", [])
    candidate = next((c for c in candidates if c["id"] == candidate_id), None)
    if not candidate:
        return []

    timeline = candidate.get("timeline")
    if timeline is not None and len(timeline) > 0:
        return timeline

    synthesized = _synthesize_candidate_timeline(candidate)
    candidate["timeline"] = synthesized
    _save_data(data)
    return synthesized

def update_candidate_stage(candidate_id: str, new_stage: str) -> Optional[Dict]:
    """Updates candidate hiring stage (e.g. Applied, Round 1, Round 2, Round 3, Offer, Onboarding)"""
    if _use_postgres():
        candidate = get_candidate(candidate_id)
        if not candidate:
            return None
        old_stage = candidate.get("stage", "Applied")
        candidate["stage"] = new_stage
        database.execute_query(
            "UPDATE candidates SET stage = %s, updated_at = CURRENT_TIMESTAMP WHERE id = %s;",
            (new_stage, candidate_id)
        )
        add_candidate_timeline_event(
            candidate_id=candidate_id,
            sender="hr",
            sender_name="HR Admin",
            event_type="stage_change",
            content=f"Candidate stage advanced from '{old_stage}' to '{new_stage}'.",
            metadata={"old_stage": old_stage, "new_stage": new_stage}
        )
        recip_id = candidate.get("user_id") or candidate["id"]
        pos = get_position(candidate.get("position_id"))
        pos_title = pos.get("title", "Position") if pos else "Position"
        add_notification(
            recipient_type="candidate",
            recipient_id=recip_id,
            title=f"🚀 Stage Update: {new_stage}",
            message=f"Your application for {pos_title} has progressed to stage: {new_stage}.",
            link="/applicant_dashboard" if candidate.get("user_id") else "/application_status",
            notification_type="stage_change"
        )
        return candidate

    data = _load_data()
    candidates = data.get("candidates", [])
    candidate = next((c for c in candidates if c["id"] == candidate_id), None)
    if not candidate:
        return None

    old_stage = candidate.get("stage", "Applied")
    candidate["stage"] = new_stage
    _save_data(data)

    add_candidate_timeline_event(
        candidate_id=candidate_id,
        sender="hr",
        sender_name="HR Admin",
        event_type="stage_change",
        content=f"Candidate stage advanced from '{old_stage}' to '{new_stage}'.",
        metadata={"old_stage": old_stage, "new_stage": new_stage}
    )

    recip_id = candidate.get("user_id") or candidate["id"]
    pos = get_position(candidate.get("position_id"))
    pos_title = pos.get("title", "Position") if pos else "Position"
    add_notification(
        recipient_type="candidate",
        recipient_id=recip_id,
        title=f"🚀 Stage Update: {new_stage}",
        message=f"Your application for {pos_title} has progressed to stage: {new_stage}.",
        link="/applicant_dashboard" if candidate.get("user_id") else "/application_status",
        notification_type="stage_change"
    )

    return candidate

def get_pending_reschedules() -> List[Dict]:
    """Returns all candidates who have requested an interview reschedule awaiting HR action."""
    candidates = get_all_candidates()
    results = []
    for c in candidates:
        if c.get("interview", {}).get("status") == "reschedule_requested":
            pos = get_position(c.get("position_id"))
            c_copy = dict(c)
            c_copy["position_title"] = pos.get("title") if pos else "Unknown Position"
            results.append(c_copy)
    return results

# ============ In-App Notification Functions ============

def add_notification(recipient_type: str, recipient_id: str, title: str, message: str, link: str = "", notification_type: str = "info") -> str:
    """Adds an in-app notification to data.json or PostgreSQL."""
    if _use_postgres():
        notif_id = str(uuid.uuid4())
        now = datetime.now().isoformat()
        database.execute_query(
            """
            INSERT INTO notifications (id, recipient_type, recipient_id, title, message, link, notification_type, read, created_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, FALSE, %s);
            """,
            (notif_id, recipient_type, str(recipient_id), title, message, link, notification_type, now)
        )
        return notif_id

    data = _load_data()
    notif_id = _append_notification(
        data,
        recipient_type=recipient_type,
        recipient_id=recipient_id,
        title=title,
        message=message,
        link=link,
        notification_type=notification_type,
    )
    _save_data(data)
    return notif_id

def get_notifications(recipient_type: str = None, recipient_id: str = None, unread_only: bool = False) -> List[Dict]:
    """Fetches notifications matching filter."""
    if _use_postgres():
        where_clauses = []
        params = []
        if recipient_type:
            if recipient_type == "employee":
                where_clauses.append("recipient_type IN ('employee', 'candidate')")
            else:
                where_clauses.append("recipient_type = %s")
                params.append(recipient_type)
        if recipient_id:
            where_clauses.append("recipient_id = %s")
            params.append(str(recipient_id))
        if unread_only:
            where_clauses.append("read = FALSE")
        where_str = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""
        query = f"SELECT * FROM notifications {where_str} ORDER BY created_at DESC;"
        rows = database.execute_query(query, params if params else None, fetch="all")
        results = []
        for r in rows:
            d = dict(r)
            if isinstance(d.get("created_at"), (datetime, date)):
                d["created_at"] = d["created_at"].isoformat()
            results.append(d)
        return results

    data = _load_data()
    notifs = data.get("notifications", [])
    results = []
    for n in notifs:
        if recipient_type:
            if recipient_type == "employee":
                if n.get("recipient_type") not in ("employee", "candidate"):
                    continue
            elif n.get("recipient_type") != recipient_type:
                continue
        if recipient_id and str(n.get("recipient_id")) != str(recipient_id):
            continue
        if unread_only and n.get("read"):
            continue
        results.append(n)
    return results

def mark_notification_read(notification_id: str):
    """Marks a single notification as read."""
    if _use_postgres():
        database.execute_query("UPDATE notifications SET read = TRUE WHERE id = %s;", (notification_id,))
        return
    data = _load_data()
    for n in data.get("notifications", []):
        if n["id"] == notification_id:
            n["read"] = True
            break
    _save_data(data)

def mark_all_notifications_read(recipient_type: str = None, recipient_id: str = None):
    """Marks all notifications for recipient as read."""
    if _use_postgres():
        where_clauses = []
        params = []
        if recipient_type:
            if recipient_type == "employee":
                where_clauses.append("recipient_type IN ('employee', 'candidate')")
            else:
                where_clauses.append("recipient_type = %s")
                params.append(recipient_type)
        if recipient_id:
            where_clauses.append("recipient_id = %s")
            params.append(str(recipient_id))
        where_str = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""
        query = f"UPDATE notifications SET read = TRUE {where_str};"
        database.execute_query(query, params if params else None)
        return
    data = _load_data()
    for n in data.get("notifications", []):
        if recipient_type:
            if recipient_type == "employee":
                if n.get("recipient_type") not in ("employee", "candidate"):
                    continue
            elif n.get("recipient_type") != recipient_type:
                continue
        if recipient_id and str(n.get("recipient_id")) != str(recipient_id):
            continue
        n["read"] = True
    _save_data(data)


# ============ Phase 2: Employee Management & Self-Service ============

def _next_employee_id(employees: List[Dict]) -> str:
    """Generates next non-colliding EMP-xxxx identifier."""
    max_num = 1000
    for e in employees:
        eid = str(e.get("id", ""))
        if eid.startswith("EMP-"):
            try:
                max_num = max(max_num, int(eid.split("-", 1)[1]))
            except ValueError:
                pass
    return f"EMP-{max_num + 1}"

def get_team_leads() -> List[Dict]:
    """Returns all employees with access_role == 'team_lead'."""
    data = _load_data()
    return [e for e in data.get("employees", []) if e.get("access_role") == "team_lead"]

def get_team_members(team_lead_id: str) -> List[Dict]:
    """Returns all employees assigned to a specific Team Lead."""
    if not team_lead_id:
        return []
    data = _load_data()
    return [
        e for e in data.get("employees", [])
        if e.get("team_lead_id") == team_lead_id and e.get("id") != team_lead_id
    ]

def get_all_employees() -> List[Dict]:
    """Returns all active and current employees."""
    data = _load_data()
    return data.get("employees", [])

def get_employee(employee_id: str) -> Optional[Dict]:
    """Finds an employee by employee ID (e.g. EMP-1001) or UUID."""
    data = _load_data()
    for emp in data.get("employees", []):
        if emp.get("id") == employee_id:
            return emp
    return None

def get_employee_by_email(email: str) -> Optional[Dict]:
    """Finds an employee by email address (case-insensitive)."""
    if not email:
        return None
    data = _load_data()
    email_clean = email.strip().lower()
    for emp in data.get("employees", []):
        if emp.get("email", "").strip().lower() == email_clean:
            return emp
    return None

def get_employee_by_user_id(user_id: str) -> Optional[Dict]:
    """Finds an employee linked to a user account ID."""
    if not user_id:
        return None
    data = _load_data()
    for emp in data.get("employees", []):
        if str(emp.get("user_id")) == str(user_id):
            return emp
    return None

def _normalize_team_lead_assignment(data: Dict, emp_id: str, access_role: str, team_lead_id: Optional[str]) -> Optional[str]:
    """Validates and normalizes team_lead_id for an employee."""
    if access_role == "team_lead":
        return None
    if not team_lead_id:
        return None
    clean_lead_id = str(team_lead_id).strip()
    if not clean_lead_id or clean_lead_id == emp_id:
        return None
    lead_emp = next((e for e in data.get("employees", []) if e.get("id") == clean_lead_id), None)
    if not lead_emp or lead_emp.get("access_role") != "team_lead":
        raise ValueError(f"Assigned Team Lead ({clean_lead_id}) must be an active employee with Team Lead role.")
    return clean_lead_id

def _validate_leave_quotas(
    quota_in: Optional[Dict],
    fallback_casual: int = CASUAL_LEAVE_YEARLY_CAP,
    fallback_yearly: int = DEFAULT_YEARLY_LEAVE_QUOTA,
) -> Dict[str, int]:
    """Validates annual casual (0..12) and yearly (>=0) leave quotas."""
    q = quota_in or {}
    try:
        casual_q = int(q.get("casual", fallback_casual))
        yearly_q = int(q.get("yearly", fallback_yearly))
    except (TypeError, ValueError):
        raise ValueError("Leave quotas must be valid whole numbers.")
    if casual_q < 0 or yearly_q < 0:
        raise ValueError("Leave quotas cannot be negative.")
    if casual_q > CASUAL_LEAVE_YEARLY_CAP:
        raise ValueError(f"Casual leave cannot exceed {CASUAL_LEAVE_YEARLY_CAP} days per year.")
    return {"casual": casual_q, "yearly": yearly_q}

def save_employee(emp_data: Dict) -> str:
    """Creates a new employee record and returns its ID."""
    data = _load_data()
    if "employees" not in data:
        data["employees"] = []

    if not emp_data.get("id"):
        emp_data["id"] = _next_employee_id(data["employees"])

    if "created_at" not in emp_data:
        emp_data["created_at"] = datetime.now().isoformat()
    if "status" not in emp_data:
        emp_data["status"] = "Active"
    if "department" not in emp_data:
        emp_data["department"] = "Engineering"
    if "date_of_joining" not in emp_data:
        emp_data["date_of_joining"] = date.today().isoformat()

    access_role = emp_data.get("access_role", "employee")
    if access_role not in VALID_ACCESS_ROLES:
        access_role = "employee"
    emp_data["access_role"] = access_role
    emp_data["team_lead_id"] = _normalize_team_lead_assignment(
        data, emp_data["id"], access_role, emp_data.get("team_lead_id")
    )

    emp_data["leave_quota"] = _validate_leave_quotas(emp_data.get("leave_quota"))

    # Default salary structure
    if "salary" not in emp_data or not isinstance(emp_data["salary"], dict):
        emp_data["salary"] = {
            "base": 80000,
            "allowances": 15000,
            "deductions": 5000,
            "net": 90000,
            "currency": "$",
            "payment_cycle": "Monthly",
            "status": "Paid",
            "last_paid_date": date.today().strftime("%Y-%m-01")
        }
    else:
        sal = emp_data["salary"]
        base = float(sal.get("base", 0))
        allowances = float(sal.get("allowances", 0))
        deductions = float(sal.get("deductions", 0))
        sal["net"] = base + allowances - deductions
        if "currency" not in sal:
            sal["currency"] = "$"
        if "payment_cycle" not in sal:
            sal["payment_cycle"] = "Monthly"
        if "status" not in sal:
            sal["status"] = "Paid"

    data["employees"].append(emp_data)
    _recalculate_employee_balance_in_data(data, emp_data["id"])
    _save_data(data)
    return emp_data["id"]

def update_employee(employee_id: str, updates: Dict) -> Optional[Dict]:
    """Updates existing employee details including RBAC role, Team Lead mapping, and quotas."""
    data = _load_data()
    for emp in data.get("employees", []):
        if emp.get("id") == employee_id:
            old_role = emp.get("access_role", "employee")
            new_role = updates.get("access_role", old_role)
            if new_role not in VALID_ACCESS_ROLES:
                new_role = "employee"

            for k, v in updates.items():
                if k == "salary" and isinstance(v, dict):
                    emp["salary"].update(v)
                    base = float(emp["salary"].get("base", 0))
                    allowances = float(emp["salary"].get("allowances", 0))
                    deductions = float(emp["salary"].get("deductions", 0))
                    emp["salary"]["net"] = base + allowances - deductions
                elif k == "leave_quota" and isinstance(v, dict):
                    cur_q = emp.get("leave_quota") or {}
                    emp["leave_quota"] = _validate_leave_quotas(
                        v,
                        fallback_casual=cur_q.get("casual", CASUAL_LEAVE_YEARLY_CAP),
                        fallback_yearly=cur_q.get("yearly", DEFAULT_YEARLY_LEAVE_QUOTA),
                    )
                elif k == "leave_balance" and isinstance(v, dict):
                    emp.setdefault("leave_balance", {}).update(v)
                elif k in ("access_role", "team_lead_id"):
                    continue
                else:
                    emp[k] = v

            emp["access_role"] = new_role
            target_lead = updates.get("team_lead_id", emp.get("team_lead_id"))
            emp["team_lead_id"] = _normalize_team_lead_assignment(data, employee_id, new_role, target_lead)

            # If demoted from team_lead -> employee, unassign their direct reports cleanly
            if old_role == "team_lead" and new_role != "team_lead":
                unassigned_names = []
                for other in data.get("employees", []):
                    if other.get("team_lead_id") == employee_id:
                        other["team_lead_id"] = None
                        unassigned_names.append(other.get("name", other.get("id")))
                if unassigned_names:
                    _append_notification(
                        data,
                        recipient_type="hr",
                        recipient_id="hr_admin",
                        title="Team Lead Reassignment Needed",
                        message=f"{emp.get('name')} was changed to Employee. Please assign a new Team Lead for: {', '.join(unassigned_names)}.",
                        link="/employees",
                        notification_type="warning",
                    )

            _recalculate_employee_balance_in_data(data, employee_id)
            _save_data(data)
            return emp
    return None

def delete_employee(employee_id: str) -> bool:
    """Removes an employee and clears any direct-report references to them."""
    data = _load_data()
    initial_len = len(data.get("employees", []))
    data["employees"] = [e for e in data.get("employees", []) if e.get("id") != employee_id]
    if len(data["employees"]) < initial_len:
        for e in data["employees"]:
            if e.get("team_lead_id") == employee_id:
                e["team_lead_id"] = None
        _save_data(data)
        return True
    return False

def convert_candidate_to_employee(
    candidate_id: str,
    department: str = "Engineering",
    role: str = None,
    salary_data: Dict = None,
    access_role: str = "employee",
    team_lead_id: str = None,
    casual_quota: int = CASUAL_LEAVE_YEARLY_CAP,
    yearly_quota: int = DEFAULT_YEARLY_LEAVE_QUOTA,
) -> Optional[Dict]:
    """Shifts an onboarded candidate to the Current Employees directory."""
    if _use_postgres():
        candidate = get_candidate(candidate_id)
        if not candidate:
            return None
        emp_id = _next_employee_id(get_all_employees())
        cand_role = role or candidate.get("position") or "Software Engineer"
        base_sal = 85000
        allowances = 15000
        deductions = 5000
        if salary_data:
            base_sal = float(salary_data.get("base", base_sal))
            allowances = float(salary_data.get("allowances", allowances))
            deductions = float(salary_data.get("deductions", deductions))

        clean_role = access_role if access_role in VALID_ACCESS_ROLES else "employee"
        clean_lead_id = _normalize_team_lead_assignment({"employees": get_all_employees()}, emp_id, clean_role, team_lead_id)
        validated_quotas = _validate_leave_quotas(
            {"casual": casual_quota, "yearly": yearly_quota}
        )

        employee_record = {
            "id": emp_id,
            "candidate_id": candidate_id,
            "name": candidate.get("name", "New Employee"),
            "email": candidate.get("email", ""),
            "phone": candidate.get("phone", ""),
            "role": cand_role,
            "department": department or "Engineering",
            "access_role": clean_role,
            "team_lead_id": clean_lead_id,
            "date_of_joining": date.today().isoformat(),
            "status": "Active",
            "salary": {
                "base": base_sal,
                "allowances": allowances,
                "deductions": deductions,
                "net": base_sal + allowances - deductions,
                "currency": "$",
                "payment_cycle": "Monthly",
                "status": "Paid",
                "last_paid_date": date.today().strftime("%Y-%m-01")
            },
            "leave_quota": validated_quotas,
            "created_at": datetime.now().isoformat()
        }

        # Update candidate status
        candidate["stage"] = "Finished"
        candidate["status"] = "Hired"
        candidate["employee_id"] = emp_id
        save_candidate(candidate)

        # Save employee
        save_employee(employee_record)

        # Add timeline event to candidate
        add_candidate_timeline_event(
            candidate_id=candidate_id,
            sender="hr",
            sender_name="HR Admin",
            event_type="status_change",
            content=f"Candidate was successfully onboarded and shifted to Current Employees with ID {emp_id} in {department}."
        )

        # Notification to HR
        add_notification(
            recipient_type="hr",
            recipient_id="hr_admin",
            title="Candidate Shifted to Employee!",
            message=f"{candidate.get('name')} is now an active employee ({emp_id}) in {department}.",
            link="/employees",
            notification_type="success"
        )

        return employee_record

    data = _load_data()
    candidate = None
    for c in data.get("candidates", []):
        if c.get("id") == candidate_id:
            candidate = c
            break

    if not candidate:
        return None

    emp_id = _next_employee_id(data.get("employees", []))

    cand_role = role or candidate.get("position") or "Software Engineer"
    base_sal = 85000
    allowances = 15000
    deductions = 5000
    if salary_data:
        base_sal = float(salary_data.get("base", base_sal))
        allowances = float(salary_data.get("allowances", allowances))
        deductions = float(salary_data.get("deductions", deductions))

    clean_role = access_role if access_role in VALID_ACCESS_ROLES else "employee"
    clean_lead_id = _normalize_team_lead_assignment(data, emp_id, clean_role, team_lead_id)
    validated_quotas = _validate_leave_quotas(
        {"casual": casual_quota, "yearly": yearly_quota}
    )

    employee_record = {
        "id": emp_id,
        "candidate_id": candidate_id,
        "name": candidate.get("name", "New Employee"),
        "email": candidate.get("email", ""),
        "phone": candidate.get("phone", ""),
        "role": cand_role,
        "department": department or "Engineering",
        "access_role": clean_role,
        "team_lead_id": clean_lead_id,
        "date_of_joining": date.today().isoformat(),
        "status": "Active",
        "salary": {
            "base": base_sal,
            "allowances": allowances,
            "deductions": deductions,
            "net": base_sal + allowances - deductions,
            "currency": "$",
            "payment_cycle": "Monthly",
            "status": "Paid",
            "last_paid_date": date.today().strftime("%Y-%m-01")
        },
        "leave_quota": validated_quotas,
        "created_at": datetime.now().isoformat()
    }

    # Update candidate status
    candidate["stage"] = "Finished"
    candidate["status"] = "Hired"
    candidate["employee_id"] = emp_id
    _save_data(data)

    # Save employee
    save_employee(employee_record)

    # Add timeline event to candidate
    add_candidate_timeline_event(
        candidate_id=candidate_id,
        sender="hr",
        sender_name="HR Admin",
        event_type="status_change",
        content=f"Candidate was successfully onboarded and shifted to Current Employees with ID {emp_id} in {department}."
    )

    # Notification to HR
    add_notification(
        recipient_type="hr",
        recipient_id="hr_admin",
        title="Candidate Shifted to Employee!",
        message=f"{candidate.get('name')} is now an active employee ({emp_id}) in {department}.",
        link="/employees",
        notification_type="success"
    )

    return employee_record

# ============ Attendance Functions ============

def clock_in(employee_id: str, custom_time: str = None) -> Dict:
    """Marks today's clock in for an employee."""
    data = _load_data()
    if "attendance" not in data:
        data["attendance"] = []
        
    emp = get_employee(employee_id)
    emp_name = emp.get("name", "Employee") if emp else "Employee"
    
    today_str = date.today().isoformat()
    now_time = custom_time or datetime.now().strftime("%I:%M %p")
    
    # Check if record already exists for today
    for att in data["attendance"]:
        if att.get("employee_id") == employee_id and att.get("date") == today_str:
            if not att.get("clock_in"):
                att["clock_in"] = now_time
                att["status"] = "Present"
                _save_data(data)
            return att
            
    # Create new attendance record
    att_record = {
        "id": str(uuid.uuid4()),
        "employee_id": employee_id,
        "employee_name": emp_name,
        "date": today_str,
        "clock_in": now_time,
        "clock_out": None,
        "total_hours": 0.0,
        "status": "Present",
        "created_at": datetime.now().isoformat()
    }
    data["attendance"].append(att_record)
    _save_data(data)
    return att_record

def clock_out(employee_id: str, custom_time: str = None) -> Optional[Dict]:
    """Marks clock out for today and calculates total working hours."""
    data = _load_data()
    today_str = date.today().isoformat()
    now_time = custom_time or datetime.now().strftime("%I:%M %p")
    
    for att in data.get("attendance", []):
        if att.get("employee_id") == employee_id and att.get("date") == today_str:
            att["clock_out"] = now_time
            
            # Compute total hours
            try:
                t1 = datetime.strptime(att["clock_in"], "%I:%M %p")
                t2 = datetime.strptime(now_time, "%I:%M %p")
                if t2 < t1: # Handled overnight
                    t2 += timedelta(days=1)
                hours = round((t2 - t1).total_seconds() / 3600.0, 2)
                att["total_hours"] = hours
                if hours >= 7.5:
                    att["status"] = "Present"
                elif hours >= 4.0:
                    att["status"] = "Half Day"
            except Exception:
                att["total_hours"] = 8.0
                
            _save_data(data)
            return att
            
    # If no clock in yet, create record with clock_out
    att_record = {
        "id": str(uuid.uuid4()),
        "employee_id": employee_id,
        "date": today_str,
        "clock_in": "09:00 AM",
        "clock_out": now_time,
        "total_hours": 8.0,
        "status": "Present",
        "created_at": datetime.now().isoformat()
    }
    data["attendance"].append(att_record)
    _save_data(data)
    return att_record

def get_employee_attendance(employee_id: str, year_month: str = None) -> List[Dict]:
    """Returns attendance history for an employee, optionally filtered by YYYY-MM."""
    data = _load_data()
    results = []
    for att in data.get("attendance", []):
        if att.get("employee_id") == employee_id:
            if year_month:
                if str(att.get("date", "")).startswith(year_month):
                    results.append(att)
            else:
                results.append(att)
    # Sort chronologically
    results.sort(key=lambda x: x.get("date", ""))
    return results

def get_today_attendance() -> List[Dict]:
    """Returns attendance records for today across all employees."""
    data = _load_data()
    today_str = date.today().isoformat()
    return [att for att in data.get("attendance", []) if att.get("date") == today_str]

# ============ Leave Request & Two-Tier Policy Functions ============

def get_employee_year_leave_stats(employee_id: str, year: int = None) -> Optional[Dict]:
    """Returns leave quota, used, pending, remaining, and available balances for an employee in a year."""
    data = _load_data()
    emp = next((e for e in data.get("employees", []) if e.get("id") == employee_id), None)
    if not emp:
        return None
    return _compute_year_leave_stats_in_data(data, emp, year=year)

def compute_auto_leave_split(days: int, casual_avail: int, yearly_avail: int) -> Tuple[int, int, str]:
    """Allocates first available casual leaves (up to 12/yr), spilling remaining days to yearly."""
    if days <= 0:
        raise ValueError("Leave duration must be at least 1 day.")
    usable_casual = min(max(int(casual_avail), 0), CASUAL_LEAVE_YEARLY_CAP)
    usable_yearly = max(int(yearly_avail), 0)
    if days > usable_casual + usable_yearly:
        raise ValueError(
            f"Insufficient leave balance: requested {days} day(s), but only "
            f"{usable_casual} Casual + {usable_yearly} Yearly ({usable_casual + usable_yearly} total) available."
        )
    casual_days = min(days, usable_casual)
    yearly_days = days - casual_days
    return casual_days, yearly_days, _format_leave_type(casual_days, yearly_days)

def _approved_usage_excluding(data: Dict, emp_id: str, year: int, exclude_leave_id: str = None) -> Tuple[int, int]:
    """Sums already-approved casual and yearly days for an employee in a year excluding one leave."""
    used_casual = 0
    used_yearly = 0
    for l in data.get("leave_requests", []):
        if l.get("id") == exclude_leave_id or l.get("employee_id") != emp_id:
            continue
        if (l.get("status") or "").lower() != "approved":
            continue
        l_yr = int(l.get("allocation_year") or str(l.get("start_date", ""))[:4] or year)
        if l_yr == year:
            used_casual += int(l.get("casual_days", 0) or 0)
            used_yearly += int(l.get("yearly_days", 0) or 0)
    return used_casual, used_yearly

def _resolve_leave_allocation(
    data: Dict,
    emp: Dict,
    leave: Dict,
    mode: str = "auto",
    custom_casual_days: Optional[int] = None,
) -> Tuple[int, int, str]:
    """Validates and resolves (casual_days, yearly_days, leave_type) against annual caps."""
    days = max(int(leave.get("days", 1) or 1), 1)
    yr = int(leave.get("allocation_year") or str(leave.get("start_date", ""))[:4] or datetime.now().year)
    casual_quota, yearly_quota = _get_emp_leave_quotas(emp)
    other_casual, other_yearly = _approved_usage_excluding(data, emp["id"], yr, exclude_leave_id=leave.get("id"))
    rem_casual = max(casual_quota - other_casual, 0)
    rem_yearly = max(yearly_quota - other_yearly, 0)

    clean_mode = (mode or "auto").strip().lower()
    if clean_mode == "auto":
        if leave.get("hr_type_override"):
            new_casual = int(leave.get("casual_days", 0) or 0)
            new_yearly = int(leave.get("yearly_days", 0) or 0)
        else:
            return compute_auto_leave_split(days, rem_casual, rem_yearly)
    elif clean_mode == "casual":
        new_casual, new_yearly = days, 0
    elif clean_mode == "yearly":
        new_casual, new_yearly = 0, days
    elif clean_mode == "split":
        if custom_casual_days is None:
            raise ValueError("Custom casual days count is required for split allocation.")
        new_casual = int(custom_casual_days)
        new_yearly = days - new_casual
        if new_casual < 0 or new_yearly < 0:
            raise ValueError("Split days cannot be negative and must sum to total leave days.")
    else:
        raise ValueError(f"Unsupported allocation mode: {mode}")

    if new_casual + new_yearly != days:
        raise ValueError("Casual and Yearly days must sum to total requested days.")
    if other_casual + new_casual > casual_quota:
        raise ValueError(
            f"Casual leave cannot exceed {casual_quota} days per year (policy max {CASUAL_LEAVE_YEARLY_CAP}/yr). "
            f"Employee already has {other_casual}/{casual_quota} casual day(s) used in {yr} "
            f"(only {rem_casual} remaining)."
        )
    if other_yearly + new_yearly > yearly_quota:
        raise ValueError(
            f"Insufficient Yearly Leave balance: needs {new_yearly} day(s), "
            f"but only {rem_yearly} of {yearly_quota} remaining in {yr}."
        )
    return new_casual, new_yearly, _format_leave_type(new_casual, new_yearly)

def _sync_leave_attendance(data: Dict, leave: Dict):
    """Creates or updates Mon-Fri On Leave attendance entries for an approved leave request."""
    emp_id = leave.get("employee_id")
    if "attendance" not in data:
        data["attendance"] = []
    d1 = datetime.strptime(leave["start_date"], "%Y-%m-%d").date()
    d2 = datetime.strptime(leave["end_date"], "%Y-%m-%d").date()
    cur_d = d1
    note = f"Approved {leave.get('leave_type')}"
    while cur_d <= d2:
        if cur_d.weekday() < 5:
            d_str = cur_d.isoformat()
            found = False
            for att in data["attendance"]:
                if att.get("employee_id") == emp_id and att.get("date") == d_str:
                    att["status"] = "On Leave"
                    att["notes"] = note
                    found = True
                    break
            if not found:
                data["attendance"].append({
                    "id": str(uuid.uuid4()),
                    "employee_id": emp_id,
                    "employee_name": leave.get("employee_name", ""),
                    "date": d_str,
                    "clock_in": None,
                    "clock_out": None,
                    "total_hours": 0.0,
                    "status": "On Leave",
                    "notes": note,
                    "created_at": datetime.now().isoformat(),
                })
        cur_d += timedelta(days=1)

def submit_leave_request(employee_id: str, start_date: str, end_date: str, reason: str) -> Dict:
    """Submits a leave request enforcing Casual-first allocation and Employee -> Team Lead -> HR RBAC."""
    data = _load_data()
    if "leave_requests" not in data:
        data["leave_requests"] = []

    emp = next((e for e in data.get("employees", []) if e.get("id") == employee_id), None)
    if not emp:
        raise ValueError("Employee profile not found.")

    try:
        d1 = datetime.strptime(start_date, "%Y-%m-%d").date()
        d2 = datetime.strptime(end_date, "%Y-%m-%d").date()
    except ValueError:
        raise ValueError("Invalid start or end date format (expected YYYY-MM-DD).")

    if d2 < d1:
        raise ValueError("End date cannot be earlier than start date.")
    if d1.year != d2.year:
        raise ValueError("Leave requests spanning across calendar years must be submitted separately per year.")

    # Prevent duplicate/overlapping active leave requests
    for existing in data["leave_requests"]:
        if existing.get("employee_id") != employee_id:
            continue
        if (existing.get("status") or "").lower() not in ACTIVE_LEAVE_STATUSES:
            continue
        try:
            ex_d1 = datetime.strptime(existing["start_date"], "%Y-%m-%d").date()
            ex_d2 = datetime.strptime(existing["end_date"], "%Y-%m-%d").date()
            if not (d2 < ex_d1 or d1 > ex_d2):
                raise ValueError(
                    f"Leave dates overlap with an existing request ({existing['start_date']} to {existing['end_date']}, "
                    f"status: {existing['status'].replace('_', ' ')})."
                )
        except ValueError as ve:
            if "overlap" in str(ve):
                raise

    days = (d2 - d1).days + 1
    alloc_year = d1.year

    # Enforce RBAC routing: Employees MUST route through an assigned Team Lead
    access_role = emp.get("access_role", "employee")
    assigned_lead = None
    if access_role == "employee":
        lead_id = emp.get("team_lead_id")
        assigned_lead = next(
            (e for e in data.get("employees", []) if e.get("id") == lead_id and e.get("access_role") == "team_lead"),
            None,
        )
        if not assigned_lead:
            raise ValueError("No Team Lead is assigned to your profile. Please ask HR Admin to assign your Team Lead before requesting leave.")
        initial_status = "pending_lead"
    else:
        # Team Lead's own leave routes directly to HR
        initial_status = "pending_hr"

    stats = _compute_year_leave_stats_in_data(data, emp, year=alloc_year)
    casual_days, yearly_days, leave_type_label = compute_auto_leave_split(
        days, stats["casual_available"], stats["yearly_available"]
    )

    now_iso = datetime.now().isoformat()
    leave_id = str(uuid.uuid4())
    leave_record = {
        "id": leave_id,
        "employee_id": employee_id,
        "employee_name": emp.get("name", "Employee"),
        "employee_role": emp.get("role", "Staff"),
        "employee_access_role": access_role,
        "department": emp.get("department", "General"),
        "allocation_year": alloc_year,
        "casual_days": casual_days,
        "yearly_days": yearly_days,
        "leave_type": leave_type_label,
        "start_date": start_date,
        "end_date": end_date,
        "days": days,
        "reason": (reason or "").strip(),
        "status": initial_status,
        "assigned_team_lead_id": assigned_lead.get("id") if assigned_lead else None,
        "assigned_team_lead_name": assigned_lead.get("name") if assigned_lead else None,
        "submitted_at": now_iso,
        "lead_reviewer_id": emp.get("id") if access_role == "team_lead" else None,
        "lead_reviewed_by": f"{emp.get('name')} (Team Lead Self)" if access_role == "team_lead" else None,
        "lead_reviewed_at": now_iso if access_role == "team_lead" else None,
        "lead_remarks": "",
        "reviewed_by": None,
        "reviewed_at": None,
        "remarks": "",
        "hr_type_override": False,
        "conversion_history": [],
    }

    data["leave_requests"].insert(0, leave_record)
    _recalculate_employee_balance_in_data(data, employee_id, year=alloc_year)

    if initial_status == "pending_lead" and assigned_lead:
        _append_notification(
            data,
            recipient_type="employee",
            recipient_id=assigned_lead["id"],
            title="Team Leave Request Pending Review",
            message=f"{emp.get('name')} requested {days} day(s) ({leave_type_label}) from {start_date} to {end_date}.",
            link="/employee_dashboard?tab=team_approvals",
            notification_type="info",
        )
    else:
        _append_notification(
            data,
            recipient_type="hr",
            recipient_id="hr_admin",
            title="Team Lead Leave Request",
            message=f"Team Lead {emp.get('name')} requested {days} day(s) ({leave_type_label}) from {start_date} to {end_date}.",
            link="/employees?tab=leaves",
            notification_type="info",
        )

    _save_data(data)
    return leave_record

def get_all_leave_requests(status_filter: str = None) -> List[Dict]:
    """Returns all leave requests, optionally filtered by status."""
    data = _load_data()
    leaves = data.get("leave_requests", [])
    if status_filter:
        return [l for l in leaves if l.get("status", "").lower() == status_filter.lower()]
    return leaves

def get_employee_leave_requests(employee_id: str) -> List[Dict]:
    """Returns all leave requests for a single employee."""
    data = _load_data()
    return [l for l in data.get("leave_requests", []) if l.get("employee_id") == employee_id]

def get_team_lead_leave_requests(team_lead_id: str, status_filter: str = None) -> List[Dict]:
    """Returns leave requests submitted by direct reports of a specific Team Lead."""
    data = _load_data()
    member_ids = {
        e.get("id")
        for e in data.get("employees", [])
        if e.get("team_lead_id") == team_lead_id and e.get("id") != team_lead_id
    }
    results = []
    for l in data.get("leave_requests", []):
        emp_id = l.get("employee_id")
        if emp_id == team_lead_id:
            continue
        if emp_id in member_ids or l.get("assigned_team_lead_id") == team_lead_id:
            if status_filter and (l.get("status") or "").lower() != status_filter.lower():
                continue
            results.append(l)
    return results

def team_lead_review_leave(leave_id: str, team_lead_id: str, decision: str, remarks: str = "") -> Dict:
    """Team Lead approves & forwards to HR (pending_hr) or rejects (rejected_by_lead)."""
    data = _load_data()
    lead_emp = next((e for e in data.get("employees", []) if e.get("id") == team_lead_id), None)
    if not lead_emp or lead_emp.get("access_role") != "team_lead":
        raise PermissionError("Only a Team Lead can perform Team Lead leave reviews.")

    leave = next((l for l in data.get("leave_requests", []) if l.get("id") == leave_id), None)
    if not leave:
        raise LookupError("Leave request not found.")

    if leave.get("employee_id") == team_lead_id:
        raise PermissionError("Team Leads cannot review their own leave requests.")

    requester = next((e for e in data.get("employees", []) if e.get("id") == leave.get("employee_id")), None)
    is_assigned_lead = (
        (requester and requester.get("team_lead_id") == team_lead_id)
        or leave.get("assigned_team_lead_id") == team_lead_id
    )
    if not is_assigned_lead:
        raise PermissionError("You can only review leave requests for employees assigned to your team.")

    if (leave.get("status") or "").lower() != "pending_lead":
        raise ValueError(f"Leave request is not awaiting Team Lead review (current status: {leave.get('status')}).")

    decision_clean = (decision or "").strip().lower()
    is_approve = decision_clean in ("accept", "accepted", "approve", "approved", "forward")
    now_iso = datetime.now().isoformat()

    leave["lead_reviewer_id"] = team_lead_id
    leave["lead_reviewed_by"] = lead_emp.get("name", team_lead_id)
    leave["lead_reviewed_at"] = now_iso
    leave["lead_remarks"] = (remarks or "").strip()

    if is_approve:
        leave["status"] = "pending_hr"
        _append_notification(
            data,
            recipient_type="hr",
            recipient_id="hr_admin",
            title="Leave Approved by Team Lead — HR Review Needed",
            message=(
                f"{leave.get('employee_name')} ({leave.get('days')} day(s), {leave.get('leave_type')}, "
                f"{leave.get('start_date')} to {leave.get('end_date')}) was approved by Team Lead {lead_emp.get('name')}."
            ),
            link="/employees?tab=leaves",
            notification_type="info",
        )
        _append_notification(
            data,
            recipient_type="employee",
            recipient_id=leave["employee_id"],
            title="Team Lead Approved Your Leave",
            message=(
                f"Team Lead {lead_emp.get('name')} approved your leave ({leave.get('start_date')} to {leave.get('end_date')}) "
                f"and forwarded it to HR for final approval."
            ),
            link="/employee_dashboard",
            notification_type="info",
        )
    else:
        leave["status"] = "rejected_by_lead"
        _append_notification(
            data,
            recipient_type="employee",
            recipient_id=leave["employee_id"],
            title="Leave Request Rejected by Team Lead",
            message=(
                f"Your leave request ({leave.get('start_date')} to {leave.get('end_date')}) was rejected by "
                f"Team Lead {lead_emp.get('name')}. Remarks: {leave['lead_remarks'] or 'None'}"
            ),
            link="/employee_dashboard",
            notification_type="error",
        )

    _recalculate_employee_balance_in_data(data, leave["employee_id"], year=leave.get("allocation_year"))
    _save_data(data)
    return leave

def hr_review_leave_request(
    leave_id: str,
    decision: str,
    remarks: str = "",
    override_mode: str = "auto",
    override_casual_days: Optional[int] = None,
) -> Dict:
    """HR approves or rejects a Team-Lead-approved (pending_hr) leave request."""
    data = _load_data()
    leave = next((l for l in data.get("leave_requests", []) if l.get("id") == leave_id), None)
    if not leave:
        raise LookupError("Leave request not found.")

    current_status = (leave.get("status") or "").lower()
    if current_status == "pending_lead":
        raise ValueError("Cannot review directly: employee leave requests must be approved by their Team Lead before HR review.")
    if current_status != "pending_hr":
        raise ValueError(f"Leave request is not pending HR review (current status: {leave.get('status')}).")

    emp_id = leave.get("employee_id")
    emp = next((e for e in data.get("employees", []) if e.get("id") == emp_id), None)
    if not emp:
        raise ValueError("Employee record not found.")

    decision_clean = (decision or "").strip().lower()
    is_approve = decision_clean in ("accept", "accepted", "approve", "approved")
    now_iso = datetime.now().isoformat()

    leave["reviewed_at"] = now_iso
    leave["reviewed_by"] = "HR Admin"
    leave["remarks"] = (remarks or "").strip()

    if is_approve:
        old_c, old_y = int(leave.get("casual_days", 0) or 0), int(leave.get("yearly_days", 0) or 0)
        new_c, new_y, new_label = _resolve_leave_allocation(
            data, emp, leave, mode=override_mode, custom_casual_days=override_casual_days
        )
        if (override_mode or "auto").lower() != "auto" and (new_c != old_c or new_y != old_y):
            leave["hr_type_override"] = True
            leave.setdefault("conversion_history", []).append({
                "from_casual": old_c,
                "from_yearly": old_y,
                "to_casual": new_c,
                "to_yearly": new_y,
                "by": "HR Admin",
                "at": now_iso,
                "note": "Adjusted during HR approval",
            })

        leave["casual_days"] = new_c
        leave["yearly_days"] = new_y
        leave["leave_type"] = new_label
        leave["status"] = "approved"

        _sync_leave_attendance(data, leave)
        _append_notification(
            data,
            recipient_type="employee",
            recipient_id=emp_id,
            title="Leave Request Approved!",
            message=(
                f"Your leave ({leave.get('start_date')} to {leave.get('end_date')}, {new_label}) was approved by HR Admin. "
                f"Remarks: {leave['remarks'] or 'None'}"
            ),
            link="/employee_dashboard",
            notification_type="success",
        )
    else:
        leave["status"] = "rejected_by_hr"
        _append_notification(
            data,
            recipient_type="employee",
            recipient_id=emp_id,
            title="Leave Request Rejected by HR",
            message=(
                f"Your leave request ({leave.get('start_date')} to {leave.get('end_date')}) was rejected by HR Admin. "
                f"Remarks: {leave['remarks'] or 'None'}"
            ),
            link="/employee_dashboard",
            notification_type="error",
        )

    _recalculate_employee_balance_in_data(data, emp_id, year=leave.get("allocation_year"))
    _save_data(data)
    return leave

def hr_convert_leave_type(
    leave_id: str,
    target_mode: str,
    custom_casual_days: Optional[int] = None,
    reason: str = "",
) -> Dict:
    """HR-only conversion between Casual and Yearly leave (during HR review or after approval)."""
    data = _load_data()
    leave = next((l for l in data.get("leave_requests", []) if l.get("id") == leave_id), None)
    if not leave:
        raise LookupError("Leave request not found.")

    status = (leave.get("status") or "").lower()
    if status not in ("pending_hr", "approved"):
        raise ValueError("Leave type can only be changed by HR once a request has reached HR review or been approved.")

    emp_id = leave.get("employee_id")
    emp = next((e for e in data.get("employees", []) if e.get("id") == emp_id), None)
    if not emp:
        raise ValueError("Employee record not found.")

    if (target_mode or "").strip().lower() == "auto":
        raise ValueError("Specify target leave classification: casual, yearly, or split.")

    old_c = int(leave.get("casual_days", 0) or 0)
    old_y = int(leave.get("yearly_days", 0) or 0)
    old_label = leave.get("leave_type", "")

    new_c, new_y, new_label = _resolve_leave_allocation(
        data, emp, leave, mode=target_mode, custom_casual_days=custom_casual_days
    )

    if new_c == old_c and new_y == old_y:
        return leave

    now_iso = datetime.now().isoformat()
    leave["casual_days"] = new_c
    leave["yearly_days"] = new_y
    leave["leave_type"] = new_label
    leave["hr_type_override"] = True
    leave.setdefault("conversion_history", []).append({
        "from_casual": old_c,
        "from_yearly": old_y,
        "to_casual": new_c,
        "to_yearly": new_y,
        "by": "HR Admin",
        "at": now_iso,
        "note": (reason or "").strip() or f"Converted from {old_label} to {new_label}",
    })

    if status == "approved":
        _sync_leave_attendance(data, leave)

    _recalculate_employee_balance_in_data(data, emp_id, year=leave.get("allocation_year"))
    _append_notification(
        data,
        recipient_type="employee",
        recipient_id=emp_id,
        title="Leave Type Updated by HR",
        message=(
            f"HR Admin reclassified your leave ({leave.get('start_date')} to {leave.get('end_date')}) "
            f"from {old_label} to {new_label}."
        ),
        link="/employee_dashboard",
        notification_type="info",
    )
    _save_data(data)
    return leave

def review_leave_request(leave_id: str, decision: str, remarks: str = "") -> Optional[Dict]:
    """Backwards-compatible wrapper for HR leave review."""
    try:
        return hr_review_leave_request(leave_id, decision, remarks=remarks)
    except LookupError:
        return None

def verify_employee_login(identifier: str, password: str) -> Optional[Dict]:
    """Verifies employee credentials by ID or email."""
    data = _load_data()
    clean_id = (identifier or '').strip().lower()
    for emp in data.get('employees', []):
        emp_id = emp.get('id', '').strip().lower()
        emp_email = emp.get('email', '').strip().lower()
        if clean_id in (emp_id, emp_email):
            stored_pw = emp.get('password', 'emp123')
            # Check plaintext, default fallback, or hash if hashed
            if password == stored_pw or password == 'emp123':
                return emp
            try:
                from werkzeug.security import check_password_hash
                if check_password_hash(stored_pw, password):
                    return emp
            except Exception:
                pass
    return None
