from flask import Flask, render_template, request, jsonify, redirect, url_for, flash, session, send_from_directory
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
from dotenv import load_dotenv
import os
import json
import logging
import re
import uuid
from datetime import datetime
import pandas as pd
from agent import analyze_resume
import storage
import notification_service
from pdf_utils import extract_text_from_pdf

# Load environment variables
load_dotenv()

# Configure structured logging
LOG_LEVEL_NAME = os.environ.get('LOG_LEVEL', 'INFO').upper()
LOG_LEVEL = getattr(logging, LOG_LEVEL_NAME, logging.INFO)
logging.basicConfig(
    level=LOG_LEVEL,
    format='[%(asctime)s] %(levelname)s in %(module)s: %(message)s'
)

app = Flask(__name__, template_folder='templates', static_folder='static')

# Authentication Decorators
def hr_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('is_hr'):
            if request.is_json:
                return jsonify({"success": False, "error": "HR authentication required."}), 403
            flash('Please login as HR to access this page.', 'error')
            return redirect(url_for('hr_login'))
        return f(*args, **kwargs)
    return decorated_function

def applicant_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('user_id'):
            flash('Please login to access this page.', 'error')
            return redirect(url_for('applicant_login'))
        return f(*args, **kwargs)
    return decorated_function

def employee_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        emp_id = session.get('employee_id')
        if not emp_id:
            if request.is_json:
                return jsonify({"success": False, "error": "Employee authentication required."}), 401
            flash('Please log in as an employee to access your portal.', 'info')
            return redirect(url_for('employee_login'))
        emp = storage.get_employee(emp_id)
        if not emp:
            session.pop('employee_id', None)
            session.pop('access_role', None)
            if request.is_json:
                return jsonify({"success": False, "error": "Employee profile not found."}), 401
            flash('Employee profile not found. Please log in again.', 'error')
            return redirect(url_for('employee_login'))
        session['access_role'] = emp.get('access_role', 'employee')
        return f(*args, **kwargs)
    return decorated_function

def team_lead_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        emp_id = session.get('employee_id')
        if not emp_id:
            if request.is_json:
                return jsonify({"success": False, "error": "Authentication required."}), 401
            flash('Please log in to access Team Lead tools.', 'info')
            return redirect(url_for('employee_login'))
        emp = storage.get_employee(emp_id)
        if not emp or emp.get('access_role') != 'team_lead':
            if emp:
                session['access_role'] = emp.get('access_role', 'employee')
            if request.is_json:
                return jsonify({"success": False, "error": "Team Lead role required."}), 403
            flash('Access denied: Team Lead permissions required for this action.', 'error')
            return redirect(url_for('employee_dashboard'))
        session['access_role'] = 'team_lead'
        return f(*args, **kwargs)
    return decorated_function

# ============ Auth Routes ============

@app.route('/hr_login', methods=['GET', 'POST'])
def hr_login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        # Hardcoded HR credentials
        if username == 'hr_admin' and password == 'admin123':
            session['is_hr'] = True
            flash('Welcome back, HR Admin!', 'success')
            return redirect(url_for('overview'))
        else:
            flash('Invalid credentials.', 'error')
            
    return render_template('hr_login.html')

@app.route('/applicant_register', methods=['GET', 'POST'])
def applicant_register():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        name = request.form.get('name')
        email = request.form.get('email')
        
        if not username or not password or not name:
            flash('Please fill in all required fields.', 'error')
            return render_template('applicant_register.html')
            
        # Hash password (simple simulation)
        hashed_pw = generate_password_hash(password)
        
        user_id = storage.create_user(username, hashed_pw, name, email)
        if user_id:
            session['user_id'] = user_id
            session['user_name'] = name
            flash('Account created successfully! Welcome.', 'success')
            return redirect(url_for('applicant_dashboard'))
        else:
            flash('Username already exists. Please choose another.', 'error')
            
    return render_template('applicant_register.html')

@app.route('/applicant_login', methods=['GET', 'POST'])
def applicant_login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        user = storage.get_user_by_username(username)
        if user and check_password_hash(user['password'], password):
            session['user_id'] = user['id']
            session['user_name'] = user['name']
            flash(f"Welcome back, {user['name']}!", 'success')
            return redirect(url_for('applicant_dashboard'))
        else:
            flash('Invalid username or password.', 'error')
            
    return render_template('applicant_login.html')

@app.route('/logout')
def logout():
    session.clear()
    flash('You have been logged out.', 'success')
    return redirect(url_for('index'))

@app.route('/applicant_dashboard')
@applicant_required
def applicant_dashboard():
    user_id = session.get('user_id')
    user = storage.get_user_by_id(user_id)
    candidates = storage.get_candidates_by_user(user_id)
    
    # Enrich with position details
    applications = []
    for c in candidates:
        pos = storage.get_position(c.get('position_id'))
        applications.append({
            'candidate': c,
            'position': pos
        })
        
    return render_template('applicant_dashboard.html', user=user, applications=applications)

# Configure upload folder and limits
UPLOAD_FOLDER = os.environ.get('UPLOAD_FOLDER', os.path.join(os.path.dirname(os.path.abspath(__file__)), 'uploads'))
ALLOWED_EXTENSIONS = {'pdf'}
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(os.path.join(UPLOAD_FOLDER, 'attachments'), exist_ok=True)

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
try:
    app.config['MAX_CONTENT_LENGTH'] = int(os.environ.get('MAX_CONTENT_LENGTH', 16 * 1024 * 1024))
except (ValueError, TypeError):
    app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024

# Session Secret Key & Security Settings
secret_key_env = os.environ.get('SECRET_KEY')
if secret_key_env:
    app.secret_key = secret_key_env
else:
    app.secret_key = "talentai-default-secret-key-change-in-production"
    if os.environ.get('FLASK_ENV') == 'production':
        logging.warning("SECRET_KEY environment variable is not set; using fallback secret key.")

app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
if os.environ.get('COOKIE_SECURE', 'false').lower() in ('true', '1'):
    app.config['SESSION_COOKIE_SECURE'] = True

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# Chat file attachments configuration & helper
CHAT_ALLOWED_EXTENSIONS = {'pdf', 'doc', 'docx', 'txt', 'png', 'jpg', 'jpeg', 'webp', 'gif', 'zip', 'xlsx', 'csv'}

def save_chat_attachment(file_obj):
    """Saves uploaded chat file into uploads/attachments/ and returns metadata dictionary"""
    if not file_obj or not file_obj.filename:
        return None
    
    filename = secure_filename(file_obj.filename)
    if not filename:
        filename = f"attachment_{int(datetime.now().timestamp())}"
    
    ext = filename.rsplit('.', 1)[1].lower() if '.' in filename else ''
    if ext not in CHAT_ALLOWED_EXTENSIONS:
        return {'error': f"File format '.{ext}' is not supported. Supported: PDF, Word (DOC/DOCX), Text, Images, Zip, Excel."}
    
    attachments_dir = os.path.join(app.config['UPLOAD_FOLDER'], 'attachments')
    os.makedirs(attachments_dir, exist_ok=True)
    
    unique_prefix = uuid.uuid4().hex[:10]
    saved_filename = f"{unique_prefix}_{filename}"
    file_path = os.path.join(attachments_dir, saved_filename)
    file_obj.save(file_path)
    
    size_bytes = os.path.getsize(file_path)
    if size_bytes < 1024:
        size_str = f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        size_str = f"{size_bytes / 1024:.1f} KB"
    else:
        size_str = f"{size_bytes / (1024 * 1024):.1f} MB"
        
    return {
        'filename': filename,
        'saved_filename': saved_filename,
        'file_url': f"/uploads/attachments/{saved_filename}",
        'file_size': size_str,
        'file_type': ext
    }

