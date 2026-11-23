"""
TalentAI HR Platform - Automated PostgreSQL Storage & Integration Tests
End-to-end verification of database.py, migrate_to_postgres.py, and storage.py
PostgreSQL backend capabilities for Candidate CVs and Chat/Timeline threads.
"""

import os
import re
import json
import uuid
import tempfile
import unittest
from datetime import datetime
from unittest.mock import patch, MagicMock

import database
import storage
import migrate_to_postgres


# =============================================================================
# Mock / In-Memory PostgreSQL Simulation Engine
# =============================================================================

class FakeCursor:
    def __init__(self, db, dict_cursor=True):
        self.db = db
        self.dict_cursor = dict_cursor
        self.last_rows = []
        self.rowcount = 0
        self._iter_idx = 0

    def execute(self, query, params=None):
        self.last_rows, self.rowcount = self.db.execute_sql(query, params)
        self._iter_idx = 0

    def fetchone(self):
        if self._iter_idx < len(self.last_rows):
            row = self.last_rows[self._iter_idx]
            self._iter_idx += 1
            return row
        return None

    def fetchall(self):
        rows = self.last_rows[self._iter_idx:]
        self._iter_idx = len(self.last_rows)
        return rows

    def close(self):
        pass


class FakeConnection:
    """
    High-fidelity in-memory database connection simulating PostgreSQL
    table storage, indexing, JSONB adaptation, transactions, and queries.
    """
    def __init__(self):
        self.tables = {
            "positions": {},
            "users": {},
            "candidates": {},
            "candidate_timeline": {},
            "employees": {},
            "attendance": {},
            "leave_requests": {},
            "notifications": {},
            "app_settings": {},
        }
        self.committed = False
        self.rolled_back = False
        self.queries_log = []

    def cursor(self, cursor_factory=None):
        return FakeCursor(self, dict_cursor=True)

    def commit(self):
        self.committed = True

    def rollback(self):
        self.rolled_back = True

    def close(self):
        pass

    def execute_sql(self, sql, params):
        self.queries_log.append((sql, params))
        clean = " ".join(sql.strip().split())
        upper = clean.upper()

        # Ping
        if "SELECT 1 AS PING" in upper or clean.strip(" ;") == "SELECT 1 as ping":
            return [{"ping": 1}], 1

        # DDL statements (CREATE TABLE, EXTENSION, INDEX)
        if upper.startswith("CREATE ") or upper.startswith("--") or "CREATE TABLE" in upper:
            return [], 0

        # INSERT statements
        if upper.startswith("INSERT INTO"):
            m = re.match(r"INSERT\s+INTO\s+(\w+)\s*\((.*?)\)\s*VALUES\s*\((.*?)\)", clean, re.IGNORECASE)
            if m:
                table_name = m.group(1).lower()
                cols = [c.strip() for c in m.group(2).split(",")]
                val_exprs = [v.strip() for v in m.group(3).split(",")]

                row = {}
                p_idx = 0
                for col, vexpr in zip(cols, val_exprs):
                    if vexpr == "%s":
                        val = params[p_idx] if params and p_idx < len(params) else None
                        p_idx += 1
                    elif "CURRENT_TIMESTAMP" in vexpr.upper():
                        val = datetime.now().isoformat()
                    else:
                        val = vexpr

                    if hasattr(val, "adapted"):
                        val = val.adapted
                    row[col] = val

                table = self.tables.setdefault(table_name, {})
                pk = row.get("id")
                if table_name == "app_settings":
                    pk = row.get("key")
                elif table_name == "attendance":
                    pk = str(row.get("employee_id")) + "_" + str(row.get("date"))

                if pk:
                    if pk in table:
                        table[pk].update(row)
                    else:
                        table[pk] = row
                else:
                    pk = str(uuid.uuid4())
                    row["id"] = pk
                    table[pk] = row
                return [], 1

        # SELECT statements
        if upper.startswith("SELECT"):
            # SELECT * FROM candidates WHERE id = %s
            if "FROM CANDIDATES" in upper and "WHERE ID = %S" in upper:
                cid = params[0]
                row = self.tables["candidates"].get(cid)
                return [dict(row)] if row else [], 1 if row else 0

            # SELECT * FROM candidates WHERE position_id = %s
            if "FROM CANDIDATES" in upper and "WHERE POSITION_ID = %S" in upper:
                pid = params[0]
                rows = [dict(r) for r in self.tables["candidates"].values() if r.get("position_id") == pid]
                rows.sort(key=lambda r: float(r.get("final_rank_score") or 0.0), reverse=True)
                return rows, len(rows)

            # SELECT * FROM candidates WHERE user_id = %s
            if "FROM CANDIDATES" in upper and "WHERE USER_ID = %S" in upper:
                uid = params[0]
                rows = [dict(r) for r in self.tables["candidates"].values() if r.get("user_id") == uid]
                rows.sort(key=lambda r: r.get("created_at") or "", reverse=True)
                return rows, len(rows)

            # SELECT * FROM candidates ORDER BY final_rank_score DESC
            if "FROM CANDIDATES" in upper:
                rows = list(self.tables["candidates"].values())
                rows.sort(key=lambda r: float(r.get("final_rank_score") or 0.0), reverse=True)
                return [dict(r) for r in rows], len(rows)

            # SELECT * FROM candidate_timeline WHERE candidate_id = %s
            if "FROM CANDIDATE_TIMELINE" in upper and "WHERE CANDIDATE_ID = %S" in upper:
                cid = params[0]
                rows = [dict(r) for r in self.tables["candidate_timeline"].values() if r.get("candidate_id") == cid]
                rows.sort(key=lambda r: r.get("timestamp") or "")
                return rows, len(rows)

            # SELECT * FROM positions WHERE id = %s
            if "FROM POSITIONS" in upper and "WHERE ID = %S" in upper:
                pid = params[0]
                row = self.tables["positions"].get(pid)
                return [dict(row)] if row else [], 1 if row else 0

            # SELECT * FROM positions
            if "FROM POSITIONS" in upper:
                rows = list(self.tables["positions"].values())
                rows.sort(key=lambda r: r.get("created_at") or "")
                return [dict(r) for r in rows], len(rows)

            # SELECT value FROM app_settings WHERE key = %s
            if "FROM APP_SETTINGS" in upper and "KEY =" in upper:
                key = params[0] if params else "job_description_text"
                row = self.tables["app_settings"].get(key)
                return [dict(row)] if row else [], 1 if row else 0

            # SELECT id FROM users WHERE username = %s
            if "FROM USERS" in upper and "WHERE USERNAME = %S" in upper:
                uname = params[0]
                row = next((r for r in self.tables["users"].values() if r.get("username") == uname), None)
                return [dict(row)] if row else [], 1 if row else 0

            # SELECT * FROM users WHERE id = %s
            if "FROM USERS" in upper and "WHERE ID = %S" in upper:
                uid = params[0]
                row = self.tables["users"].get(uid)
                return [dict(row)] if row else [], 1 if row else 0

            # Notifications
            if "FROM NOTIFICATIONS" in upper:
                rows = list(self.tables["notifications"].values())
                return [dict(r) for r in rows], len(rows)

            # Employees
            if "FROM EMPLOYEES" in upper:
                if "WHERE ID = %S" in upper:
                    eid = params[0]
                    row = self.tables["employees"].get(eid)
                    return [dict(row)] if row else [], 1 if row else 0
                if "WHERE LOWER(EMAIL) = LOWER(%S)" in upper:
                    em = params[0].lower()
                    row = next((r for r in self.tables["employees"].values() if (r.get("email") or "").lower() == em), None)
                    return [dict(row)] if row else [], 1 if row else 0
                if "WHERE ACCESS_ROLE = 'TEAM_LEAD'" in upper:
                    rows = [dict(r) for r in self.tables["employees"].values() if r.get("access_role") == "team_lead"]
                    return rows, len(rows)
                rows = list(self.tables["employees"].values())
                return [dict(r) for r in rows], len(rows)

            # Attendance
            if "FROM ATTENDANCE" in upper:
                if "WHERE DATE = %S" in upper:
                    dt = params[0]
                    rows = [dict(r) for r in self.tables["attendance"].values() if r.get("date") == dt]
                    return rows, len(rows)
                if "WHERE EMPLOYEE_ID = %S" in upper:
                    eid = params[0]
                    rows = [dict(r) for r in self.tables["attendance"].values() if r.get("employee_id") == eid]
                    return rows, len(rows)
                rows = list(self.tables["attendance"].values())
                return [dict(r) for r in rows], len(rows)

            # Leave requests
            if "FROM LEAVE_REQUESTS" in upper:
                if "WHERE EMPLOYEE_ID = %S" in upper:
                    eid = params[0]
                    rows = [dict(r) for r in self.tables["leave_requests"].values() if r.get("employee_id") == eid]
                    return rows, len(rows)
                rows = list(self.tables["leave_requests"].values())
                return [dict(r) for r in rows], len(rows)

        # UPDATE statements
        if upper.startswith("UPDATE"):
            if "UPDATE CANDIDATES SET STATUS = %S" in upper:
                status, cid = params[0], params[1]
                if cid in self.tables["candidates"]:
                    self.tables["candidates"][cid]["status"] = status
                return [], 1

            if "UPDATE CANDIDATES SET STAGE = %S" in upper:
                stage, cid = params[0], params[1]
                if cid in self.tables["candidates"]:
                    self.tables["candidates"][cid]["stage"] = stage
                return [], 1

            if "UPDATE POSITIONS SET TITLE = %S, DESCRIPTION = %S" in upper:
                title, desc, pid = params[0], params[1], params[2]
                if pid in self.tables["positions"]:
                    self.tables["positions"][pid]["title"] = title
                    self.tables["positions"][pid]["description"] = desc
                return [], 1

            if "UPDATE EMPLOYEES SET TEAM_LEAD_ID = %S WHERE ID = %S" in upper:
                lead_id, emp_id = params[0], params[1]
                if emp_id in self.tables.get("employees", {}):
                    self.tables["employees"][emp_id]["team_lead_id"] = lead_id
                return [], 1

            if "UPDATE NOTIFICATIONS SET READ = TRUE WHERE ID = %S" in upper:
                nid = params[0]
                if nid in self.tables["notifications"]:
                    self.tables["notifications"][nid]["read"] = True
                return [], 1

        # DELETE statements
        if upper.startswith("DELETE FROM"):
            if "DELETE FROM CANDIDATES WHERE ID = %S" in upper:
                cid = params[0]
                self.tables["candidates"].pop(cid, None)
                # Cascading delete of timeline
                self.tables["candidate_timeline"] = {
                    k: v for k, v in self.tables["candidate_timeline"].items() if v.get("candidate_id") != cid
                }
                return [], 1

            if "DELETE FROM CANDIDATES WHERE POSITION_ID = %S" in upper:
                pid = params[0]
                c_to_del = [k for k, v in self.tables["candidates"].items() if v.get("position_id") == pid]
                for cid in c_to_del:
                    self.tables["candidates"].pop(cid, None)
                    self.tables["candidate_timeline"] = {
                        k: v for k, v in self.tables["candidate_timeline"].items() if v.get("candidate_id") != cid
                    }
                return [], len(c_to_del)

            if "DELETE FROM POSITIONS WHERE ID = %S" in upper:
                pid = params[0]
                self.tables["positions"].pop(pid, None)
                return [], 1

            if "DELETE FROM EMPLOYEES WHERE ID = %S" in upper:
                eid = params[0]
                self.tables["employees"].pop(eid, None)
                return [], 1

        return [], 0


