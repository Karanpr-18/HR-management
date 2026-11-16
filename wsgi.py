"""
WSGI entrypoint for TalentAI HR Platform.
Suitable for Gunicorn, uWSGI, and other production WSGI servers.
"""
import os
from dotenv import load_dotenv

# Load environment variables from .env if present
load_dotenv()

from app import app

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