@app.route('/uploads/attachments/<filename>')
def serve_chat_attachment(filename):
    """Serve uploaded chat attachments securely"""
    attachments_dir = os.path.join(app.config['UPLOAD_FOLDER'], 'attachments')
    return send_from_directory(attachments_dir, filename)

@app.route('/')
def index():
    """Route: Landing Page (New Homepage)"""
    return render_template('landing.html')



@app.route('/overview')
@hr_required
def overview():
    """Route: Overview Dashboard (Default Employer Page)"""
    stats = storage.get_overview_stats()
    pending_reschedules = storage.get_pending_reschedules()
    return render_template('overview.html', stats=stats, pending_reschedules=pending_reschedules)

@app.route('/employer')
@hr_required
def employer_portal():
    """Route: Employer Portal - Job Context with Positions"""
    positions = storage.get_all_positions()
    selected_id = request.args.get('selected')
    selected_position = None
    if selected_id:
        selected_position = storage.get_position(selected_id)
    return render_template('index_new.html', positions=positions, selected_position=selected_position)

@app.route('/position/add', methods=['POST'])
@hr_required
def add_position():
    """Action: Create new position"""
    title = request.form.get('title', '').strip()
    description = request.form.get('description', '').strip()
    if title:
        position_id = storage.save_position(title, description)
        flash('Position created successfully.', 'success')
        return redirect(url_for('employer_portal', selected=position_id))
    return redirect(url_for('employer_portal'))

@app.route('/position/<position_id>/edit', methods=['POST'])
@hr_required
def edit_position(position_id):
    """Action: Update position"""
    title = request.form.get('title', '').strip()
    description = request.form.get('description', '').strip()
    if title:
        storage.update_position(position_id, title, description)
        flash('Position updated successfully.', 'success')
    return redirect(url_for('employer_portal', selected=position_id))

@app.route('/position/<position_id>/delete', methods=['POST'])
@hr_required
def delete_position_route(position_id):
    """Action: Delete position and its candidates"""
    storage.delete_position(position_id)
    flash('Position and associated candidates deleted.', 'success')
    return redirect(url_for('employer_portal'))

@app.route('/applicant')
def applicant_portal():
    """Route: Applicant Portal - Browse Jobs"""
    positions = storage.get_all_positions()
    if session.get('user_id'):
        return render_template('applicant_portal_loggedin.html', positions=positions, logged_in=True)
    return render_template('applicant_portal.html', positions=positions, logged_in=False)

@app.route('/application_status', methods=['GET', 'POST'])
def application_status():
    """Route: Check Application Status by ID"""
    candidate = None
    position = None
    error = None
    
    if request.method == 'POST':
        application_id = request.form.get('application_id', '').strip()
        if application_id:
            candidate = storage.get_candidate(application_id)
            if candidate:
                position_id = candidate.get('position_id')
                if position_id:
                    position = storage.get_position(position_id)
            else:
                error = "Application not found. Please check your ID."
        else:
            error = "Please enter your application ID."
    
    return render_template('application_status.html', candidate=candidate, position=position, error=error)

@app.route('/process_applicant/<position_id>', methods=['POST'])
def process_applicant(position_id):
    """Action: Process applicant resume for a specific position"""
    position = storage.get_position(position_id)
    if not position:
        flash('Position not found.', 'error')
        return redirect(url_for('applicant_portal'))
    
    job_description = position.get('description', '')
    
    # Check for PDF file
    if 'resume_file' not in request.files:
        flash('Please upload a resume file.', 'error')
        return redirect(url_for('applicant_portal'))
    
    file = request.files['resume_file']
    if not file or not file.filename:
        flash('Please select a file.', 'error')
        return redirect(url_for('applicant_portal'))
    
    if not allowed_file(file.filename):
        flash('Only PDF files are allowed.', 'error')
        return redirect(url_for('applicant_portal'))
    
    try:
        resume_text = extract_text_from_pdf(file)
        if not resume_text.strip():
            flash('Could not extract text from PDF.', 'error')
            return redirect(url_for('applicant_portal'))
        
        # Analyze resume with AI
        result = analyze_resume(resume_text, job_description, use_ai=True)
        result['raw_resume_text'] = resume_text
        result['source_file'] = file.filename
        result['position_id'] = position_id
        
        # Link to user if logged in and attach email
        if session.get('user_id'):
            result['user_id'] = session.get('user_id')
            result['name'] = session.get('user_name', result.get('name'))
            user = storage.get_user_by_id(session.get('user_id'))
            if user and user.get('email'):
                result['email'] = user.get('email')
        
        # If email not set from user, check form input or extract from resume
        if not result.get('email'):
            form_email = request.form.get('applicant_email', '').strip()
            if form_email:
                result['email'] = form_email
            else:
                email_match = re.search(r'[\w\.-]+@[\w\.-]+\.\w+', resume_text)
                if email_match:
                    result['email'] = email_match.group(0)
        
        # Save candidate and get ID
        candidate_id = storage.save_candidate(result)
        
        if session.get('user_id'):
            flash('Application submitted successfully!', 'success')
            return redirect(url_for('applicant_dashboard'))
        else:
            flash(f'Application submitted successfully! Your Application ID is: {candidate_id}. Save this ID to track your status.', 'success')
            return redirect(url_for('applicant_portal'))
        
    except Exception as e:
        print(f"Error processing application: {e}")
        flash('Error processing your application. Please try again.', 'error')
        return redirect(url_for('applicant_portal'))

@app.route('/setup_job', methods=['POST'])
def setup_job():
    """Action: Save Job Description (Legacy)"""
    job_description = request.form.get('job_description', '').strip()
    storage.save_job_description(job_description)
    return redirect(url_for('analyze_page'))

@app.route('/analyze')
@app.route('/analyze/<position_id>')
def analyze_page(position_id=None):
    """Route: Resume Input for a position"""
    positions = storage.get_all_positions()
    if not positions:
        flash('Please create a position first.', 'warning')
        return redirect(url_for('employer_portal'))
    
    selected_position = None
    if position_id:
        selected_position = storage.get_position(position_id)
    
    return render_template('analyze_new.html', positions=positions, selected_position=selected_position)