# =============================================================================
# Test Suite 1: Database Layer & Connection Handling
# =============================================================================

class TestDatabaseModule(unittest.TestCase):
    def setUp(self):
        self.fake_conn = FakeConnection()
        database.set_mock_connection(self.fake_conn)

    def tearDown(self):
        database.set_mock_connection(None)
        database.close_pool()

    def test_get_db_config_from_explicit_env(self):
        with patch.dict(os.environ, {
            "POSTGRES_HOST": "db.internal",
            "POSTGRES_PORT": "5433",
            "POSTGRES_USER": "hr_user",
            "POSTGRES_PASSWORD": "secret_password",
            "POSTGRES_DB": "hr_test_db",
            "DATABASE_URL": ""
        }):
            cfg = database.get_db_config()
            self.assertEqual(cfg["host"], "db.internal")
            self.assertEqual(cfg["port"], 5433)
            self.assertEqual(cfg["user"], "hr_user")
            self.assertEqual(cfg["password"], "secret_password")
            self.assertEqual(cfg["dbname"], "hr_test_db")

    def test_get_db_config_from_database_url(self):
        test_url = "postgresql://myuser:mypass@customhost:5432/mydb"
        with patch.dict(os.environ, {"DATABASE_URL": test_url}):
            cfg = database.get_db_config()
            self.assertEqual(cfg, {"dsn": test_url})

    def test_get_connection_url_masking(self):
        with patch.dict(os.environ, {
            "POSTGRES_HOST": "localhost",
            "POSTGRES_PORT": "5432",
            "POSTGRES_USER": "testadmin",
            "POSTGRES_PASSWORD": "supersecretpassword",
            "POSTGRES_DB": "testdb",
            "DATABASE_URL": ""
        }):
            url = database.get_connection_url(masked=True)
            self.assertNotIn("supersecretpassword", url)
            self.assertIn("****", url)
            self.assertIn("testadmin", url)

    def test_json_serialization_helpers(self):
        sample_dict = {"skills": ["Python", "PostgreSQL"], "rank": 9.5}
        sample_list = [1, 2, 3]

        adapted = database.to_json(sample_dict)
        self.assertTrue(hasattr(adapted, "adapted"))
        self.assertEqual(database.from_json(sample_dict), sample_dict)
        self.assertEqual(database.from_json(sample_list), sample_list)
        self.assertIsNone(database.to_json(None))
        self.assertIsNone(database.from_json(None))

        # from_json string parsing
        json_str = json.dumps(sample_dict)
        self.assertEqual(database.from_json(json_str), sample_dict)

    def test_check_connection_and_availability(self):
        ok, msg = database.check_connection()
        self.assertTrue(ok)
        self.assertEqual(msg, "Connected successfully")
        self.assertTrue(database.is_database_available())

    def test_init_db_schema_creation(self):
        # Verify schema.sql is read and executed without errors
        res = database.init_db()
        self.assertTrue(res)

    def test_transaction_context_manager(self):
        with database.transaction() as cur:
            cur.execute("SELECT 1 as ping;")
            res = cur.fetchone()
            self.assertEqual(res["ping"], 1)
        self.assertTrue(self.fake_conn.committed)

    def test_transaction_rollback_on_error(self):
        class CustomTestError(Exception):
            pass

        with self.assertRaises(CustomTestError):
            with database.transaction() as cur:
                cur.execute("SELECT 1 as ping;")
                raise CustomTestError("Simulated failure")

        self.assertTrue(self.fake_conn.rolled_back)


