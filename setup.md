# 🚀 AI Resume Ranking Dashboard - Setup Guide

A step-by-step guide to set up and run the AI-powered Resume Ranking Dashboard.

---

## 📋 Table of Contents

1. [Prerequisites](#prerequisites)
2. [Clone the Repository](#clone-the-repository)
3. [Set Up Python Environment](#set-up-python-environment)
4. [Install Dependencies](#install-dependencies)
5. [Configure Environment Variables](#configure-environment-variables)
6. [Verify Installation](#verify-installation)
7. [Run the Application](#run-the-application)
8. [Troubleshooting](#troubleshooting)

---

## ✅ Prerequisites

Before you begin, ensure you have the following installed:

| Requirement | Minimum Version | Maximum Version | Description |
|-------------|-----------------|-----------------|-------------|
| **Python** | 3.10 | 3.13 | Core programming language (3.14 NOT supported) |
| **pip** | 21.0+ | Latest | Package installer for Python |
| **Git** | 2.0+ | Latest | Version control (optional) |
| **Web Browser** | Latest | Latest | Chrome, Firefox, or Edge |

### Check Your Python Version

```bash
python --version
# Should output: Python 3.10.x - 3.13.x (NOT 3.14+)
```

> ⚠️ **Important**: Python 3.14 is NOT yet supported by google-generativeai library. Use Python 3.10, 3.11, 3.12, or 3.13.

### Install Python (if needed)

**Ubuntu/Debian:**
```bash
sudo apt update
sudo apt install python3.10 python3-pip python3-venv
```

**macOS:**
```bash
brew install python@3.10
```

**Windows:**
Download from [python.org](https://www.python.org/downloads/)

---

## 📦 Clone the Repository

```bash
# Clone the repository (if using Git)
git clone <repository-url>
cd resume-ranking-app

# OR download and extract the source code manually
```

---

## 🐍 Set Up Python Environment

It's recommended to use a virtual environment to isolate project dependencies.

### Create Virtual Environment

```bash
# Create a new virtual environment
python -m venv venv

# Activate the virtual environment
# On Linux/macOS:
source venv/bin/activate

# On Windows:
venv\Scripts\activate
```

### Verify Virtual Environment

```bash
# You should see (venv) at the beginning of your terminal prompt
which python
# Should point to: /path/to/resume-ranking-app/venv/bin/python
```

> **Note:** Always activate the virtual environment before working on the project.

---

## 📥 Install Dependencies

```bash
# Upgrade pip to the latest version
pip install --upgrade pip

# Install all project dependencies
pip install -r requirements.txt
```

### Expected Output

```
Successfully installed Flask-3.0.0 google-generativeai-0.3.0 python-dotenv-1.0.0 gunicorn-21.2.0
```

### Individual Package Installation (Optional)

If you prefer to install packages manually:

```bash
pip install flask==3.0.0
pip install google-generativeai==0.3.0
pip install python-dotenv==1.0.0
pip install gunicorn==21.2.0
```

---

## ⚙️ Configure Environment Variables

### Step 1: Create Environment File

```bash
# Copy the example environment file
cp .env.example .env

# On Windows (Command Prompt):
copy .env.example .env

# On Windows (PowerShell):
Copy-Item .env.example .env
```

### Step 2: Edit the Environment File

Open `.env` in your preferred text editor and configure the following:

```bash
# =============================================================================
# REQUIRED: Google Gemini API Key
# =============================================================================
# Get your API key from: https://aistudio.google.com/app/apikey
GEMINI_API_KEY=your-gemini-api-key-here

# =============================================================================
# OPTIONAL: Server Configuration
# =============================================================================
PORT=5000
DEBUG=false

# =============================================================================
# OPTIONAL: AI Configuration
# =============================================================================
GEMINI_MODEL=gemini-pro
GEMINI_MAX_TOKENS=500
GEMINI_TEMPERATURE=0.3

# =============================================================================
# OPTIONAL: Feature Toggles
# =============================================================================
USE_AI_ANALYSIS=true
ENABLE_BATCH_PROCESSING=true
```

### Step 3: Get Your Gemini API Key

1. Go to [Google AI Studio](https://aistudio.google.com/app/apikey)
2. Sign in with your Google account
3. Click "Create API Key"
4. Copy the generated key
5. Paste it in your `.env` file as `GEMINI_API_KEY`

> **Note:** The API key is free for personal use within quota limits. See [Google AI Studio pricing](https://aistudio.google.com/pricing) for details.

---

## ✅ Verify Installation

Run these commands to verify your setup:

### 1. Check Python Packages

```bash
pip list
```

Expected output:
```
Package             Version
------------------- --------
Flask               3.0.0
google-generativeai 0.3.0
gunicorn            21.2.0
python-dotenv       1.0.0
```

### 2. Check Environment Variables

```bash
# On Linux/macOS:
source .env && echo $GEMINI_API_KEY

# On Windows (Command Prompt):
type .env | findstr GEMINI_API_KEY
```

### 3. Run Tests (Optional)

```bash
# Run the test suite
python -m pytest test_agent.py -v
```

---

## 🚀 Run the Application

### Development Mode

```bash
# Start the Flask development server
python app.py
```

Expected output:
```
* Running on http://0.0.0.0:5000
* Debug mode: off
```

### Production Mode (using Gunicorn)

```bash
# Start with Gunicorn (production WSGI server)
gunicorn -w 4 -b 0.0.0.0:5000 app:app
```

### Access the Dashboard

Open your web browser and navigate to:

```
http://localhost:5000
```

You should see the AI Resume Ranking Dashboard interface.

---

## 📡 API Endpoints

Once the application is running, you can access these endpoints:

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | Dashboard UI |
| `/api/health` | GET | Health check |
| `/api/analyze` | POST | Analyze single resume |
| `/api/batch-analyze` | POST | Analyze multiple resumes |
| `/api/ranking` | POST | Rank candidates |

### Example API Usage

```bash
# Health check
curl http://localhost:5000/api/health

# Analyze a resume
curl -X POST http://localhost:5000/api/analyze \
  -H "Content-Type: application/json" \
  -d '{"resume_text": "Your resume text here"}'
```

---

## 🔧 Troubleshooting

### Common Issues and Solutions

#### 1. `ModuleNotFoundError: No module named 'flask'`

**Solution:** Activate virtual environment and reinstall dependencies

```bash
source venv/bin/activate  # Linux/macOS
# or: venv\Scripts\activate  # Windows
pip install -r requirements.txt
```

#### 2. `ImportError: libglib2.0-0 not found` (Linux)

**Solution:** Install missing system library

```bash
sudo apt-get install libglib2.0-0
```

#### 3. API Key Error

**Solution:** Verify your `.env` file contains the correct API key

```bash
cat .env | grep GEMINI_API_KEY
```

#### 4. Port Already in Use

**Solution:** Change the port or kill the process using port 5000

```bash
# Find process using port 5000
lsof -i :5000

# Kill the process
kill <PID>

# OR use a different port
PORT=5001 python app.py
```

#### 5. Gemini API Quota Exceeded

**Solution:** 
- Check your usage at [Google AI Studio](https://aistudio.google.com)
- The application will automatically fall back to rule-based analysis
- Wait for quota reset (typically daily)

#### 6. File Upload Errors

**Solution:** Check file size limits (max 16MB)

```bash
# Increase limit in .env
MAX_CONTENT_LENGTH=32000000  # 32MB
```

#### 7. Python 3.14 Compatibility Error

**Error:**
```
TypeError: Metaclasses with custom tp_new are not supported.
```

**Solution:** Python 3.14 is not yet supported by google-generativeai library. Use Python 3.10-3.13:

```bash
# Check current Python version
python --version

# If using Python 3.14, install an older version:
# Ubuntu/Debian:
sudo apt install python3.12 python3.12-venv python3.12-dev

# macOS:
brew install python@3.12

# Create new virtual environment with Python 3.12
python3.12 -m venv venv
source venv/bin/activate

# Reinstall dependencies
pip install -r requirements.txt
```

---

## 📁 Project Structure

```
resume-ranking-app/
├── app.py              # Flask application entry point
├── agent.py            # AI Resume Ranking Agent
├── test_agent.py       # Unit tests
├── requirements.txt    # Python dependencies
├── .env.example        # Environment template
├── .env                # Your environment config (create this)
├── README.md           # Project documentation
├── setup.md            # This setup guide
├── uploads/            # Uploaded resume files
├── templates/
│   └── index.html      # Dashboard UI template
└── static/
    ├── css/
    │   └── style.css   # Dashboard styles
    └── js/
        └── app.js      # Frontend JavaScript
```

---

## 🔒 Security Best Practices

1. **Never commit `.env` to version control**
2. **Rotate API keys periodically**
3. **Use HTTPS in production**
4. **Validate file uploads**
5. **Implement rate limiting for API endpoints**

---

## 📚 Additional Resources

- [Flask Documentation](https://flask.palletsprojects.com)
- [Google Gemini API Docs](https://ai.google.dev/docs)
- [Python-dotenv Documentation](https://pypi.org/project/python-dotenv/)
- [Gunicorn Documentation](https://docs.gunicorn.org)

---

## ✅ Setup Complete!

You're now ready to use the AI Resume Ranking Dashboard. 

**Next steps:**
1. Open http://localhost:5000 in your browser
2. Upload resumes or paste resume text
3. Analyze and rank candidates

**Need help?** Check the [README.md](README.md) or open an issue in the repository.

---

*Last Updated: February 2025*
*Version: 1.0.0*

