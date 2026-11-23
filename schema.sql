-- =============================================================================
-- TalentAI HR Platform - PostgreSQL Database Schema
-- Architecture for Candidates CVs, Chat/Timeline, Positions, Employees,
-- Attendance, Leave Requests, Users, and Notifications
-- =============================================================================

-- Enable UUID extension if available
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- =============================================================================
-- 1. POSITIONS TABLE
-- =============================================================================
CREATE TABLE IF NOT EXISTS positions (
    id VARCHAR(64) PRIMARY KEY,
    title VARCHAR(255) NOT NULL,
    description TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_positions_title ON positions(title);

-- =============================================================================
-- 2. USERS TABLE (Authentication & Portals)
-- =============================================================================
CREATE TABLE IF NOT EXISTS users (
    id VARCHAR(64) PRIMARY KEY,
    username VARCHAR(150) UNIQUE NOT NULL,
    password VARCHAR(255) NOT NULL,
    name VARCHAR(255) NOT NULL,
    email VARCHAR(255) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_users_username ON users(username);
CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);

-- =============================================================================
-- 3. CANDIDATE CVS TABLE
-- Primary store for candidate CVs, raw resume text, extracted profile fields,
-- AI ranking scores, skills, attachments, and application metadata.
-- =============================================================================
CREATE TABLE IF NOT EXISTS candidates (
    id VARCHAR(64) PRIMARY KEY,
    position_id VARCHAR(64) REFERENCES positions(id) ON DELETE SET NULL,
    user_id VARCHAR(64) REFERENCES users(id) ON DELETE SET NULL,
    employee_id VARCHAR(64),
    name VARCHAR(255) NOT NULL,
    email VARCHAR(255),
    phone VARCHAR(100),
    university VARCHAR(255),
    status VARCHAR(50) DEFAULT 'pending',
    stage VARCHAR(50) DEFAULT 'Screening',
    job_role VARCHAR(255),
    position VARCHAR(255),
    
    -- CV / Resume Content & Documents
    raw_resume_text TEXT,
    source_file VARCHAR(500),
    analysis_method VARCHAR(100) DEFAULT 'AI Analysis',
    
    -- Numerical Scores (for relational indexing & fast sorting)
    python_score NUMERIC(5, 2) DEFAULT 0.0,
    experience_score NUMERIC(5, 2) DEFAULT 0.0,
    uni_tier_score NUMERIC(5, 2) DEFAULT 0.0,
    final_rank_score NUMERIC(5, 2) DEFAULT 0.0,
    python_experience_years NUMERIC(5, 2) DEFAULT 0.0,
    
    -- JSONB Structured Fields
    -- scores: full breakdown including evidence quotes and detailed sub-metrics
    scores JSONB DEFAULT '{}'::jsonb,
    -- skills: list of technical skills extracted from CV
    skills JSONB DEFAULT '[]'::jsonb,
    -- parsed_data: full structured parse results from LLM / parser
    parsed_data JSONB DEFAULT '{}'::jsonb,
    -- attachments: list of uploaded documents, CV files, portfolios
    attachments JSONB DEFAULT '[]'::jsonb,
    -- interview: active interview details, schedule, reschedule requests
    interview JSONB DEFAULT '{}'::jsonb,
    -- interview_rounds: history of all interview rounds
    interview_rounds JSONB DEFAULT '[]'::jsonb,
    
    -- Timestamps
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_candidates_position_id ON candidates(position_id);
CREATE INDEX IF NOT EXISTS idx_candidates_user_id ON candidates(user_id);
CREATE INDEX IF NOT EXISTS idx_candidates_email ON candidates(email);
CREATE INDEX IF NOT EXISTS idx_candidates_status ON candidates(status);
CREATE INDEX IF NOT EXISTS idx_candidates_stage ON candidates(stage);
CREATE INDEX IF NOT EXISTS idx_candidates_final_rank_score ON candidates(final_rank_score DESC);
CREATE INDEX IF NOT EXISTS idx_candidates_created_at ON candidates(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_candidates_skills ON candidates USING GIN (skills);
CREATE INDEX IF NOT EXISTS idx_candidates_scores ON candidates USING GIN (scores);
CREATE INDEX IF NOT EXISTS idx_candidates_parsed_data ON candidates USING GIN (parsed_data);
CREATE INDEX IF NOT EXISTS idx_candidates_attachments ON candidates USING GIN (attachments);

-- =============================================================================
-- 4. CHAT THREADS & CANDIDATE TIMELINE TABLE
-- Stores full conversational history, candidate messages, recruiter notes,
-- timeline progression events, interview interactions, and message attachments.
-- =============================================================================
CREATE TABLE IF NOT EXISTS candidate_timeline (
    id VARCHAR(64) PRIMARY KEY,
    candidate_id VARCHAR(64) NOT NULL REFERENCES candidates(id) ON DELETE CASCADE,
    sender VARCHAR(50) NOT NULL,            -- 'candidate' | 'hr' | 'system' | 'team_lead'
    sender_name VARCHAR(255) NOT NULL,
    type VARCHAR(50) NOT NULL,              -- 'message' | 'internal_note' | 'interview' | 'reschedule' | 'stage_change' | 'system'
    content TEXT NOT NULL,
    metadata JSONB DEFAULT '{}'::jsonb,     -- Extra payload, source files, reschedule reasons
    attachments JSONB DEFAULT '[]'::jsonb,  -- Array of file attachment objects
    timestamp TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_timeline_candidate_id ON candidate_timeline(candidate_id);
CREATE INDEX IF NOT EXISTS idx_timeline_timestamp ON candidate_timeline(timestamp ASC);
CREATE INDEX IF NOT EXISTS idx_timeline_type ON candidate_timeline(type);
CREATE INDEX IF NOT EXISTS idx_timeline_sender ON candidate_timeline(sender);
CREATE INDEX IF NOT EXISTS idx_timeline_metadata ON candidate_timeline USING GIN (metadata);
CREATE INDEX IF NOT EXISTS idx_timeline_attachments ON candidate_timeline USING GIN (attachments);

-- =============================================================================
-- 5. EMPLOYEES TABLE
-- Stores organizational directory, RBAC access roles, team lead hierarchy,
-- compensation, and annual leave quotas & balances.
-- =============================================================================
CREATE TABLE IF NOT EXISTS employees (
    id VARCHAR(64) PRIMARY KEY,             -- e.g. 'EMP-1001'
    candidate_id VARCHAR(64) REFERENCES candidates(id) ON DELETE SET NULL,
    user_id VARCHAR(64) REFERENCES users(id) ON DELETE SET NULL,
    name VARCHAR(255) NOT NULL,
    email VARCHAR(255) UNIQUE NOT NULL,
    phone VARCHAR(100),
    role VARCHAR(255) NOT NULL,
    department VARCHAR(255) NOT NULL,
    date_of_joining DATE DEFAULT CURRENT_DATE,
    status VARCHAR(50) DEFAULT 'Active',
    password VARCHAR(255) NOT NULL,
    access_role VARCHAR(50) DEFAULT 'employee',  -- 'employee' | 'team_lead' | 'hr_admin'
    team_lead_id VARCHAR(64) REFERENCES employees(id) ON DELETE SET NULL,
    
    -- JSONB Structured Compensation & Leave Data
    salary JSONB DEFAULT '{"base": 0, "allowances": 0, "deductions": 0, "net": 0, "currency": "$", "payment_cycle": "Monthly", "status": "Paid"}'::jsonb,
    leave_quota JSONB DEFAULT '{"casual": 12, "yearly": 15}'::jsonb,
    leave_balance JSONB DEFAULT '{"casual": 12, "yearly": 15, "casual_used": 0, "yearly_used": 0, "casual_pending": 0, "yearly_pending": 0}'::jsonb,
    
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_employees_email ON employees(email);
CREATE INDEX IF NOT EXISTS idx_employees_access_role ON employees(access_role);
CREATE INDEX IF NOT EXISTS idx_employees_team_lead_id ON employees(team_lead_id);
CREATE INDEX IF NOT EXISTS idx_employees_department ON employees(department);
CREATE INDEX IF NOT EXISTS idx_employees_status ON employees(status);

-- =============================================================================
-- 6. ATTENDANCE TABLE
-- Daily employee clock-in, clock-out, total work hours, and statuses.
-- =============================================================================
CREATE TABLE IF NOT EXISTS attendance (
    id VARCHAR(64) PRIMARY KEY,
    employee_id VARCHAR(64) NOT NULL REFERENCES employees(id) ON DELETE CASCADE,
    employee_name VARCHAR(255),
    date DATE NOT NULL,
    clock_in VARCHAR(50),
    clock_out VARCHAR(50),
    total_hours NUMERIC(5, 2) DEFAULT 0.0,
    status VARCHAR(50) DEFAULT 'Present',   -- 'Present' | 'On Leave' | 'Late' | 'Absent'
    notes TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_employee_date UNIQUE (employee_id, date)
);

CREATE INDEX IF NOT EXISTS idx_attendance_employee_id ON attendance(employee_id);
CREATE INDEX IF NOT EXISTS idx_attendance_date ON attendance(date DESC);
CREATE INDEX IF NOT EXISTS idx_attendance_employee_date ON attendance(employee_id, date);

-- =============================================================================
-- 7. LEAVE REQUESTS TABLE
-- Multi-tier workflow: Employee -> Team Lead Review -> HR Review & Classification
-- =============================================================================
CREATE TABLE IF NOT EXISTS leave_requests (
    id VARCHAR(64) PRIMARY KEY,
    employee_id VARCHAR(64) NOT NULL REFERENCES employees(id) ON DELETE CASCADE,
    employee_name VARCHAR(255) NOT NULL,
    employee_role VARCHAR(255),
    department VARCHAR(255),
    leave_type VARCHAR(100) NOT NULL,        -- 'Casual Leave', 'Yearly Leave', 'Mixed (...)', etc.
    start_date DATE NOT NULL,
    end_date DATE NOT NULL,
    days INTEGER NOT NULL DEFAULT 1,
    reason TEXT,
    status VARCHAR(50) DEFAULT 'pending_lead', -- 'pending_lead' | 'pending_hr' | 'approved' | 'rejected'
    allocation_year INTEGER NOT NULL,
    
    -- Team Lead assignment & review
    assigned_team_lead_id VARCHAR(64),
    assigned_team_lead_name VARCHAR(255),
    casual_days INTEGER DEFAULT 0,
    yearly_days INTEGER DEFAULT 0,
    lead_reviewer_id VARCHAR(64),
    lead_reviewed_by VARCHAR(255),
    lead_reviewed_at TIMESTAMP WITH TIME ZONE,
    lead_remarks TEXT,
    
    -- HR review & conversion
    reviewed_by VARCHAR(255),
    reviewed_at TIMESTAMP WITH TIME ZONE,
    remarks TEXT,
    hr_type_override BOOLEAN DEFAULT FALSE,
    conversion_history JSONB DEFAULT '[]'::jsonb,
    
    submitted_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_leave_requests_employee_id ON leave_requests(employee_id);
CREATE INDEX IF NOT EXISTS idx_leave_requests_status ON leave_requests(status);
CREATE INDEX IF NOT EXISTS idx_leave_requests_allocation_year ON leave_requests(allocation_year);
CREATE INDEX IF NOT EXISTS idx_leave_requests_assigned_lead ON leave_requests(assigned_team_lead_id);
CREATE INDEX IF NOT EXISTS idx_leave_requests_dates ON leave_requests(start_date, end_date);

-- =============================================================================
-- 8. NOTIFICATIONS TABLE
-- Real-time and persistent alerts across candidates, team leads, employees, HR
-- =============================================================================
CREATE TABLE IF NOT EXISTS notifications (
    id VARCHAR(64) PRIMARY KEY,
    recipient_type VARCHAR(50) NOT NULL,     -- 'employee' | 'hr' | 'user' | 'candidate'
    recipient_id VARCHAR(64) NOT NULL,
    title VARCHAR(255) NOT NULL,
    message TEXT NOT NULL,
    link VARCHAR(500) DEFAULT '',
    notification_type VARCHAR(50) DEFAULT 'info', -- 'info' | 'success' | 'warning' | 'danger'
    read BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_notifications_recipient ON notifications(recipient_type, recipient_id, read);
CREATE INDEX IF NOT EXISTS idx_notifications_created_at ON notifications(created_at DESC);

-- =============================================================================
-- 9. APP SETTINGS / GLOBAL CONFIGURATION
-- Key-value persistent store (e.g. default job description, system toggles)
-- =============================================================================
CREATE TABLE IF NOT EXISTS app_settings (
    key VARCHAR(100) PRIMARY KEY,
    value TEXT,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);