# =============================================================================
# Test Suite 2: PostgreSQL Data Migration
# =============================================================================

class TestMigrationScript(unittest.TestCase):
    def setUp(self):
        self.fake_conn = FakeConnection()
        database.set_mock_connection(self.fake_conn)
        self.temp_dir = tempfile.mkdtemp()
        self.test_json_path = os.path.join(self.temp_dir, "migration_data.json")

        self.sample_data = {
            "positions": [
                {
                    "id": "POS-TEST-1",
                    "title": "Principal Backend Architect",
                    "description": "Lead high throughput distributed systems design.",
                    "created_at": "2026-01-01T00:00:00"
                }
            ],
            "users": [
                {
                    "id": "USR-TEST-1",
                    "username": "candidate_alex",
                    "password": "hashed_password",
                    "name": "Alex Rivera",
                    "email": "alex@corp.test",
                    "created_at": "2026-01-01T00:00:00"
                }
            ],
            "candidates": [
                {
                    "id": "CAND-TEST-1",
                    "position_id": "POS-TEST-1",
                    "user_id": "USR-TEST-1",
                    "name": "Alex Rivera",
                    "email": "alex@corp.test",
                    "phone": "+1 555-0101",
                    "university": "MIT",
                    "status": "accepted",
                    "stage": "Finished",
                    "raw_resume_text": "Experienced Systems Architect with Python & PostgreSQL mastery.",
                    "python_score": 9.8,
                    "experience_score": 9.5,
                    "uni_tier_score": 10.0,
                    "final_rank_score": 9.7,
                    "python_experience_years": 8.0,
                    "skills": ["Python", "PostgreSQL", "Distributed Systems", "Kubernetes"],
                    "attachments": [{"filename": "alex_cv.pdf", "path": "uploads/alex_cv.pdf"}],
                    "interview": {"status": "confirmed"},
                    "interview_rounds": [{"round_title": "System Design", "date": "2026-01-10"}],
                    "created_at": "2026-01-01T12:00:00",
                    "timeline": [
                        {
                            "id": "EVENT-1",
                            "sender": "candidate",
                            "sender_name": "Alex Rivera",
                            "type": "system",
                            "content": "Submitted application.",
                            "metadata": {"source_file": "alex_cv.pdf"},
                            "timestamp": "2026-01-01T12:00:00"
                        },
                        {
                            "id": "EVENT-2",
                            "sender": "hr",
                            "sender_name": "HR Admin",
                            "type": "message",
                            "content": "Welcome to the team!",
                            "metadata": {},
                            "timestamp": "2026-01-02T10:00:00"
                        }
                    ]
                }
            ],
            "employees": [
                {
                    "id": "EMP-LEAD-1",
                    "name": "Marcus Vance",
                    "email": "marcus@corp.test",
                    "role": "Engineering Director",
                    "department": "Engineering",
                    "access_role": "team_lead",
                    "team_lead_id": None,
                    "leave_quota": {"casual": 12, "yearly": 15},
                    "salary": {"base": 120000, "net": 130000}
                },
                {
                    "id": "EMP-STAFF-1",
                    "name": "Alex Rivera",
                    "email": "alex@corp.test",
                    "role": "Principal Architect",
                    "department": "Engineering",
                    "access_role": "employee",
                    "team_lead_id": "EMP-LEAD-1",
                    "leave_quota": {"casual": 12, "yearly": 15},
                    "salary": {"base": 110000, "net": 120000}
                }
            ],
            "attendance": [
                {
                    "id": "ATT-1",
                    "employee_id": "EMP-STAFF-1",
                    "employee_name": "Alex Rivera",
                    "date": "2026-01-05",
                    "clock_in": "09:00",
                    "clock_out": "17:30",
                    "total_hours": 8.5,
                    "status": "Present"
                }
            ],
            "leave_requests": [
                {
                    "id": "LEAVE-1",
                    "employee_id": "EMP-STAFF-1",
                    "employee_name": "Alex Rivera",
                    "leave_type": "Casual Leave",
                    "start_date": "2026-02-01",
                    "end_date": "2026-02-02",
                    "days": 2,
                    "casual_days": 2,
                    "yearly_days": 0,
                    "reason": "Personal rest",
                    "status": "approved"
                }
            ],
            "notifications": [
                {
                    "id": "NOTIF-1",
                    "recipient_type": "employee",
                    "recipient_id": "EMP-STAFF-1",
                    "title": "Welcome",
                    "message": "Welcome to TalentAI platform",
                    "read": False
                }
            ],
            "job_description_text": "Default Python Architect Job Description"
        }

        with open(self.test_json_path, "w") as f:
            json.dump(self.sample_data, f)

    def tearDown(self):
        database.set_mock_connection(None)
        if os.path.exists(self.test_json_path):
            os.remove(self.test_json_path)
        os.rmdir(self.temp_dir)

    def test_load_json_data_validation(self):
        data = migrate_to_postgres.load_json_data(self.test_json_path)
        self.assertEqual(data["job_description_text"], "Default Python Architect Job Description")

        with self.assertRaises(FileNotFoundError):
            migrate_to_postgres.load_json_data("/nonexistent/path/data.json")

    def test_full_migration_execution(self):
        stats = migrate_to_postgres.migrate_data(self.test_json_path)

        self.assertEqual(stats["positions"], 1)
        self.assertEqual(stats["users"], 1)
        self.assertEqual(stats["candidates"], 1)
        self.assertEqual(stats["timeline_events"], 2)
        self.assertEqual(stats["employees"], 2)
        self.assertEqual(stats["attendance"], 1)
        self.assertEqual(stats["leave_requests"], 1)
        self.assertEqual(stats["notifications"], 1)
        self.assertEqual(stats["app_settings"], 1)

        # Verify candidate CV fields in table
        cand_in_db = self.fake_conn.tables["candidates"]["CAND-TEST-1"]
        self.assertEqual(cand_in_db["name"], "Alex Rivera")
        self.assertEqual(cand_in_db["raw_resume_text"], "Experienced Systems Architect with Python & PostgreSQL mastery.")
        self.assertEqual(cand_in_db["final_rank_score"], 9.7)
        self.assertEqual(cand_in_db["python_score"], 9.8)
        self.assertIn("Distributed Systems", cand_in_db["skills"])

        # Verify timeline events
        events_in_db = [v for v in self.fake_conn.tables["candidate_timeline"].values() if v.get("candidate_id") == "CAND-TEST-1"]
        self.assertEqual(len(events_in_db), 2)

        # Verify employees hierarchy
        staff_emp = self.fake_conn.tables["employees"]["EMP-STAFF-1"]
        self.assertEqual(staff_emp["team_lead_id"], "EMP-LEAD-1")

    def test_migration_idempotence(self):
        # Running migration twice should update existing rows rather than create conflicts
        stats1 = migrate_to_postgres.migrate_data(self.test_json_path)
        stats2 = migrate_to_postgres.migrate_data(self.test_json_path)

        self.assertEqual(stats1, stats2)
        self.assertEqual(len(self.fake_conn.tables["candidates"]), 1)
        self.assertEqual(len(self.fake_conn.tables["candidate_timeline"]), 2)