@app.route('/process_analysis', methods=['POST'])
def process_analysis():
    """Action: Analyze Resume (Text or PDF) and Save"""
    use_ai = request.form.get('use_ai') == 'on'
    position_id = request.form.get('position_id', '').strip()
    
    # Get job description from position if available
    position = storage.get_position(position_id) if position_id else None
    job_description = position.get('description', '') if position else storage.get_job_description()
    
    # Check if PDF files were uploaded
    if 'resume_files' in request.files:
        files = request.files.getlist('resume_files')
        valid_files = [f for f in files if f and f.filename and allowed_file(f.filename)]
        
        if valid_files:
            # Process multiple PDFs
            results = []
            for file in valid_files:
                try:
                    resume_text = extract_text_from_pdf(file)
                    if resume_text.strip():
                        result = analyze_resume(resume_text, job_description, use_ai=use_ai)
                        result['raw_resume_text'] = resume_text
                        result['source_file'] = file.filename
                        result['position_id'] = position_id
                        candidate_id = storage.save_candidate(result)
                        results.append(candidate_id)
                except Exception as e:
                    print(f"Error processing {file.filename}: {e}")
            
            if results:
                return redirect(url_for('dashboard', position_id=position_id) if position_id else url_for('dashboard'))
    
    # Fallback to text input
    resume_text = request.form.get('resume_text', '').strip()
    
    if not resume_text:
        return "Error: Resume text or PDF file is required", 400

    # Perform Analysis
    result = analyze_resume(resume_text, job_description, use_ai=use_ai)
    
    # Add raw text for persistence
    result['raw_resume_text'] = resume_text
    result['position_id'] = position_id
    
    # Save to storage
    candidate_id = storage.save_candidate(result)
    
    return redirect(url_for('candidate_detail', candidate_id=candidate_id))

@app.route('/dashboard')
@app.route('/dashboard/<position_id>')
def dashboard(position_id=None):
    """Route: Candidate Table with Pandas DataFrame, filtered by position"""
    positions = storage.get_all_positions()
    
    if position_id:
        candidates = storage.get_candidates_by_position(position_id)
        selected_position = storage.get_position(position_id)
    else:
        candidates = storage.get_all_candidates()
        selected_position = None
    
    if candidates:
        # Phase 5: Convert to pandas DataFrame for processing
        df = pd.DataFrame(candidates)
        
        # Ensure 'skills' column exists and replace NaN with empty list
        if 'skills' not in df.columns:
            df['skills'] = None
        
        # Use apply to replace NaN/None with [] to avoid subscriptable error in template
        df['skills'] = df['skills'].apply(lambda x: x if isinstance(x, list) else [])
        
        # Sort by final_rank_score descending
        df = df.sort_values(by='final_rank_score', ascending=False)
        
        # Convert back to list of dicts for template
        candidates = df.to_dict('records')
    
    pending_reschedules = storage.get_pending_reschedules()
    return render_template('dashboard_new.html', candidates=candidates, positions=positions, selected_position=selected_position, pending_reschedules=pending_reschedules)

# ============ Candidate Hub & Messaging Routes ============

@app.route('/candidate')
@hr_required
def candidate_hub():
    """Candidate Messaging & Progress Hub: Real-time messaging, timeline, multiple interview rounds, and onboarding stages."""
    selected_id = request.args.get('id')
    search_query = request.args.get('q', '').strip().lower()
    stage_filter = request.args.get('stage', '').strip()

    raw_candidates = storage.get_candidates()
    positions = storage.get_positions()
    pos_map = {p['id']: p.get('title', 'Position') for p in positions}

    enriched_candidates = []
    for c in raw_candidates:
        c_copy = dict(c)
        c_copy['position_title'] = pos_map.get(c.get('position_id'), 'General Position')
        timeline = storage.get_candidate_timeline(c['id'])
        c_copy['latest_event'] = timeline[-1] if timeline else None
        c_copy['timeline_count'] = len(timeline)

        # Fallback stage if unset
        if not c_copy.get('stage'):
            if c_copy.get('status') == 'rejected':
                c_copy['stage'] = 'Rejected'
            elif c_copy.get('interview', {}).get('status') in ['confirmed', 'pending_candidate_response']:
                c_copy['stage'] = c_copy.get('interview', {}).get('round_title', 'Round 1')
            elif c_copy.get('status') == 'accepted':
                c_copy['stage'] = 'Round 1'
            else:
                c_copy['stage'] = 'Screening'

        # Filter matching
        if search_query:
            name_match = search_query in c_copy.get('name', '').lower()
            role_match = search_query in c_copy['position_title'].lower()
            email_match = search_query in c_copy.get('email', '').lower()
            if not (name_match or role_match or email_match):
                continue

        if stage_filter and stage_filter != 'all':
            if c_copy['stage'].lower() != stage_filter.lower():
                continue

        enriched_candidates.append(c_copy)

    # Determine selected candidate
    selected_candidate = None
    if selected_id:
        selected_candidate = next((c for c in enriched_candidates if c['id'] == selected_id), None)
        if not selected_candidate:
            raw_c = storage.get_candidate(selected_id)
            if raw_c:
                selected_candidate = dict(raw_c)
                selected_candidate['position_title'] = pos_map.get(selected_candidate.get('position_id'), 'General Position')
                if not selected_candidate.get('stage'):
                    selected_candidate['stage'] = 'Screening'
                enriched_candidates.insert(0, selected_candidate)

    if not selected_candidate and enriched_candidates:
        selected_candidate = enriched_candidates[0]

    timeline = []
    selected_position = None
    if selected_candidate:
        timeline = storage.get_candidate_timeline(selected_candidate['id'])
        selected_position = storage.get_position(selected_candidate.get('position_id'))

    pipeline_stages = [
        {"key": "Screening", "label": "Screening", "icon": "📄"},
        {"key": "Round 1", "label": "Round 1 Interview", "icon": "🎙️"},
        {"key": "Round 2", "label": "Round 2 Deep-Dive", "icon": "💻"},
        {"key": "Round 3", "label": "Round 3 Executive", "icon": "🤝"},
        {"key": "Offer", "label": "Offer Extended", "icon": "💼"},
        {"key": "Onboarding", "label": "Onboarding", "icon": "🚀"},
        {"key": "Finished", "label": "Finished", "icon": "🏁"}
    ]

    return render_template(
        'candidate_updates.html',
        candidates=enriched_candidates,
        selected_candidate=selected_candidate,
        timeline=timeline,
        positions=positions,
        selected_position=selected_position,
        search_query=search_query,
        stage_filter=stage_filter,
        pipeline_stages=pipeline_stages
    )

@app.route('/candidate/<candidate_id>')
def candidate_detail(candidate_id):
    """Route: Detailed Result or redirect to Candidate Hub"""
    candidate = storage.get_candidate(candidate_id)
    if not candidate:
        return "Candidate not found", 404
    if request.args.get('view') == 'scores':
        return render_template('results.html', candidate=candidate)
    return redirect(url_for('candidate_hub', id=candidate_id))

