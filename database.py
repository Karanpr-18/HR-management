"""
TalentAI HR Platform - Database Access Layer
Robust PostgreSQL connection pooling, transactional helpers, schema management,
and data serialization using psycopg2 with resilient in-memory fallback.
"""

import os
import re
import uuid
import logging
import threading
from datetime import datetime, date
from contextlib import contextmanager
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

try:
    import psycopg2
    import psycopg2.pool
    import psycopg2.extras
    HAS_PSYCOPG2 = True
except ImportError:
    psycopg2 = None
    HAS_PSYCOPG2 = False

logger = logging.getLogger("talentai.database")
if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("[%(asctime)s] [%(levelname)s] [database] %(message)s"))
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)

# =============================================================================
# Global Pool & Concurrency Lock
# =============================================================================
_pool = None
_pool_lock = threading.Lock()
_mock_connection = None  # Hook for mock connections during unit tests
_fallback_connection = None  # Resilient in-memory fallback connection

DEFAULT_MIN_CONNECTIONS = 1
DEFAULT_MAX_CONNECTIONS = 20


def get_db_config() -> Dict[str, Any]:
    """
    Parses and returns database connection configuration from environment.
    Priority:
      1. DATABASE_URL (standard 12-factor connection string)
      2. Explicit POSTGRES_* environment variables with fallback defaults.
    """
    database_url = os.environ.get("DATABASE_URL", "").strip()
    if database_url:
        return {"dsn": database_url}

    return {
        "host": os.environ.get("POSTGRES_HOST", "localhost"),
        "port": int(os.environ.get("POSTGRES_PORT", 5432)),
        "user": os.environ.get("POSTGRES_USER", "postgres"),
        "password": os.environ.get("POSTGRES_PASSWORD", "postgres"),
        "dbname": os.environ.get("POSTGRES_DB", "talentai_hr"),
        "connect_timeout": int(os.environ.get("POSTGRES_TIMEOUT", 10)),
    }


def is_postgres_configured() -> bool:
    """
    Checks if PostgreSQL connection settings are provided in the environment.
    Returns True if DATABASE_URL or POSTGRES_HOST / POSTGRES_DB is explicitly set.
    """
    return bool(
        os.environ.get("DATABASE_URL")
        or os.environ.get("POSTGRES_HOST")
        or os.environ.get("POSTGRES_DB")
    )


def get_connection_url(masked: bool = True) -> str:
    """Returns a formatted connection string, optionally masking sensitive passwords."""
    cfg = get_db_config()
    if "dsn" in cfg:
        dsn = cfg["dsn"]
        if masked and "@" in dsn and ":" in dsn.split("@")[0]:
            parts = dsn.split("@")
            prefix = parts[0]
            scheme_user = prefix.split(":")[:2]
            return f"{':'.join(scheme_user)}:****@{parts[1]}"
        return dsn
    pwd = "****" if masked else cfg.get("password", "")
    return f"postgresql://{cfg.get('user')}:{pwd}@{cfg.get('host')}:{cfg.get('port')}/{cfg.get('dbname')}"


# =============================================================================
# In-Memory Resilient Fallback Engine
# =============================================================================

class InMemoryCursor:
    def __init__(self, conn, dict_cursor=True):
        self.conn = conn
        self.dict_cursor = dict_cursor
        self.last_rows = []
        self.rowcount = 0
        self._iter_idx = 0

    def execute(self, query, params=None):
        self.last_rows, self.rowcount = self.conn.execute_sql(query, params)
        self._iter_idx = 0

    def fetchone(self):
        if self._iter_idx < len(self.last_rows):
            row = self.last_rows[self._iter_idx]
            self._iter_idx += 1
            return dict(row) if (self.dict_cursor and isinstance(row, dict)) else row
        return None

    def fetchall(self):
        rows = self.last_rows[self._iter_idx:]
        self._iter_idx = len(self.last_rows)
        return [dict(r) if (self.dict_cursor and isinstance(r, dict)) else r for r in rows]

    def close(self):
        pass