# =============================================================================
# Test Suite 3: Candidate CV Storing & Retrieving
# =============================================================================

class TestPostgresCandidateStorage(unittest.TestCase):
    def setUp(self):
        self.fake_conn = FakeConnection()
        database.set_mock_connection(self.fake_conn)
        self.assertTrue(storage._use_postgres())

    def tearDown(self):
        database.set_mock_connection(None)

    def test_save_and_retrieve_candidate_cv_full_fidelity(self):
        cv_payload = {
            "name": "Elena Rostova",
            "email": "elena.rostova@example.com",
            "phone": "+1 415 555 9876",
            "position_id": "POS-DATA-101",
            "position": "Lead AI Engineer",
            "job_role": "Lead AI Engineer",
            "university": "Carnegie Mellon University",
            "status": "pending",
            "stage": "Technical Assessment",
            "raw_resume_text": (
                "Elena Rostova - Principal AI & ML Engineer.\n"
                "10+ years engineering backend infrastructure, Python, PyTorch, PostgreSQL, and LLMs.\n"
                "Architected distributed retrieval systems serving 50M daily requests."
            ),
            "source_file": "elena_rostova_resume.pdf",
            "analysis_method": "Gemini-1.5-Pro",
            "python_score": 9.9,
            "experience_score": 9.7,
            "uni_tier_score": 10.0,
            "final_rank_score": 9.85,
            "python_experience_years": 10.0,
            "skills": ["Python", "PostgreSQL", "PyTorch", "FastAPI", "Docker", "Kubernetes"],
            "attachments": [
                {"filename": "elena_rostova_resume.pdf", "path": "uploads/elena_rostova_resume.pdf", "size": 1048576},
                {"filename": "portfolio.pdf", "path": "uploads/portfolio.pdf", "size": 2097152}
            ],
            "custom_metadata_tag": "FastTrackCandidate",
            "years_of_experience": 10
        }

        # 1. Save Candidate CV to PostgreSQL
        cand_id = storage.save_candidate(cv_payload)
        self.assertTrue(cand_id)
        self.assertEqual(cv_payload["id"], cand_id)

        # 2. Retrieve Candidate CV by ID
        cand = storage.get_candidate(cand_id)
        self.assertIsNotNone(cand)
        self.assertEqual(cand["id"], cand_id)
        self.assertEqual(cand["name"], "Elena Rostova")
        self.assertEqual(cand["email"], "elena.rostova@example.com")
        self.assertEqual(cand["raw_resume_text"], cv_payload["raw_resume_text"])
        self.assertEqual(cand["source_file"], "elena_rostova_resume.pdf")

        # Verify numerical score fidelity
        self.assertEqual(cand["final_rank_score"], 9.85)
        self.assertEqual(cand["python_score"], 9.9)
        self.assertEqual(cand["experience_score"], 9.7)
        self.assertEqual(cand["uni_tier_score"], 10.0)
        self.assertEqual(cand["python_experience_years"], 10.0)

        # Verify skills and attachments
        self.assertEqual(cand["skills"], ["Python", "PostgreSQL", "PyTorch", "FastAPI", "Docker", "Kubernetes"])
        self.assertEqual(len(cand["attachments"]), 2)
        self.assertEqual(cand["attachments"][0]["filename"], "elena_rostova_resume.pdf")

        # Verify extra parsed_data fields preserved
        self.assertEqual(cand.get("custom_metadata_tag"), "FastTrackCandidate")
        self.assertEqual(cand.get("years_of_experience"), 10)

    def test_get_all_candidates_sorting_by_rank(self):
        candidates = [
            {"name": "Candidate B", "final_rank_score": 8.0, "python_score": 8.0},
            {"name": "Candidate A", "final_rank_score": 9.5, "python_score": 9.5},
            {"name": "Candidate C", "final_rank_score": 7.2, "python_score": 7.0},
        ]
        for c in candidates:
            storage.save_candidate(c)

        all_cands = storage.get_all_candidates()
        self.assertEqual(len(all_cands), 3)
        self.assertEqual(all_cands[0]["name"], "Candidate A")
        self.assertEqual(all_cands[1]["name"], "Candidate B")
        self.assertEqual(all_cands[2]["name"], "Candidate C")

    def test_get_candidates_by_position_and_user(self):
        cand1 = {"name": "Pos1 Cand", "position_id": "POS-1", "user_id": "USR-1", "final_rank_score": 9.0}
        cand2 = {"name": "Pos2 Cand", "position_id": "POS-2", "user_id": "USR-2", "final_rank_score": 8.5}
        storage.save_candidate(cand1)
        storage.save_candidate(cand2)

        pos1_cands = storage.get_candidates_by_position("POS-1")
        self.assertEqual(len(pos1_cands), 1)
        self.assertEqual(pos1_cands[0]["name"], "Pos1 Cand")

        user2_cands = storage.get_candidates_by_user("USR-2")
        self.assertEqual(len(user2_cands), 1)
        self.assertEqual(user2_cands[0]["name"], "Pos2 Cand")

    def test_update_status_and_stage(self):
        cand_id = storage.save_candidate({"name": "Test Candidate", "status": "pending", "stage": "Screening"})

        storage.update_candidate_status(cand_id, "accepted")
        c = storage.get_candidate(cand_id)
        self.assertEqual(c["status"], "accepted")

        storage.update_candidate_stage(cand_id, "Offer")
        c = storage.get_candidate(cand_id)
        self.assertEqual(c["stage"], "Offer")

    def test_delete_candidate(self):
        cand_id = storage.save_candidate({"name": "To Delete Candidate"})
        self.assertIsNotNone(storage.get_candidate(cand_id))

        storage.delete_candidate(cand_id)
        self.assertIsNone(storage.get_candidate(cand_id))

    def test_overview_stats_calculation(self):
        storage.save_candidate({"name": "Cand 1", "status": "accepted", "final_rank_score": 9.0})
        storage.save_candidate({"name": "Cand 2", "status": "pending", "final_rank_score": 8.0})
        storage.save_candidate({"name": "Cand 3", "status": "rejected", "final_rank_score": 5.0})

        stats = storage.get_overview_stats()
        self.assertEqual(stats["total_candidates"], 3)
        self.assertEqual(stats["accepted_count"], 1)
        self.assertEqual(stats["pending_count"], 1)
        self.assertEqual(stats["rejected_count"], 1)