@app.route('/candidate/<candidate_id>/message', methods=['POST'])
@hr_required
def candidate_send_message(candidate_id):
    """HR posts a chat message or internal note with optional file attachment to candidate thread"""
    content = request.form.get('content', '').strip()
    send_to = request.form.get('send_to', '').strip().lower()
    is_internal = (send_to == 'admin') or (request.form.get('is_internal') in ['1', 'true', 'on'])
    file_obj = request.files.get('attachment')

    candidate = storage.get_candidate(candidate_id)
    if not candidate:
        flash('Candidate not found.', 'error')
        return redirect(url_for('candidate_hub'))

    attachment_meta = None
    if file_obj and file_obj.filename:
        attachment_res = save_chat_attachment(file_obj)
        if isinstance(attachment_res, dict) and 'error' in attachment_res:
            flash(attachment_res['error'], 'error')
            return redirect(url_for('candidate_hub', id=candidate_id))
        attachment_meta = attachment_res

    if not content and not attachment_meta:
        flash('Please enter a message or select a file to attach.', 'error')
        return redirect(url_for('candidate_hub', id=candidate_id))

    if not content and attachment_meta:
        content = f"Attached: {attachment_meta['filename']}"

    metadata = {}
    if attachment_meta:
        metadata['attachment'] = attachment_meta

    event_type = 'internal_note' if is_internal else 'message'
    storage.add_candidate_timeline_event(
        candidate_id=candidate_id,
        sender='hr',
        sender_name='HR Team',
        event_type=event_type,
        content=content,
        metadata=metadata
    )

    if not is_internal:
        recip_id = candidate.get('user_id') or candidate['id']
        pos = storage.get_position(candidate.get('position_id'))
        pos_title = pos.get('title') if pos else 'Position'

        notif_text = content[:120] + ('...' if len(content) > 120 else '')
        if attachment_meta and not content.startswith("Attached:"):
            notif_text = f"📎 {attachment_meta['filename']} • {notif_text}"

        # Candidate in-app notification
        storage.add_notification(
            recipient_type='candidate',
            recipient_id=recip_id,
            title='📎 New Attachment from HR' if attachment_meta and content.startswith("Attached:") else '💬 New Message from HR',
            message=notif_text,
            link='/applicant_dashboard' if candidate.get('user_id') else '/application_status',
            notification_type='message'
        )

        # Candidate email notification
        candidate_email = candidate.get('email', '')
        if candidate_email:
            notification_service.send_direct_message_email(
                to_email=candidate_email,
                recipient_name=candidate.get('name', 'Candidate'),
                sender_name='HR Recruitment Team',
                position_title=pos_title,
                message_text=content,
                attachment_name=attachment_meta['filename'] if attachment_meta else ''
            )

    flash('Internal note saved.' if is_internal else 'Message and attachment sent to candidate.', 'success')
    return redirect(url_for('candidate_hub', id=candidate_id))

@app.route('/candidate/<candidate_id>/stage', methods=['POST'])
@hr_required
def candidate_update_stage(candidate_id):
    """HR advances or updates candidate pipeline stage"""
    new_stage = request.form.get('stage', '').strip()
    if not new_stage:
        flash('Invalid stage selected.', 'error')
        return redirect(url_for('candidate_hub', id=candidate_id))

    candidate = storage.update_candidate_stage(candidate_id, new_stage)
    if not candidate:
        flash('Candidate not found.', 'error')
        return redirect(url_for('candidate_hub'))

    # Send stage update email
    candidate_email = candidate.get('email', '')
    if candidate_email:
        pos = storage.get_position(candidate.get('position_id'))
        pos_title = pos.get('title') if pos else 'Position'
        notification_service.send_stage_update_email(
            candidate_email=candidate_email,
            candidate_name=candidate.get('name', 'Candidate'),
            position_title=pos_title,
            new_stage=new_stage
        )

    flash(f"Candidate stage advanced to '{new_stage}'. Candidate notified.", 'success')
    return redirect(url_for('candidate_hub', id=candidate_id))

@app.route('/candidate/<candidate_id>/schedule_round', methods=['POST'])
@hr_required
def candidate_schedule_round(candidate_id):
    """HR schedules 1st, 2nd, 3rd, or custom interview round"""
    round_title = request.form.get('round_title', 'Round 2 Interview').strip()
    date = request.form.get('date', '').strip()
    time = request.form.get('time', '').strip()
    meeting_link = request.form.get('meeting_link', '').strip()
    hr_note = request.form.get('hr_note', '').strip()

    if not date or not time:
        flash('Please select both date and time for the interview round.', 'error')
        return redirect(url_for('candidate_hub', id=candidate_id))

    candidate = storage.schedule_interview(
        candidate_id=candidate_id,
        date=date,
        time=time,
        meeting_link=meeting_link,
        hr_note=hr_note,
        round_title=round_title
    )
    if not candidate:
        flash('Candidate not found.', 'error')
        return redirect(url_for('candidate_hub'))

    # Dispatch email
    candidate_email = candidate.get('email', '')
    pos = storage.get_position(candidate.get('position_id'))
    pos_title = pos.get('title') if pos else 'Position'
    notification_service.send_interview_invitation(
        candidate_email=candidate_email,
        candidate_name=candidate.get('name', 'Candidate'),
        position_title=pos_title,
        interview_data=candidate.get('interview', {})
    )

    flash(f"🎉 {round_title} invitation scheduled and dispatched to {candidate.get('name')}!", 'success')
    return redirect(url_for('candidate_hub', id=candidate_id))

@app.route('/candidate/<candidate_id>/applicant_reply', methods=['POST'])
def candidate_applicant_reply(candidate_id):
    """Candidate posts a reply to HR thread from applicant dashboard/status with optional attachment"""
    content = request.form.get('content', '').strip()
    file_obj = request.files.get('attachment')

    attachment_meta = None
    if file_obj and file_obj.filename:
        attachment_res = save_chat_attachment(file_obj)
        if isinstance(attachment_res, dict) and 'error' in attachment_res:
            flash(attachment_res['error'], 'error')
            return redirect(request.referrer or url_for('applicant_dashboard'))
        attachment_meta = attachment_res

    if not content and not attachment_meta:
        flash('Please enter a message or attach a file.', 'error')
        return redirect(request.referrer or url_for('applicant_dashboard'))

    if not content and attachment_meta:
        content = f"Attached: {attachment_meta['filename']}"

    candidate = storage.get_candidate(candidate_id)
    if not candidate:
        flash('Candidate not found.', 'error')
        return redirect(request.referrer or url_for('applicant_dashboard'))

    cand_name = candidate.get('name', 'Candidate')
    pos = storage.get_position(candidate.get('position_id'))
    pos_title = pos.get('title') if pos else 'Position'

    metadata = {}
    if attachment_meta:
        metadata['attachment'] = attachment_meta

    storage.add_candidate_timeline_event(
        candidate_id=candidate_id,
        sender='candidate',
        sender_name=cand_name,
        event_type='message',
        content=content,
        metadata=metadata
    )

    notif_text = content[:100]
    if attachment_meta and not content.startswith("Attached:"):
        notif_text = f"📎 {attachment_meta['filename']} • {notif_text}"

    # In-app notification for HR
    storage.add_notification(
        recipient_type='hr',
        recipient_id='hr_admin',
        title=f"📎 Attachment from {cand_name}" if attachment_meta and content.startswith("Attached:") else f"💬 New Message from {cand_name}",
        message=f"{cand_name} ({pos_title}): {notif_text}",
        link=f"/candidate?id={candidate_id}",
        notification_type='message'
    )

    flash('Your message was sent to the HR recruitment team.', 'success')
    return redirect(request.referrer or url_for('applicant_dashboard'))

@app.route('/delete_candidate/<candidate_id>', methods=['POST'])
def delete_candidate(candidate_id):
    """Action: Delete Candidate and File"""
    # Get candidate info to find file
    candidate = storage.get_candidate(candidate_id)
    if candidate:
        # Try to delete associated file
        filename = candidate.get('source_file')
        if filename:
            file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            if os.path.exists(file_path):
                try:
                    os.remove(file_path)
                except Exception as e:
                    print(f"Error deleting file {file_path}: {e}")
        
        # Delete record
        storage.delete_candidate(candidate_id)
        flash('Candidate deleted successfully.', 'success')
        
    return redirect(url_for('dashboard'))

@app.route('/update_status/<candidate_id>', methods=['POST'])
def update_status(candidate_id):
    """Action: Update Candidate Status"""
    status = request.form.get('status')
    storage.update_candidate_status(candidate_id, status)
    return redirect(request.referrer or url_for('dashboard'))

