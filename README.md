# TalentAI – Smart HR Management System 🚀

A comprehensive AI-powered hiring platform designed to automate and streamline the recruitment process for both HR administrators and job applicants.

*   **Live Demo:** [https://hr-management-app-w6xc.onrender.com/](https://hr-management-e1l5.onrender.com)

[![AI Powered](https://img.shields.io/badge/AI-Powered-blueviolet)](https://gemini.google.com/app)
[![Framework](https://img.shields.io/badge/Framework-Flask-black)](https://flask.palletsprojects.com/)
[![Status](https://img.shields.io/badge/Status-Demo-orange)](#-notes-for-developers)

---

## 🚀 Key Features

### 🏢 For HR Administrators
*   **Secure Admin Portal:** Dedicated login for HR personnel (`hr_admin` / `admin123`).
*   **Centralized Dashboard:** Real-time overview of all active candidates, job positions, and hiring stats.
*   **Job Management:** Full CRUD capabilities (Create, Read, Update, Delete) for job positions.
*   **AI-Powered Resume Analysis:** Automatically parses and analyzes PDF resumes against job descriptions using **Google Gemini Pro**.
*   **Intelligent Scoring:** Candidates are automatically ranked based on:
    *   **Python Proficiency** (50% weight)
    *   **Relevant Experience** (30% weight)
    *   **University Tier/Academic Background** (20% weight)

### 👤 For Applicants
*   **Public Job Board:** Browse all open positions with detailed descriptions without needing an account.
*   **Personal Candidate Dashboard:** Register and login to track the status of all your applications.
*   **Seamless Application:** Simple drag-and-drop PDF upload for resumes.
*   **Application Tracking:** Real-time updates on status: `Pending`, `Accepted`, or `Rejected`.

---

## 🛠️ Technology Stack
*   **Backend:** Python, Flask
*   **AI Engine:** Google Gemini Pro (via `google-genai` SDK) & Groq Llama 3.1 (for fallback/speed)
*   **Data Processing:** Pandas (for dashboard sorting and analytics)
*   **Frontend:** Modern HTML5, CSS3 (Custom design with animations and glassmorphism)
*   **Storage:** JSON-based file storage (optimized for demo portability)

---

## 📦 Installation & Setup

1.  **Clone the repository:**
    ```bash
    git clone https://github.com/Karanpr-18/HR-management-app.git
    cd HR-management-app
    ```

2.  **Create and activate a virtual environment:**
    ```bash
    python -m venv venv
    source venv/bin/activate  # On Windows: venv\Scripts\activate
    ```

3.  **Install dependencies:**
    ```bash
    pip install -r requirements.txt
    ```

4.  **Set up Environment Variables:**
    Create a `.env` file in the root directory and add your API keys:
    ```env
    GOOGLE_API_KEY=your_gemini_key_here
    GROQ_API_KEY=your_groq_key_here
    ```

5.  **Run the application:**
    ```bash
    python app.py
    ```
    Access the application at `http://127.0.0.1:5000`

---

## 🔑 Demo Credentials

| Role | Username | Password |
| :--- | :--- | :--- |
| **HR Admin** | `hr_admin` | `admin123` |
| **Applicant** | *Register your own* | *Register your own* |

---

## ⚠️ Notes for Developers
*   **Demo Purpose:** This is a demonstration application built to showcase AI integration in HR workflows.
*   **Data Persistence:** Currently uses `data.json` for storage. In a production environment, this should be migrated to a robust database like PostgreSQL or MongoDB.
*   **Security:** To simplify the demo, administrative credentials are hardcoded and session keys rotate on restart. Do not use this specific configuration in a production setting.
*   **File Storage:** Uploaded resumes are stored in the local `uploads/` directory.

---
*Developed  for efficient and intelligent hiring.*
