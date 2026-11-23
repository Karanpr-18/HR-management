"""
WSGI entrypoint for TalentAI HR Platform.
Suitable for Gunicorn, uWSGI, and other production WSGI servers.
"""
import os
import logging
from dotenv import load_dotenv

# Load environment variables from .env if present
load_dotenv()

# Configure logging
LOG_LEVEL_NAME = os.environ.get('LOG_LEVEL', 'INFO').upper()
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL_NAME, logging.INFO),
    format='[%(asctime)s] %(levelname)s in %(module)s: %(message)s'
)
logger = logging.getLogger("wsgi")

# Initialize PostgreSQL database
try:
    import database
    logger.info("Ensuring PostgreSQL database schema is initialized...")
    database.init_db(seed_if_empty=True)
    logger.info("PostgreSQL database initialized and seeded successfully.")
except Exception as exc:
    logger.warning(f"Database initialization warning on WSGI startup: {exc}")

# Configure logging
LOG_LEVEL_NAME = os.environ.get('LOG_LEVEL', 'INFO').upper()
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL_NAME, logging.INFO),
    format='[%(asctime)s] %(levelname)s in %(module)s: %(message)s'
)
logger = logging.getLogger("wsgi")

# Initialize PostgreSQL database
try:
    import database
    logger.info("Ensuring PostgreSQL database schema is initialized...")
    database.init_db(seed_if_empty=True)
    logger.info("PostgreSQL database initialized and seeded successfully.")
except Exception as exc:
    logger.warning(f"Database initialization warning on WSGI startup: {exc}")

from app import app

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