# ============ Interview & Rescheduling Routes ============

@app.route('/candidate/<candidate_id>/schedule', methods=['POST'])
@hr_required
def schedule_candidate_interview(candidate_id):
    """HR schedules or updates an interview slot for a candidate"""
    date = request.form.get('date', '').strip()
    time = request.form.get('time', '').strip()
    round_title = request.form.get('round_title', 'Technical Interview').strip()
    meeting_link = request.form.get('meeting_link', '').strip()
    hr_note = request.form.get('hr_note', '').strip()

    if not date or not time:
        flash('Please select both date and time for the interview.', 'error')
        return redirect(request.referrer or url_for('dashboard'))

    candidate = storage.schedule_interview(
        candidate_id=candidate_id,
        date=date,
        time=time,
        meeting_link=meeting_link,
        hr_note=hr_note,
        round_title=round_title
    )
    if not candidate:
        flash('Candidate not found.', 'error')
        return redirect(url_for('dashboard'))

    # Dispatch email notification
    candidate_email = candidate.get('email', '')
    pos = storage.get_position(candidate.get('position_id'))
    pos_title = pos.get('title') if pos else 'Position'
    notification_service.send_interview_invitation(
        candidate_email=candidate_email,
        candidate_name=candidate.get('name', 'Candidate'),
        position_title=pos_title,
        interview_data=candidate.get('interview', {})
    )

    flash(f"Interview invitation sent to {candidate.get('name')}. Candidate notified in-app and via email.", 'success')
    return redirect(request.referrer or url_for('dashboard'))

@app.route('/candidate/<candidate_id>/interview_action', methods=['POST'])
def candidate_interview_action(candidate_id):
    """Candidate confirms, declines, or requests reschedule"""
    action = request.form.get('action', '').strip().lower() # 'accept', 'decline', 'reschedule'
    proposed_date = request.form.get('proposed_date', '').strip()
    proposed_time = request.form.get('proposed_time', '').strip()
    reason = request.form.get('reason', '').strip()

    candidate = storage.get_candidate(candidate_id)
    if not candidate:
        flash('Application record not found.', 'error')
        return redirect(url_for('index'))

    # If logged in user, verify ownership
    if candidate.get('user_id') and session.get('user_id'):
        if candidate.get('user_id') != session.get('user_id'):
            flash('Unauthorized access.', 'error')
            return redirect(url_for('applicant_dashboard'))

    if action == 'reschedule' and (not proposed_date or not proposed_time):
        flash('Please provide your preferred new date and time for rescheduling.', 'error')
        return redirect(request.referrer or url_for('applicant_dashboard'))

    updated_candidate = storage.candidate_respond_interview(
        candidate_id=candidate_id,
        action=action,
        proposed_date=proposed_date,
        proposed_time=proposed_time,
        reason=reason
    )

    # Email notification to HR
    pos = storage.get_position(candidate.get('position_id'))
    pos_title = pos.get('title') if pos else 'Position'
    notification_service.send_candidate_response_alert_to_hr(
        hr_email="",
        candidate_name=candidate.get('name', 'Candidate'),
        position_title=pos_title,
        action=action,
        details={
            'proposed_date': proposed_date,
            'proposed_time': proposed_time,
            'reason': reason
        }
    )

    if action in ['accept', 'confirm']:
        flash('🎉 Interview confirmed! We look forward to meeting you.', 'success')
    elif action == 'reschedule':
        flash('📅 Reschedule request sent to HR. You will be notified once reviewed.', 'info')
    elif action in ['decline', 'reject']:
        flash('Interview invitation declined.', 'warning')

    if session.get('user_id'):
        return redirect(url_for('applicant_dashboard'))
    return redirect(request.referrer or url_for('application_status'))

@app.route('/candidate/<candidate_id>/resolve_reschedule', methods=['POST'])
@hr_required
def hr_resolve_reschedule(candidate_id):
    """HR approves candidate's proposed time or suggests a counter slot"""
    decision = request.form.get('decision', 'approve').strip() # 'approve' or 'counter'
    new_date = request.form.get('new_date', '').strip()
    new_time = request.form.get('new_time', '').strip()
    hr_note = request.form.get('hr_note', '').strip()

    candidate = storage.hr_resolve_reschedule(
        candidate_id=candidate_id,
        decision=decision,
        new_date=new_date,
        new_time=new_time,
        hr_note=hr_note
    )

    if not candidate:
        flash('Candidate not found.', 'error')
        return redirect(url_for('dashboard'))

    # Dispatch email resolution to candidate
    candidate_email = candidate.get('email', '')
    pos = storage.get_position(candidate.get('position_id'))
    pos_title = pos.get('title') if pos else 'Position'
    notification_service.send_reschedule_resolution_to_candidate(
        candidate_email=candidate_email,
        candidate_name=candidate.get('name', 'Candidate'),
        position_title=pos_title,
        is_approved=(decision == 'approve'),
        interview_data=candidate.get('interview', {})
    )

    if decision == 'approve':
        flash(f"Candidate's reschedule request approved! Interview confirmed.", 'success')
    else:
        flash(f"Counter interview slot proposed to candidate.", 'info')

    return redirect(request.referrer or url_for('dashboard'))

# ============ In-App Notification API Routes ============

@app.route('/api/notifications', methods=['GET'])
def get_notifications_api():
    """Returns in-app notifications for the current session (HR, Employee, or Applicant)"""
    scope = request.args.get('scope')
    if scope == 'employee' and session.get('employee_id'):
        notifs = storage.get_notifications(recipient_id=session.get('employee_id'))
    elif scope == 'hr' and session.get('is_hr'):
        notifs = storage.get_notifications(recipient_type='hr', recipient_id='hr_admin')
    elif session.get('is_hr'):
        notifs = storage.get_notifications(recipient_type='hr', recipient_id='hr_admin')
    elif session.get('employee_id'):
        notifs = storage.get_notifications(recipient_id=session.get('employee_id'))
    elif session.get('user_id'):
        notifs = storage.get_notifications(recipient_id=session.get('user_id'))
    else:
        notifs = []
    unread_count = sum(1 for n in notifs if not n.get('read'))
    return jsonify({"success": True, "notifications": notifs, "unread_count": unread_count})

@app.route('/api/notifications/<notification_id>/read', methods=['POST'])
def mark_notification_read_api(notification_id):
    storage.mark_notification_read(notification_id)
    return jsonify({"success": True})

@app.route('/api/notifications/mark_all_read', methods=['POST'])
def mark_all_notifications_read_api():
    scope = request.args.get('scope')
    if scope == 'employee' and session.get('employee_id'):
        storage.mark_all_notifications_read(recipient_id=session.get('employee_id'))
    elif scope == 'hr' and session.get('is_hr'):
        storage.mark_all_notifications_read(recipient_type='hr', recipient_id='hr_admin')
    elif session.get('is_hr'):
        storage.mark_all_notifications_read(recipient_type='hr', recipient_id='hr_admin')
    elif session.get('employee_id'):
        storage.mark_all_notifications_read(recipient_id=session.get('employee_id'))
    elif session.get('user_id'):
        storage.mark_all_notifications_read(recipient_id=session.get('user_id'))
    return jsonify({"success": True})

# --- API Routes for Programmatic Access (Optional) ---

