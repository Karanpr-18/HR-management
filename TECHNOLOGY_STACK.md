# 🚀 Technology Stack & API Configuration

## Overview
AI-powered Resume Ranking Dashboard for technical recruitment using AI to analyze and rank candidates against job requirements.

---

## 🛠️ Technology Stack

### Backend Technologies

#### **Python 3.10+** 
- **Purpose**: Core programming language
- **Why**: Excellent for AI/ML applications, rich ecosystem of libraries
- **Role**: Server-side logic, AI processing, API handling
- **⚠️ Note**: Python 3.14 is NOT supported by google-generativeai. Use 3.10-3.13.

#### **Flask 3.0.0**
- **Purpose**: Web Framework
- **Why**: Lightweight, flexible, easy to set up for REST APIs
- **Role**: 
  - HTTP request handling
  - API endpoint management
  - Template rendering for UI
  - Request/response processing
- **Key Features Used**:
  - `@app.route()` decorators for routing
  - `request.get_json()` for JSON parsing
  - `jsonify()` for API responses
  - `render_template()` for HTML rendering

#### **Google Gemini API (Python)**
- **Purpose**: AI-powered resume analysis
- **Why**: Access to Gemini Pro for advanced NLP understanding, cost-effective
- **Role**:
  - AI-enhanced resume parsing
  - Contextual understanding of skills
  - Detailed candidate evaluation
- **Key Features**:
  - `genai` library integration
  - `GenerativeModel` for text analysis
  - Multimodal capabilities

#### **Gunicorn 21.2.0**
- **Purpose**: WSGI HTTP Server
- **Why**: Production-ready, handles multiple workers
- **Role**:
  - Running the Flask application in production
  - Managing worker processes
  - Load balancing requests

---

### Frontend Technologies

#### **HTML5**
- **Purpose**: Page structure
- **Why**: Semantic markup, cross-browser compatible
- **Role**: Dashboard layout, form inputs, result display

#### **CSS3**
- **Purpose**: Styling
- **Why**: Modern features, responsive design
- **Role**:
  - Dashboard aesthetics
  - Responsive layout
  - Visual feedback (loading states, results)

#### **JavaScript (ES6+)**
- **Purpose**: Client-side interactivity
- **Why**: Rich ecosystem, async/await support
- **Role**:
  - API calls to backend
  - Dynamic content updates
  - Form handling
  - Results visualization

---

### Supporting Libraries

#### **python-dotenv 1.0.0**
- **Purpose**: Environment variable management
- **Why**: Secure configuration, environment separation
- **Role**: Loading `.env` file variables
- **Usage**: `from dotenv import load_dotenv`

#### **Werkzeug 3.1.5**
- **Purpose**: WSGI utilities
- **Why**: Security, file handling utilities
- **Role**:
  - Secure filename handling
  - File upload processing
  - WSGI compatibility

#### **Jinja2 3.1.6**
- **Purpose**: Template engine
- **Why**: Flask's default, powerful templating
- **Role**: HTML template rendering with dynamic data

#### **itsdangerous 2.2.0**
- **Purpose**: Data serialization
- **Why**: Secure session handling
- **Role**: Flask session management

#### **Other Dependencies**:
- `click` - Command-line interface
- `blinker` - Signal dispatching
- `anyio` - Async I/O support
- `httpx` - HTTP client
- `pydantic` - Data validation
- `distro` - Linux distribution info
- `tqdm` - Progress bars

---

## 🔑 Required API Keys

### **Google Gemini API Key** (PRIMARY)
- **Environment Variable**: `GEMINI_API_KEY`
- **Required For**: AI-powered resume analysis
- **Where to Get**: https://aistudio.google.com/app/apikey
- **Pricing**: Free tier available, pay-per-use after limits
- **Alternative**: Optional - falls back to rule-based analysis if not provided
- **Security**: 
  - NEVER commit to version control
  - Use `.env` file for local development
  - Rotate keys regularly

### **Optional API Keys** (For Future Enhancement)

#### LinkedIn API (Profile enrichment)
- **Variable**: `LINKEDIN_CLIENT_ID`, `LINKEDIN_CLIENT_SECRET`
- **Purpose**: Candidate profile enhancement
- **Get**: https://developer.linkedin.com

#### GitHub API (Code portfolio analysis)
- **Variable**: `GITHUB_TOKEN`
- **Purpose**: Analyze candidate's GitHub repositories
- **Get**: https://github.com/settings/tokens

---

## ⚙️ Configuration

### Environment Variables

Create a `.env` file in the project root:

```bash
# Required
GEMINI_API_KEY=your-gemini-api-key-here

# Optional - Server Configuration
PORT=5000
DEBUG=false

# Optional - AI Configuration
GEMINI_MODEL=gemini-pro
GEMINI_MAX_TOKENS=500
GEMINI_TEMPERATURE=0.3

# Optional - Feature Toggles
USE_AI_ANALYSIS=true
ENABLE_BATCH_PROCESSING=true
```

### Configuration Priority
1. Environment variables (highest priority)
2. `.env` file
3. Default values in code

---

## 📦 Dependency Management

### Core Dependencies (`requirements.txt`)
```
flask==3.0.0
google-generativeai==0.3.0
python-dotenv==1.0.0
gunicorn==21.2.0
```

### Development Dependencies (Optional)
```bash
pytest==7.4.0          # Testing
pytest-cov==4.1.0      # Coverage reports
black==23.9.0          # Code formatting
flake8==6.1.0          # Linting
```

---

## 🏗️ Architecture Overview

```
┌─────────────────────────────────────────────────────┐
│                  Frontend Layer                      │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  │
│  │   HTML5     │  │    CSS3     │  │ JavaScript  │  │
│  │  Templates  │  │   Styles    │  │    (ES6+)   │  │
│  └─────────────┘  └─────────────┘  └─────────────┘  │
└────────────────────────┬────────────────────────────┘
                         │ HTTP Requests
┌────────────────────────▼────────────────────────────┐
│                  Flask Application                   │
│  ┌─────────────────────────────────────────────┐    │
│  │              API Endpoints                   │    │
│  │  POST /api/analyze      - Single Resume     │    │
│  │  POST /api/batch-analyze - Multiple Resumes │    │
│  │  POST /api/ranking      - Rank Candidates   │    │
│  │  GET  /api/health       - Health Check      │    │
│  └─────────────────────────────────────────────┘    │
└────────────────────────┬────────────────────────────┘
                         │
┌────────────────────────▼────────────────────────────┐
│                 Agent Layer                          │
│  ┌─────────────────────────────────────────────┐    │
│  │            ResumeRankingAgent               │    │
│  │  ┌─────────────┐  ┌─────────────────────┐   │    │
│  │  │ Rule-Based  │  │   AI-Powered        │   │    │
│  │  │ Analysis    │  │   (Gemini Pro)      │   │    │
│  │  └─────────────┘  └─────────────────────┘   │    │
│  └─────────────────────────────────────────────┘    │
└────────────────────────┬────────────────────────────┘
                         │
┌────────────────────────▼────────────────────────────┐
│                 Scoring Engine                       │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  │
│  │   Python    │  │ University  │  │  Experience │  │
│  │   Score     │  │    Tier     │  │    Score    │  │
│  │   (40%)     │  │   (25%)     │  │    (25%)    │  │
│  └─────────────┘  └─────────────┘  └─────────────┘  │
└─────────────────────────────────────────────────────┘
```

---

## 🔒 Security Best Practices

1. **API Keys**
   - Never commit keys to version control
   - Use `.env` files (already in `.gitignore`)
   - Rotate keys periodically
   - Use restricted keys with minimal permissions

2. **File Uploads**
   - Validate file types and sizes
   - Use `secure_filename()` to prevent path traversal
   - Store uploads in isolated directory
   - Set `MAX_CONTENT_LENGTH` limit

3. **API Endpoints**
   - Implement rate limiting (recommended)
   - Add authentication for production
   - Validate all input data
   - Use HTTPS in production

---

## 📊 Scoring Algorithm

### Weights
- **Python Skills**: 40%
- **University Tier**: 25%
- **Experience Impact**: 25%
- **Years of Experience**: 10%

### University Tier Scoring
| Tier | Score | Examples |
|------|-------|----------|
| Global Top | 10 | Stanford, MIT, IITs, Ivy League |
| Leading National | 8 | NITs, CMU, ETH Zurich, NUS |
| Standard | 5 | Other universities |

### Python Score Criteria
| Level | Score | Criteria |
|-------|-------|----------|
| Expert | 8-10 | Core libraries, complex architecture |
| Intermediate | 5-7 | Basic scripting, Pandas |
| Beginner | 1-4 | Basic mention |

---

## 🚀 Quick Start

```bash
# 1. Create virtual environment
python -m venv venv
source venv/bin/activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Configure environment
cp .env.example .env
# Edit .env and add your GEMINI_API_KEY

# 4. Run development server
python app.py

# 5. Access at http://localhost:5000
```

---

## 📞 Support & Resources

- **Flask Docs**: https://flask.palletsprojects.com
- **Gemini API Docs**: https://ai.google.dev/docs
- **Python Docs**: https://docs.python.org
- **Project Issues**: Check GitHub repository

---

*Last Updated: February 2025*
*Version: 1.0.0*