# =============================================================================
# Test Suite 4: Chat Threads, Messages & Candidate Timeline
# =============================================================================

class TestPostgresChatAndTimeline(unittest.TestCase):
    def setUp(self):
        self.fake_conn = FakeConnection()
        database.set_mock_connection(self.fake_conn)
        self.cand_id = storage.save_candidate({
            "name": "Liam Connor",
            "email": "liam@example.com",
            "position": "Software Engineer",
            "final_rank_score": 9.0
        })

    def tearDown(self):
        database.set_mock_connection(None)

    def test_candidate_and_hr_chat_messages(self):
        # 1. Candidate sends chat message
        msg1 = storage.add_candidate_timeline_event(
            candidate_id=self.cand_id,
            sender="candidate",
            sender_name="Liam Connor",
            event_type="message",
            content="Hello HR team! I have submitted my application.",
            metadata={"source": "chat_widget"}
        )
        self.assertIsNotNone(msg1)
        self.assertEqual(msg1["sender"], "candidate")
        self.assertEqual(msg1["content"], "Hello HR team! I have submitted my application.")

        # 2. HR responds to candidate
        msg2 = storage.add_candidate_timeline_event(
            candidate_id=self.cand_id,
            sender="hr",
            sender_name="HR Recruitment Team",
            event_type="message",
            content="Thank you Liam! We reviewed your CV and are scheduling your technical interview.",
            metadata={"hr_id": "EMP-1004"}
        )
        self.assertIsNotNone(msg2)
        self.assertEqual(msg2["sender"], "hr")

        # 3. Retrieve conversation timeline
        timeline = storage.get_candidate_timeline(self.cand_id)
        self.assertEqual(len(timeline), 2)
        self.assertEqual(timeline[0]["content"], "Hello HR team! I have submitted my application.")
        self.assertEqual(timeline[1]["content"], "Thank you Liam! We reviewed your CV and are scheduling your technical interview.")

    def test_internal_recruiter_notes(self):
        note = storage.add_candidate_timeline_event(
            candidate_id=self.cand_id,
            sender="hr",
            sender_name="HR Lead Reviewer",
            event_type="internal_note",
            content="Confidential Note: Candidate demonstrated exceptional PostgreSQL query optimization skills.",
            metadata={"visibility": "internal_only", "priority": "high"}
        )
        self.assertIsNotNone(note)
        self.assertEqual(note["type"], "internal_note")

        timeline = storage.get_candidate_timeline(self.cand_id)
        matching = [e for e in timeline if e["type"] == "internal_note"]
        self.assertEqual(len(matching), 1)
        self.assertEqual(matching[0]["content"], note["content"])
        self.assertEqual(matching[0]["metadata"]["priority"], "high")

    def test_chat_attachments(self):
        event = storage.add_candidate_timeline_event(
            candidate_id=self.cand_id,
            sender="candidate",
            sender_name="Liam Connor",
            event_type="message",
            content="Here is my design portfolio document.",
            metadata={
                "attachments": [
                    {"filename": "system_design_diagram.png", "url": "/uploads/system_design_diagram.png"},
                    {"filename": "certifications.pdf", "url": "/uploads/certifications.pdf"}
                ]
            }
        )
        self.assertIsNotNone(event)
        self.assertEqual(len(event["attachments"]), 2)

        timeline = storage.get_candidate_timeline(self.cand_id)
        att_event = next(e for e in timeline if e["id"] == event["id"])
        self.assertEqual(len(att_event["attachments"]), 2)
        self.assertEqual(att_event["attachments"][0]["filename"], "system_design_diagram.png")

    def test_empty_timeline_auto_synthesis(self):
        # Fresh candidate with no timeline events yet
        fresh_id = storage.save_candidate({
            "name": "Maya Lin",
            "position": "Data Scientist",
            "final_rank_score": 9.4,
            "python_score": 9.6,
            "experience_score": 9.2,
            "uni_tier_score": 9.5,
            "source_file": "maya_resume.pdf"
        })

        # Querying timeline should synthesize initial events
        timeline = storage.get_candidate_timeline(fresh_id)
        self.assertTrue(len(timeline) >= 2)
        types = [e["type"] for e in timeline]
        self.assertIn("system", types)
        # Verify screening event contains scores
        screening = next(e for e in timeline if "Screening" in e.get("sender_name", "") or "score" in e.get("content", ""))
        self.assertIn("9.4", screening["content"])

    def test_employee_and_attendance_in_postgres(self):
        # Create Team Lead
        lead_id = storage.save_employee({
            "id": "EMP-2001",
            "name": "Sarah Connor",
            "email": "sarah@corp.test",
            "role": "Engineering Lead",
            "access_role": "team_lead",
            "leave_quota": {"casual": 12, "yearly": 15}
        })
        self.assertEqual(lead_id, "EMP-2001")

        # Create Employee under Team Lead
        emp_id = storage.save_employee({
            "id": "EMP-2002",
            "name": "John Connor",
            "email": "john@corp.test",
            "role": "Software Engineer",
            "access_role": "employee",
            "team_lead_id": "EMP-2001",
            "leave_quota": {"casual": 10, "yearly": 15}
        })
        self.assertEqual(emp_id, "EMP-2002")

        # Verify retrieval from PostgreSQL simulation
        emp = storage.get_employee("EMP-2002")
        self.assertIsNotNone(emp)
        self.assertEqual(emp["name"], "John Connor")
        self.assertEqual(emp["team_lead_id"], "EMP-2001")
        self.assertEqual(emp["leave_quota"]["casual"], 10)

        # Clock in
        att = storage.clock_in("EMP-2002", custom_time="09:15 AM")
        self.assertIsNotNone(att)
        self.assertEqual(att["employee_id"], "EMP-2002")
        self.assertEqual(att["clock_in"], "09:15 AM")
        self.assertEqual(att["status"], "Present")

        # Verify today's attendance
        today_att = storage.get_today_attendance()
        self.assertTrue(any(a["employee_id"] == "EMP-2002" for a in today_att))

        # Delete employee
        deleted = storage.delete_employee("EMP-2002")
        self.assertTrue(deleted)
        self.assertIsNone(storage.get_employee("EMP-2002"))


if __name__ == "__main__":
    unittest.main()