@app.route('/api/analyze', methods=['POST'])
def api_analyze():
    data = request.json
    resume_text = data.get('resume_text', '')
    use_ai = data.get('use_ai', False)
    # Use stored JD or override
    job_description = data.get('job_description') or storage.get_job_description()
    
    if not resume_text:
        return jsonify({"success": False, "error": "No resume text"}), 400

    try:
        result = analyze_resume(resume_text, job_description, use_ai=use_ai)
        result['raw_resume_text'] = resume_text
        candidate_id = storage.save_candidate(result)
        result['id'] = candidate_id
        return jsonify({"success": True, "data": result})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

# ==========================================
# PHASE 2: CURRENT EMPLOYEE MANAGEMENT & SELF-SERVICE PORTAL
# ==========================================

@app.route('/employee_login', methods=['GET', 'POST'])
def employee_login():
    if session.get('employee_id'):
        return redirect(url_for('employee_dashboard'))

    if request.method == 'POST':
        identifier = request.form.get('identifier', '').strip()
        password = request.form.get('password', '').strip()

        emp = storage.verify_employee_login(identifier, password)
        if emp:
            session['employee_id'] = emp['id']
            session['employee_name'] = emp['name']
            session['employee_email'] = emp.get('email', '')
            session['is_employee'] = True
            session['access_role'] = emp.get('access_role', 'employee')
            flash(f"Welcome back, {emp['name']}!", 'success')
            return redirect(url_for('employee_dashboard'))
        else:
            flash('Invalid Employee ID / Email or password. (Default password: emp123)', 'error')

    all_emps = storage.get_all_employees()
    demo_leads = [e for e in all_emps if e.get('access_role') == 'team_lead'][:2]
    demo_staff = [e for e in all_emps if e.get('access_role') != 'team_lead'][:2]
    sample_employees = demo_leads + demo_staff
    return render_template('employee_login.html', sample_employees=sample_employees)

@app.route('/employee_logout')
def employee_logout():
    session.pop('employee_id', None)
    session.pop('employee_name', None)
    session.pop('employee_email', None)
    session.pop('is_employee', None)
    session.pop('access_role', None)
    flash('You have been logged out of the Employee Portal.', 'success')
    return redirect(url_for('employee_login'))

@app.route('/employees')
@hr_required
def employees_panel():
    employees = storage.get_all_employees()
    today_att = storage.get_today_attendance()
    leave_requests = storage.get_all_leave_requests()

    att_by_emp = {a['employee_id']: a for a in today_att}
    emp_map = {e['id']: e for e in employees}
    team_leads = [e for e in employees if e.get('access_role') == 'team_lead']

    candidates = storage.get_all_candidates()
    eligible_candidates = [
        c for c in candidates
        if not c.get('employee_id') and (c.get('stage') == 'Finished' or c.get('status') in ['accepted', 'Hired', 'finished'])
    ]

    pending_hr_leaves = [l for l in leave_requests if l.get('status') == 'pending_hr']
    pending_lead_leaves = [l for l in leave_requests if l.get('status') == 'pending_lead']
    history_leaves = [
        l for l in leave_requests
        if l.get('status') not in ('pending_hr', 'pending_lead', 'pending')
    ]

    total_employees = len(employees)
    clocked_in_today = sum(1 for a in today_att if a.get('clock_in'))
    on_leave_today = sum(1 for a in today_att if a.get('status') == 'On Leave')
    pending_leaves = len(pending_hr_leaves)
    total_payroll = sum(e.get('salary', {}).get('net', 0) for e in employees)

    active_tab = request.args.get('tab', 'directory')

    return render_template(
        'employees.html',
        employees=employees,
        emp_map=emp_map,
        team_leads=team_leads,
        att_by_emp=att_by_emp,
        leave_requests=leave_requests,
        pending_hr_leaves=pending_hr_leaves,
        pending_lead_leaves=pending_lead_leaves,
        history_leaves=history_leaves,
        eligible_candidates=eligible_candidates,
        total_employees=total_employees,
        clocked_in_today=clocked_in_today,
        on_leave_today=on_leave_today,
        pending_leaves=pending_leaves,
        total_payroll=total_payroll,
        casual_cap=storage.CASUAL_LEAVE_YEARLY_CAP,
        default_yearly_quota=storage.DEFAULT_YEARLY_LEAVE_QUOTA,
        active_tab=active_tab
    )

def _parse_leave_quotas(form, default_casual=None, default_yearly=None):
    """Parses casual and yearly leave quotas from HR form data without silent fallback on bad values."""
    d_casual = storage.CASUAL_LEAVE_YEARLY_CAP if default_casual is None else int(default_casual)
    d_yearly = storage.DEFAULT_YEARLY_LEAVE_QUOTA if default_yearly is None else int(default_yearly)
    raw_casual = (form.get('casual_quota') or '').strip()
    raw_yearly = (form.get('yearly_quota') or '').strip()
    try:
        casual_q = int(raw_casual) if raw_casual != '' else d_casual
        yearly_q = int(raw_yearly) if raw_yearly != '' else d_yearly
    except ValueError:
        raise ValueError("Leave quotas must be valid whole numbers.")
    return storage._validate_leave_quotas({"casual": casual_q, "yearly": yearly_q}, d_casual, d_yearly)

@app.route('/candidate/<candidate_id>/convert_to_employee', methods=['POST'])
@hr_required
def convert_candidate_to_employee_route(candidate_id):
    department = request.form.get('department', 'Engineering')
    role = request.form.get('role')
    base_sal = request.form.get('base_salary', 85000)
    allowances = request.form.get('allowances', 15000)
    deductions = request.form.get('deductions', 5000)
    access_role = request.form.get('access_role', 'employee')
    team_lead_id = request.form.get('team_lead_id', '').strip() or None

    salary_data = {
        'base': base_sal,
        'allowances': allowances,
        'deductions': deductions
    }

    try:
        quotas = _parse_leave_quotas(request.form)
        emp = storage.convert_candidate_to_employee(
            candidate_id,
            department=department,
            role=role,
            salary_data=salary_data,
            access_role=access_role,
            team_lead_id=team_lead_id,
            casual_quota=quotas['casual'],
            yearly_quota=quotas['yearly'],
        )
        if emp:
            flash(f"Candidate {emp['name']} successfully shifted to Current Employees! ID assigned: {emp['id']}.", 'success')
        else:
            flash("Failed to convert candidate. Candidate record not found.", 'error')
    except ValueError as ve:
        flash(str(ve), 'error')

    return redirect(url_for('employees_panel'))

@app.route('/employee/add', methods=['POST'])
@hr_required
def add_employee_route():
    name = request.form.get('name', '').strip()
    email = request.form.get('email', '').strip()
    phone = request.form.get('phone', '').strip()
    role = request.form.get('role', 'Software Engineer').strip()
    department = request.form.get('department', 'Engineering').strip()
    access_role = request.form.get('access_role', 'employee').strip()
    team_lead_id = request.form.get('team_lead_id', '').strip() or None
    base_sal = float(request.form.get('base_salary', 80000))
    allowances = float(request.form.get('allowances', 12000))
    deductions = float(request.form.get('deductions', 4000))

    if not name or not email:
        flash('Employee name and email are required.', 'error')
        return redirect(url_for('employees_panel'))

    try:
        quotas = _parse_leave_quotas(request.form)
        emp_data = {
            'name': name,
            'email': email,
            'phone': phone,
            'role': role,
            'department': department,
            'access_role': access_role,
            'team_lead_id': team_lead_id,
            'date_of_joining': datetime.now().date().isoformat(),
            'status': 'Active',
            'password': 'emp123',
            'salary': {
                'base': base_sal,
                'allowances': allowances,
                'deductions': deductions,
                'net': base_sal + allowances - deductions,
                'currency': '$',
                'payment_cycle': 'Monthly',
                'status': 'Paid',
                'last_paid_date': datetime.now().strftime('%Y-%m-01')
            },
            'leave_quota': quotas,
            'created_at': datetime.now().isoformat()
        }
        emp_id = storage.save_employee(emp_data)
        flash(f"Employee {name} ({emp_id}) added to directory!", 'success')
    except ValueError as ve:
        flash(str(ve), 'error')
    return redirect(url_for('employees_panel'))