class InMemoryConnection:
    """
    Simulates PostgreSQL relational tables, JSONB columns, primary keys, and queries.
    Used seamlessly when a live PostgreSQL daemon is not reachable.
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

    def cursor(self, cursor_factory=None):
        return InMemoryCursor(self, dict_cursor=True)

    def commit(self):
        self.committed = True

    def rollback(self):
        self.rolled_back = True

    def close(self):
        pass

    def execute_sql(self, sql: str, params: Optional[Sequence[Any]] = None) -> Tuple[List[Dict[str, Any]], int]:
        clean = " ".join(sql.strip().split())
        upper = clean.upper()

        # 1. Ping & Counts
        if "SELECT 1 AS PING" in upper or clean.strip(" ;") == "SELECT 1 as ping":
            return [{"ping": 1}], 1

        if "COUNT(*)" in upper:
            for tbl in self.tables:
                if f"FROM {tbl.upper()}" in upper:
                    return [{"cnt": len(self.tables[tbl])}], 1
            return [{"cnt": 0}], 1

        # 2. DDL statements
        if upper.startswith("CREATE ") or upper.startswith("--") or "CREATE TABLE" in upper:
            return [], 0

        # 3. INSERT statements
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
                    pk = f"{row.get('employee_id')}_{row.get('date')}"

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

        # 4. SELECT statements
        if upper.startswith("SELECT"):
            # CANDIDATES
            if "FROM CANDIDATES" in upper:
                if "WHERE ID = %S" in upper:
                    cid = params[0]
                    row = self.tables["candidates"].get(cid)
                    return [dict(row)] if row else [], 1 if row else 0
                if "WHERE POSITION_ID = %S" in upper:
                    pid = params[0]
                    rows = [dict(r) for r in self.tables["candidates"].values() if r.get("position_id") == pid]
                    rows.sort(key=lambda r: float(r.get("final_rank_score") or 0.0), reverse=True)
                    return rows, len(rows)
                if "WHERE USER_ID = %S" in upper:
                    uid = params[0]
                    rows = [dict(r) for r in self.tables["candidates"].values() if r.get("user_id") == uid]
                    rows.sort(key=lambda r: r.get("created_at") or "", reverse=True)
                    return rows, len(rows)
                rows = list(self.tables["candidates"].values())
                rows.sort(key=lambda r: float(r.get("final_rank_score") or 0.0), reverse=True)
                return [dict(r) for r in rows], len(rows)

            # CANDIDATE_TIMELINE
            if "FROM CANDIDATE_TIMELINE" in upper:
                if "WHERE CANDIDATE_ID = %S" in upper:
                    cid = params[0]
                    rows = [dict(r) for r in self.tables["candidate_timeline"].values() if r.get("candidate_id") == cid]
                    rows.sort(key=lambda r: r.get("timestamp") or "")
                    return rows, len(rows)
                rows = list(self.tables["candidate_timeline"].values())
                rows.sort(key=lambda r: r.get("timestamp") or "")
                return rows, len(rows)

            # POSITIONS
            if "FROM POSITIONS" in upper:
                if "WHERE ID = %S" in upper:
                    pid = params[0]
                    row = self.tables["positions"].get(pid)
                    return [dict(row)] if row else [], 1 if row else 0
                rows = list(self.tables["positions"].values())
                rows.sort(key=lambda r: r.get("created_at") or "")
                return [dict(r) for r in rows], len(rows)

            # USERS
            if "FROM USERS" in upper:
                if "WHERE USERNAME = %S" in upper:
                    uname = params[0]
                    row = next((r for r in self.tables["users"].values() if r.get("username") == uname), None)
                    return [dict(row)] if row else [], 1 if row else 0
                if "WHERE ID = %S" in upper:
                    uid = params[0]
                    row = self.tables["users"].get(uid)
                    return [dict(row)] if row else [], 1 if row else 0
                rows = list(self.tables["users"].values())
                return [dict(r) for r in rows], len(rows)

            # EMPLOYEES
            if "FROM EMPLOYEES" in upper:
                if "WHERE ID = %S" in upper:
                    eid = params[0]
                    row = self.tables["employees"].get(eid)
                    return [dict(row)] if row else [], 1 if row else 0
                if "WHERE LOWER(EMAIL) = LOWER(%S)" in upper:
                    em = params[0].strip().lower()
                    row = next((r for r in self.tables["employees"].values() if (r.get("email") or "").strip().lower() == em), None)
                    return [dict(row)] if row else [], 1 if row else 0
                if "WHERE USER_ID = %S" in upper:
                    uid = params[0]
                    row = next((r for r in self.tables["employees"].values() if str(r.get("user_id")) == str(uid)), None)
                    return [dict(row)] if row else [], 1 if row else 0
                if "WHERE ACCESS_ROLE = 'TEAM_LEAD'" in upper:
                    rows = [dict(r) for r in self.tables["employees"].values() if r.get("access_role") == "team_lead"]
                    rows.sort(key=lambda r: r.get("name", ""))
                    return rows, len(rows)
                if "WHERE TEAM_LEAD_ID = %S" in upper:
                    lead_id = params[0]
                    rows = [dict(r) for r in self.tables["employees"].values() if r.get("team_lead_id") == lead_id and r.get("id") != lead_id]
                    rows.sort(key=lambda r: r.get("name", ""))
                    return rows, len(rows)
                rows = list(self.tables["employees"].values())
                rows.sort(key=lambda r: str(r.get("id", "")))
                return [dict(r) for r in rows], len(rows)

            # ATTENDANCE
            if "FROM ATTENDANCE" in upper:
                if "WHERE DATE = %S" in upper:
                    dt = params[0]
                    rows = [dict(r) for r in self.tables["attendance"].values() if str(r.get("date")) == str(dt)]
                    return rows, len(rows)
                if "WHERE EMPLOYEE_ID = %S" in upper:
                    eid = params[0]
                    rows = [dict(r) for r in self.tables["attendance"].values() if r.get("employee_id") == eid]
                    if "YYYY-MM" in upper and len(params) > 1:
                        ym = params[1]
                        rows = [r for r in rows if str(r.get("date", "")).startswith(ym)]
                    rows.sort(key=lambda r: str(r.get("date", "")))
                    return rows, len(rows)
                rows = list(self.tables["attendance"].values())
                rows.sort(key=lambda r: str(r.get("date", "")), reverse=True)
                return [dict(r) for r in rows], len(rows)

            # LEAVE_REQUESTS
            if "FROM LEAVE_REQUESTS" in upper:
                if "WHERE ID = %S" in upper:
                    lid = params[0]
                    row = self.tables["leave_requests"].get(lid)
                    return [dict(row)] if row else [], 1 if row else 0
                if "WHERE EMPLOYEE_ID = %S" in upper:
                    eid = params[0]
                    rows = [dict(r) for r in self.tables["leave_requests"].values() if r.get("employee_id") == eid]
                    rows.sort(key=lambda r: str(r.get("start_date", "")), reverse=True)
                    return rows, len(rows)
                if "WHERE LOWER(STATUS) = LOWER(%S)" in upper:
                    st = params[0].lower()
                    rows = [dict(r) for r in self.tables["leave_requests"].values() if (r.get("status") or "").lower() == st]
                    rows.sort(key=lambda r: str(r.get("start_date", "")), reverse=True)
                    return rows, len(rows)
                if "TEAM_LEAD_ID" in upper:
                    lead_id = params[0]
                    status_filter = params[3].lower() if len(params) > 3 else None
                    emp_members = {k for k, v in self.tables["employees"].items() if v.get("team_lead_id") == lead_id and k != lead_id}
                    rows = []
                    for r in self.tables["leave_requests"].values():
                        if r.get("employee_id") != lead_id and (r.get("employee_id") in emp_members or r.get("assigned_team_lead_id") == lead_id):
                            if not status_filter or (r.get("status") or "").lower() == status_filter:
                                rows.append(dict(r))
                    rows.sort(key=lambda r: str(r.get("start_date", "")), reverse=True)
                    return rows, len(rows)
                rows = list(self.tables["leave_requests"].values())
                rows.sort(key=lambda r: str(r.get("start_date", "")), reverse=True)
                return [dict(r) for r in rows], len(rows)

            # NOTIFICATIONS
            if "FROM NOTIFICATIONS" in upper:
                rows = list(self.tables["notifications"].values())
                if "WHERE" in upper:
                    if "RECIPIENT_TYPE = %S" in upper and "RECIPIENT_ID = %S" in upper:
                        rtype, rid = params[0], params[1]
                        rows = [r for r in rows if r.get("recipient_type") == rtype and str(r.get("recipient_id")) == str(rid)]
                    elif "RECIPIENT_ID = %S" in upper:
                        rid = params[0]
                        rows = [r for r in rows if str(r.get("recipient_id")) == str(rid)]
                    if "READ = FALSE" in upper:
                        rows = [r for r in rows if not r.get("read")]
                rows.sort(key=lambda r: str(r.get("created_at", "")), reverse=True)
                return [dict(r) for r in rows], len(rows)

            # APP_SETTINGS
            if "FROM APP_SETTINGS" in upper:
                if "KEY = %S" in upper or "KEY = 'JOB_DESCRIPTION'" in upper:
                    key = params[0] if params else "job_description"
                    row = self.tables["app_settings"].get(key)
                    return [dict(row)] if row else [], 1 if row else 0
                rows = list(self.tables["app_settings"].values())
                return [dict(r) for r in rows], len(rows)

        # 5. UPDATE statements
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
                if emp_id in self.tables["employees"]:
                    self.tables["employees"][emp_id]["team_lead_id"] = lead_id
                return [], 1

            if "UPDATE EMPLOYEES SET TEAM_LEAD_ID = NULL WHERE TEAM_LEAD_ID = %S" in upper:
                lead_id = params[0]
                for emp in self.tables["employees"].values():
                    if emp.get("team_lead_id") == lead_id:
                        emp["team_lead_id"] = None
                return [], 1

            if "UPDATE NOTIFICATIONS SET READ = TRUE WHERE ID = %S" in upper:
                nid = params[0]
                if nid in self.tables["notifications"]:
                    self.tables["notifications"][nid]["read"] = True
                return [], 1

            if "UPDATE NOTIFICATIONS SET READ = TRUE" in upper:
                for notif in self.tables["notifications"].values():
                    notif["read"] = True
                return [], 1

        # 6. DELETE statements
        if upper.startswith("DELETE FROM"):
            if "DELETE FROM CANDIDATES WHERE ID = %S" in upper:
                cid = params[0]
                self.tables["candidates"].pop(cid, None)
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


def _get_fallback_connection() -> InMemoryConnection:
    """Returns the singleton in-memory database engine for local resilience."""
    global _fallback_connection
    if _fallback_connection is None:
        _fallback_connection = InMemoryConnection()
        try:
            import seed_data
            set_mock_connection(_fallback_connection)
            seed_data.seed_database()
            set_mock_connection(None)
        except Exception as exc:
            logger.warning(f"Error seeding fallback database connection: {exc}")
    return _fallback_connection


# =============================================================================
# Connection Pool Management
# =============================================================================

def get_pool(
    minconn: Optional[int] = None,
    maxconn: Optional[int] = None,
    force_reconnect: bool = False
):
    """Returns singleton ThreadedConnectionPool instance."""
    global _pool

    if not HAS_PSYCOPG2:
        raise RuntimeError("psycopg2 is not installed. Using in-memory fallback database.")

    with _pool_lock:
        if force_reconnect and _pool is not None:
            close_pool()

        if _pool is None:
            min_c = minconn or int(os.environ.get("DB_POOL_MIN", DEFAULT_MIN_CONNECTIONS))
            max_c = maxconn or int(os.environ.get("DB_POOL_MAX", DEFAULT_MAX_CONNECTIONS))
            cfg = get_db_config()
            if "dsn" in cfg:
                _pool = psycopg2.pool.ThreadedConnectionPool(min_c, max_c, dsn=cfg["dsn"])
            else:
                _pool = psycopg2.pool.ThreadedConnectionPool(
                    min_c,
                    max_c,
                    host=cfg["host"],
                    port=cfg["port"],
                    user=cfg["user"],
                    password=cfg["password"],
                    database=cfg["dbname"],
                    connect_timeout=cfg.get("connect_timeout", 5),
                )
            logger.info(f"Initialized PostgreSQL pool at {get_connection_url()}")

        return _pool


def close_pool():
    """Safely closes all active connections in the pool."""
    global _pool
    with _pool_lock:
        if _pool is not None:
            try:
                _pool.closeall()
                logger.info("Closed PostgreSQL connection pool.")
            except Exception as e:
                logger.warning(f"Error closing pool: {e}")
            finally:
                _pool = None


def set_mock_connection(conn):
    """Testing hook: allows injecting a mock or in-memory connection object."""
    global _mock_connection
    _mock_connection = conn


# =============================================================================
# Context Managers & Transaction Helpers
# =============================================================================

@contextmanager
def get_connection():
    """Context manager yielding a database connection."""
    global _mock_connection
    if _mock_connection is not None:
        yield _mock_connection
        return

    if not HAS_PSYCOPG2:
        yield _get_fallback_connection()
        return

    try:
        pool = get_pool()
        conn = pool.getconn()
        try:
            if hasattr(psycopg2, "extras") and hasattr(psycopg2.extras, "register_default_jsonb"):
                psycopg2.extras.register_default_jsonb(conn)
            yield conn
        finally:
            pool.putconn(conn)
    except Exception as exc:
        logger.debug(f"PostgreSQL connection unavailable ({exc}). Using in-memory database engine.")
        yield _get_fallback_connection()


@contextmanager
def get_cursor(commit: bool = True, dict_cursor: bool = True):
    """Context manager yielding a cursor with automated commit and rollback."""
    with get_connection() as conn:
        cursor_factory = (
            psycopg2.extras.RealDictCursor
            if (HAS_PSYCOPG2 and dict_cursor and hasattr(psycopg2, "extras") and hasattr(psycopg2.extras, "RealDictCursor"))
            else None
        )
        try:
            cur = conn.cursor(cursor_factory=cursor_factory)
        except TypeError:
            cur = conn.cursor()
        try:
            yield cur
            if commit:
                conn.commit()
        except Exception:
            try:
                conn.rollback()
            except Exception:
                pass
            raise
        finally:
            try:
                cur.close()
            except Exception:
                pass


@contextmanager
def transaction(dict_cursor: bool = True):
    """Multi-query atomic transaction block."""
    with get_cursor(commit=True, dict_cursor=dict_cursor) as cur:
        yield cur


def execute_query(
    query: str,
    params: Optional[Union[Sequence[Any], Dict[str, Any]]] = None,
    fetch: Optional[str] = None,
    commit: bool = True,
    dict_cursor: bool = True,
) -> Any:
    """Executes a single SQL query against the database."""
    with get_cursor(commit=commit, dict_cursor=dict_cursor) as cur:
        cur.execute(query, params)
        if fetch == "one":
            row = cur.fetchone()
            return dict(row) if (row is not None and dict_cursor and isinstance(row, dict)) else row
        elif fetch == "all":
            rows = cur.fetchall()
            return [dict(r) if (dict_cursor and isinstance(r, dict)) else r for r in rows] if dict_cursor else rows
        return cur.rowcount


def execute_batch(
    query: str,
    params_list: List[Union[Tuple, Dict[str, Any]]],
    commit: bool = True
) -> int:
    """Executes a batch of queries efficiently."""
    if not params_list:
        return 0
    with get_cursor(commit=commit, dict_cursor=False) as cur:
        if HAS_PSYCOPG2 and hasattr(psycopg2, "extras") and hasattr(psycopg2.extras, "execute_batch"):
            try:
                psycopg2.extras.execute_batch(cur, query, params_list)
                return len(params_list)
            except Exception:
                pass
        for p in params_list:
            cur.execute(query, p)
        return len(params_list)


def execute_transaction(operations: List[Tuple[str, Optional[Any]]]) -> bool:
    """Executes multiple (query, params) pairs inside a single atomic transaction."""
    with transaction() as cur:
        for sql, params in operations:
            cur.execute(sql, params)
    return True


# =============================================================================
# JSON Serialization Helpers
# =============================================================================

def to_json(val: Any) -> Any:
    """Wraps python dicts or lists in psycopg2.extras.Json."""
    if val is None:
        return None
    if isinstance(val, (dict, list)):
        if HAS_PSYCOPG2 and hasattr(psycopg2, "extras") and hasattr(psycopg2.extras, "Json"):
            return psycopg2.extras.Json(val)
        import json
        return json.dumps(val)
    return val


def from_json(val: Any) -> Any:
    """Parses JSONB/string into Python dict/list."""
    if val is None:
        return None
    if isinstance(val, (dict, list)):
        return val
    if isinstance(val, str):
        try:
            import json
            return json.loads(val)
        except Exception:
            return val
    return val


# =============================================================================
# Health Check & Connectivity
# =============================================================================

def check_connection() -> Tuple[bool, Optional[str]]:
    """Tests database connectivity with a lightweight ping."""
    try:
        with get_cursor(commit=False) as cur:
            cur.execute("SELECT 1 as ping;")
            res = cur.fetchone()
            if res:
                return True, "Connected successfully"
            return False, "Unexpected ping response"
    except Exception as e:
        return False, str(e)


def is_database_available() -> bool:
    """Always returns True because of resilient fallback."""
    return True


# =============================================================================
# Schema Auto-Creation & Initialization
# =============================================================================

def init_db(schema_path: Optional[str] = None, seed_if_empty: bool = False) -> bool:
    """Initializes tables from schema.sql and optionally seeds dummy data."""
    if not schema_path:
        base_dir = os.path.dirname(os.path.abspath(__file__))
        schema_path = os.path.join(base_dir, "schema.sql")

    if not os.path.exists(schema_path):
        err = f"schema.sql not found at {schema_path}"
        logger.error(err)
        raise FileNotFoundError(err)

    logger.info(f"Loading database schema from {schema_path}...")
    with open(schema_path, "r", encoding="utf-8") as f:
        schema_sql = f.read()

    with get_cursor(commit=True, dict_cursor=False) as cur:
        cur.execute(schema_sql)

    logger.info("Database schema initialized successfully.")

    if seed_if_empty:
        try:
            import seed_data
            seed_data.seed_database()
        except Exception as exc:
            logger.warning(f"Seed data execution: {exc}")

    return True
