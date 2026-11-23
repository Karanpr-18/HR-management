"""
TalentAI HR Platform - Database Access Layer
Robust PostgreSQL connection pooling, transactional helpers, schema management,
and data serialization using psycopg2.
"""

import os
import logging
import threading
from contextlib import contextmanager
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

import psycopg2
import psycopg2.pool
import psycopg2.extras

logger = logging.getLogger("talentai.database")
if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("[%(asctime)s] [%(levelname)s] [database] %(message)s"))
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)

# =============================================================================
# Global Pool & Concurrency Lock
# =============================================================================
_pool: Optional[psycopg2.pool.ThreadedConnectionPool] = None
_pool_lock = threading.Lock()
_mock_connection = None  # Hook for mock connections during unit tests

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
# Connection Pool Management
# =============================================================================

def get_pool(
    minconn: Optional[int] = None,
    maxconn: Optional[int] = None,
    force_reconnect: bool = False
) -> psycopg2.pool.ThreadedConnectionPool:
    """
    Returns the singleton ThreadedConnectionPool instance.
    Initializes lazily and thread-safely on first invocation.
    """
    global _pool

    with _pool_lock:
        if force_reconnect and _pool is not None:
            close_pool()

        if _pool is None:
            min_c = minconn or int(os.environ.get("DB_POOL_MIN", DEFAULT_MIN_CONNECTIONS))
            max_c = maxconn or int(os.environ.get("DB_POOL_MAX", DEFAULT_MAX_CONNECTIONS))
            cfg = get_db_config()
            try:
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
                        connect_timeout=cfg.get("connect_timeout", 10),
                    )
                logger.info(f"Initialized PostgreSQL pool (min={min_c}, max={max_c}) at {get_connection_url()}")
            except Exception as e:
                logger.error(f"Failed to create PostgreSQL connection pool: {e}")
                raise

        return _pool


def close_pool():
    """Safely closes all active connections in the connection pool."""
    global _pool
    with _pool_lock:
        if _pool is not None:
            try:
                _pool.closeall()
                logger.info("Closed PostgreSQL connection pool.")
            except Exception as e:
                logger.warning(f"Error while closing pool: {e}")
            finally:
                _pool = None


def set_mock_connection(conn):
    """Testing hook: allows injecting a mock connection object for testing."""
    global _mock_connection
    _mock_connection = conn


# =============================================================================
# Context Managers & Transaction Helpers
# =============================================================================

@contextmanager
def get_connection():
    """
    Context manager yielding a pooled connection.
    Guarantees that the connection is checked back into the pool.
    """
    global _mock_connection
    if _mock_connection is not None:
        yield _mock_connection
        return

    pool = get_pool()
    conn = pool.getconn()
    try:
        # Register JSONB helpers on the connection
        psycopg2.extras.register_default_jsonb(conn)
        yield conn
    finally:
        pool.putconn(conn)


@contextmanager
def get_cursor(commit: bool = True, dict_cursor: bool = True):
    """
    Context manager yielding a cursor with automated commit and rollback.

    Args:
        commit: If True, commits the transaction upon clean exit.
        dict_cursor: If True, returns rows as RealDictCursor (dict-like objects).
    """
    global _mock_connection
    if _mock_connection is not None:
        cur = _mock_connection.cursor(cursor_factory=psycopg2.extras.RealDictCursor if dict_cursor else None)
        try:
            yield cur
            if commit:
                _mock_connection.commit()
        except Exception:
            _mock_connection.rollback()
            raise
        finally:
            cur.close()
        return

    with get_connection() as conn:
        cursor_factory = psycopg2.extras.RealDictCursor if dict_cursor else None
        cur = conn.cursor(cursor_factory=cursor_factory)
        try:
            yield cur
            if commit:
                conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            cur.close()


@contextmanager
def transaction(dict_cursor: bool = True):
    """
    Context manager dedicated to multi-step transactional operations.
    Commits if all steps succeed; rolls back on any error.
    """
    with get_cursor(commit=True, dict_cursor=dict_cursor) as cur:
        yield cur


def execute_query(
    query: str,
    params: Optional[Union[Sequence, Dict[str, Any]]] = None,
    fetch: Optional[str] = None,
    commit: bool = True,
    dict_cursor: bool = True,
) -> Any:
    """
    Executes a single SQL statement.

    Args:
        query: SQL statement string.
        params: Parameters tuple, list, or dict.
        fetch: None (returns rowcount), 'one' (returns one dict), or 'all' (returns list of dicts).
        commit: Whether to commit after execution.
        dict_cursor: Whether to use RealDictCursor.

    Returns:
        Row dict, list of row dicts, or affected row count.
    """
    with get_cursor(commit=commit, dict_cursor=dict_cursor) as cur:
        cur.execute(query, params)
        if fetch == "one":
            row = cur.fetchone()
            return dict(row) if (row is not None and dict_cursor) else row
        elif fetch == "all":
            rows = cur.fetchall()
            return [dict(r) for r in rows] if dict_cursor else rows
        return cur.rowcount


def execute_batch(
    query: str,
    params_list: List[Union[Tuple, Dict[str, Any]]],
    commit: bool = True
) -> int:
    """
    Executes a batch of queries efficiently using psycopg2.extras.execute_batch.
    """
    if not params_list:
        return 0

    with get_cursor(commit=commit, dict_cursor=False) as cur:
        psycopg2.extras.execute_batch(cur, query, params_list)
        return len(params_list)


def execute_transaction(operations: List[Tuple[str, Optional[Any]]]) -> bool:
    """
    Executes multiple (query, params) pairs inside a single atomic transaction.
    """
    with transaction() as cur:
        for sql, params in operations:
            cur.execute(sql, params)
    return True


# =============================================================================
# JSON Serialization Helpers
# =============================================================================

def to_json(val: Any) -> Any:
    """
    Wraps python dicts or lists in psycopg2.extras.Json for seamless JSONB column inserts.
    Passes primitives or already formatted JSON as is.
    """
    if val is None:
        return None
    if isinstance(val, (dict, list)):
        return psycopg2.extras.Json(val)
    return val


def from_json(val: Any) -> Any:
    """
    Ensures a JSON field is parsed into a Python dict or list.
    """
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
    """
    Tests database connectivity with a lightweight ping.
    Returns:
        (True, "Connected") on success, or (False, error_message) on failure.
    """
    try:
        with get_cursor(commit=False) as cur:
            cur.execute("SELECT 1 as ping;")
            res = cur.fetchone()
            if res and (res.get("ping") == 1 or res[0] == 1):
                return True, "Connected successfully"
            return False, "Unexpected ping response"
    except Exception as e:
        return False, str(e)


def is_database_available() -> bool:
    """Convenience boolean check for database accessibility."""
    ok, _ = check_connection()
    return ok


# =============================================================================
# Schema Auto-Creation & Initialization
# =============================================================================

def init_db(schema_path: Optional[str] = None) -> bool:
    """
    Initializes PostgreSQL tables, indexes, and constraints by running schema.sql.

    Args:
        schema_path: Absolute or relative path to schema.sql.
                     Defaults to schema.sql located alongside database.py.
    """
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
    return True