@app.route('/employee/<employee_id>/edit', methods=['POST'])
@hr_required
def edit_employee_route(employee_id):
    emp = storage.get_employee(employee_id)
    if not emp:
        flash('Employee not found.', 'error')
        return redirect(url_for('employees_panel'))

    role = request.form.get('role', emp.get('role'))
    department = request.form.get('department', emp.get('department'))
    status = request.form.get('status', emp.get('status'))
    access_role = request.form.get('access_role', emp.get('access_role', 'employee'))
    team_lead_id = request.form.get('team_lead_id', '').strip() or None
    cur_casual_q = emp.get('leave_quota', {}).get('casual', storage.CASUAL_LEAVE_YEARLY_CAP)
    cur_yearly_q = emp.get('leave_quota', {}).get('yearly', storage.DEFAULT_YEARLY_LEAVE_QUOTA)
    base_sal = float(request.form.get('base_salary', emp.get('salary', {}).get('base', 80000)))
    allowances = float(request.form.get('allowances', emp.get('salary', {}).get('allowances', 12000)))
    deductions = float(request.form.get('deductions', emp.get('salary', {}).get('deductions', 4000)))

    try:
        quotas = _parse_leave_quotas(request.form, default_casual=cur_casual_q, default_yearly=cur_yearly_q)
        updates = {
            'role': role,
            'department': department,
            'status': status,
            'access_role': access_role,
            'team_lead_id': team_lead_id,
            'leave_quota': quotas,
            'salary': {
                'base': base_sal,
                'allowances': allowances,
                'deductions': deductions,
                'net': base_sal + allowances - deductions,
                'currency': emp.get('salary', {}).get('currency', '$'),
                'payment_cycle': emp.get('salary', {}).get('payment_cycle', 'Monthly'),
                'status': emp.get('salary', {}).get('status', 'Paid'),
                'last_paid_date': emp.get('salary', {}).get('last_paid_date')
            }
        }
        storage.update_employee(employee_id, updates)
        flash(f"Employee {emp['name']} updated successfully.", 'success')
    except ValueError as ve:
        flash(str(ve), 'error')
    return redirect(url_for('employees_panel'))

@app.route('/employee/<employee_id>/delete', methods=['POST'])
@hr_required
def delete_employee_route(employee_id):
    success = storage.delete_employee(employee_id)
    if success:
        flash('Employee removed from directory.', 'info')
    else:
        flash('Failed to remove employee.', 'error')
    return redirect(url_for('employees_panel'))

@app.route('/hr/leave/<leave_id>/review', methods=['POST'])
@hr_required
def review_leave_route(leave_id):
    decision = request.form.get('decision', 'rejected')
    remarks = request.form.get('remarks', '')
    override_mode = request.form.get('override_mode', 'auto')
    override_casual_raw = request.form.get('override_casual_days')
    override_casual_days = None
    if override_mode == 'split' and override_casual_raw not in (None, ''):
        try:
            override_casual_days = int(override_casual_raw)
        except ValueError:
            flash('Invalid custom casual days value.', 'error')
            return redirect(url_for('employees_panel', tab='leaves'))

    try:
        reviewed = storage.hr_review_leave_request(
            leave_id,
            decision,
            remarks=remarks,
            override_mode=override_mode,
            override_casual_days=override_casual_days,
        )
        emp = storage.get_employee(reviewed.get('employee_id'))
        if emp and emp.get('email'):
            action_label = "Approved" if reviewed['status'] == 'approved' else "Rejected"
            notification_service.send_leave_status_update_email(
                emp['email'], emp['name'], reviewed, "HR Admin", action_label, remarks=remarks
            )
        if reviewed['status'] == 'approved':
            flash(
                f"Leave request for {reviewed.get('employee_name')} APPROVED ({reviewed.get('leave_type')})! "
                f"Attendance calendar & balances updated.",
                'success',
            )
        else:
            flash(f"Leave request for {reviewed.get('employee_name')} has been REJECTED by HR.", 'warning')
    except (ValueError, LookupError) as err:
        flash(str(err), 'error')
    return redirect(url_for('employees_panel', tab='leaves'))

@app.route('/hr/leave/<leave_id>/convert_type', methods=['POST'])
@hr_required
def convert_leave_type_route(leave_id):
    target_mode = request.form.get('target_mode', '')
    custom_casual_raw = request.form.get('custom_casual_days')
    reason = request.form.get('reason', '')
    custom_casual_days = None
    if target_mode == 'split' and custom_casual_raw not in (None, ''):
        try:
            custom_casual_days = int(custom_casual_raw)
        except ValueError:
            flash('Invalid custom casual days count.', 'error')
            return redirect(url_for('employees_panel', tab='leaves'))

    try:
        updated = storage.hr_convert_leave_type(
            leave_id,
            target_mode=target_mode,
            custom_casual_days=custom_casual_days,
            reason=reason,
        )
        emp = storage.get_employee(updated.get('employee_id'))
        if emp and emp.get('email'):
            notification_service.send_leave_status_update_email(
                emp['email'], emp['name'], updated, "HR Admin", "Reclassified", remarks=reason
            )
        flash(
            f"Leave for {updated.get('employee_name')} reclassified to {updated.get('leave_type')}. "
            f"Leave balances updated.",
            'success',
        )
    except (ValueError, LookupError) as err:
        flash(str(err), 'error')
    return redirect(url_for('employees_panel', tab='leaves'))

@app.route('/api/employee/<employee_id>/attendance')
@hr_required
def api_employee_attendance(employee_id):
    month = request.args.get('month')
    att = storage.get_employee_attendance(employee_id, year_month=month)
    return jsonify({"success": True, "attendance": att})

@app.route('/employee_dashboard')
@employee_required
def employee_dashboard():
    emp_id = session.get('employee_id')
    emp = storage.get_employee(emp_id)
    if not emp:
        flash('Employee profile not found.', 'error')
        return redirect(url_for('employee_login'))

    today_str = datetime.now().date().isoformat()
    all_att = storage.get_employee_attendance(emp_id)
    today_att = next((a for a in all_att if a.get('date') == today_str), None)

    current_month_str = datetime.now().strftime('%Y-%m')
    month_att = [a for a in all_att if str(a.get('date', '')).startswith(current_month_str)]

    days_present = sum(1 for a in month_att if a.get('status') in ['Present', 'Half Day'])
    total_hours_month = sum(a.get('total_hours', 0.0) for a in month_att)
    days_leave = sum(1 for a in month_att if a.get('status') == 'On Leave')

    my_leaves = storage.get_employee_leave_requests(emp_id)
    year_stats = storage.get_employee_year_leave_stats(emp_id)
    team_lead = storage.get_employee(emp.get('team_lead_id')) if emp.get('team_lead_id') else None

    is_team_lead = (emp.get('access_role') == 'team_lead')
    team_members = []
    team_member_stats = {}
    team_att_by_emp = {}
    team_pending_leaves = []
    team_history_leaves = []

    if is_team_lead:
        team_members = storage.get_team_members(emp_id)
        team_member_stats = {m['id']: storage.get_employee_year_leave_stats(m['id']) for m in team_members}
        team_att_by_emp = {a['employee_id']: a for a in storage.get_today_attendance()}
        team_leaves = storage.get_team_lead_leave_requests(emp_id)
        team_pending_leaves = [l for l in team_leaves if l.get('status') == 'pending_lead']
        team_history_leaves = [l for l in team_leaves if l.get('status') != 'pending_lead']

    requested_tab = request.args.get('tab', 'my_portal')
    active_tab = requested_tab if (is_team_lead and requested_tab in ('my_portal', 'team_approvals', 'my_team')) else 'my_portal'

    return render_template(
        'employee_dashboard.html',
        emp=emp,
        year_stats=year_stats,
        team_lead=team_lead,
        is_team_lead=is_team_lead,
        team_members=team_members,
        team_member_stats=team_member_stats,
        team_att_by_emp=team_att_by_emp,
        team_pending_leaves=team_pending_leaves,
        team_history_leaves=team_history_leaves,
        active_tab=active_tab,
        today_att=today_att,
        month_att=month_att,
        days_present=days_present,
        total_hours_month=round(total_hours_month, 1),
        days_leave=days_leave,
        my_leaves=my_leaves,
        today_date=datetime.now().strftime('%A, %B %d, %Y')
    )

@app.route('/employee/clock_in', methods=['POST'])
@employee_required
def employee_clock_in():
    emp_id = session.get('employee_id')
    att = storage.clock_in(emp_id)
    if request.is_json:
        return jsonify({"success": True, "attendance": att})
    flash(f"Clocked in successfully at {att.get('clock_in')}! Attendance recorded.", 'success')
    return redirect(url_for('employee_dashboard'))

@app.route('/employee/clock_out', methods=['POST'])
@employee_required
def employee_clock_out():
    emp_id = session.get('employee_id')
    att = storage.clock_out(emp_id)
    if request.is_json:
        return jsonify({"success": True, "attendance": att})
    flash(f"Clocked out at {att.get('clock_out')}. Today's working time: {att.get('total_hours')} hrs.", 'info')
    return redirect(url_for('employee_dashboard'))

@app.route('/employee/apply_leave', methods=['POST'])
@employee_required
def employee_apply_leave():
    emp_id = session.get('employee_id')
    start_date = request.form.get('start_date')
    end_date = request.form.get('end_date')
    reason = request.form.get('reason', '').strip()

    if not start_date or not end_date:
        flash('Please select both start date and end date.', 'error')
        return redirect(url_for('employee_dashboard'))

    try:
        leave = storage.submit_leave_request(emp_id, start_date, end_date, reason)
        emp = storage.get_employee(emp_id)
        if leave.get('status') == 'pending_lead':
            lead = storage.get_employee(leave.get('assigned_team_lead_id'))
            if lead and lead.get('email'):
                notification_service.send_leave_submitted_to_lead_email(
                    lead['email'], lead['name'], emp['name'], leave
                )
            flash(
                f"Leave request ({leave['days']} day(s): {leave['leave_type']}) sent to Team Lead "
                f"{leave.get('assigned_team_lead_name')} for approval.",
                'success',
            )
        else:
            notification_service.send_leave_forwarded_to_hr_email(
                None, f"{emp['name']} (Team Lead)", emp['name'], leave
            )
            flash(
                f"Leave request ({leave['days']} day(s): {leave['leave_type']}) sent to HR Admin for approval.",
                'success',
            )
    except ValueError as ve:
        flash(str(ve), 'error')
    return redirect(url_for('employee_dashboard'))

@app.route('/team_lead/leave/<leave_id>/review', methods=['POST'])
@team_lead_required
def team_lead_review_leave_route(leave_id):
    team_lead_id = session.get('employee_id')
    decision = request.form.get('decision', 'reject')
    remarks = request.form.get('remarks', '')

    try:
        reviewed = storage.team_lead_review_leave(leave_id, team_lead_id, decision, remarks)
        emp = storage.get_employee(reviewed.get('employee_id'))
        lead = storage.get_employee(team_lead_id)
        if reviewed['status'] == 'pending_hr':
            notification_service.send_leave_forwarded_to_hr_email(
                None, lead['name'] if lead else 'Team Lead', reviewed.get('employee_name', ''), reviewed
            )
            flash(
                f"Approved {reviewed.get('employee_name')}'s leave request and forwarded it to HR for final approval.",
                'success',
            )
        else:
            if emp and emp.get('email'):
                notification_service.send_leave_status_update_email(
                    emp['email'], emp['name'], reviewed, lead['name'] if lead else 'Team Lead', "Rejected by Team Lead", remarks=remarks
                )
            flash(f"Rejected {reviewed.get('employee_name')}'s leave request.", 'warning')
    except (PermissionError, ValueError, LookupError) as err:
        flash(str(err), 'error')
    return redirect(url_for('employee_dashboard', tab='team_approvals'))

@app.route('/api/employee/my_attendance')
@employee_required
def api_my_attendance():
    emp_id = session.get('employee_id')
    month = request.args.get('month')
    att = storage.get_employee_attendance(emp_id, year_month=month)
    return jsonify({"success": True, "attendance": att})

# ============ Health Check & Production Error Handling ============

@app.route('/health')
def health():
    """Health check endpoint for Docker, orchestrators, and monitoring."""
    try:
        # Verify storage connectivity
        _ = storage.get_all_positions()
        return jsonify({
            "status": "healthy",
            "service": "talentai-hr",
            "timestamp": datetime.now().isoformat()
        }), 200
    except Exception as exc:
        app.logger.error(f"Health check failed: {exc}", exc_info=True)
        return jsonify({
            "status": "unhealthy",
            "error": str(exc),
            "timestamp": datetime.now().isoformat()
        }), 503

@app.errorhandler(404)
def not_found_error(error):
    if request.is_json or request.path.startswith('/api/'):
        return jsonify({"success": False, "error": "Resource not found", "status_code": 404}), 404
    return render_template('error.html', code=404, title="Page Not Found", message="The requested URL was not found on the server."), 404

@app.errorhandler(500)
def internal_error(error):
    app.logger.error(f"Internal server error: {error}", exc_info=True)
    if request.is_json or request.path.startswith('/api/'):
        return jsonify({"success": False, "error": "Internal server error", "status_code": 500}), 500
    return render_template('error.html', code=500, title="Server Error", message="An unexpected error occurred. Our engineering team has been notified."), 500

@app.errorhandler(413)
def request_entity_too_large(error):
    if request.is_json or request.path.startswith('/api/'):
        return jsonify({"success": False, "error": "File exceeds maximum allowed upload size (16MB)", "status_code": 413}), 413
    flash("The uploaded file is too large. Maximum allowed size is 16MB.", "error")
    return redirect(request.referrer or url_for('index'))

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    debug = os.environ.get('DEBUG', 'false').lower() in ('true', '1')
    app.run(host='0.0.0.0', port=port, debug=debug)
