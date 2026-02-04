from flask import Flask, render_template, request, jsonify, redirect, url_for, flash, session
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
from dotenv import load_dotenv
import os
import json
import pandas as pd
from agent import analyze_resume
import storage
from pdf_utils import extract_text_from_pdf

# Load environment variables
load_dotenv()

app = Flask(__name__, template_folder='templates', static_folder='static')

# Authentication Decorators
def hr_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('is_hr'):
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

# Configure upload folder
UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), 'uploads')
ALLOWED_EXTENSIONS = {'pdf'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max
app.secret_key = os.urandom(24) # Invalidate old sessions and use random key for security

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route('/')
def index():
    """Route: Landing Page (New Homepage)"""
    return render_template('landing.html')



@app.route('/overview')
@hr_required
def overview():
    """Route: Overview Dashboard (Default Employer Page)"""
    stats = storage.get_overview_stats()
    return render_template('overview.html', stats=stats)

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
        
        # Link to user if logged in
        if session.get('user_id'):
            result['user_id'] = session.get('user_id')
            result['name'] = session.get('user_name', result.get('name')) # Use account name if extraction fails or as fallback
        
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
    
    return render_template('dashboard_new.html', candidates=candidates, positions=positions, selected_position=selected_position)

@app.route('/candidate/<candidate_id>')
def candidate_detail(candidate_id):
    """Route: Detailed Result"""
    candidate = storage.get_candidate(candidate_id)
    if not candidate:
        return "Candidate not found", 404
    return render_template('results.html', candidate=candidate)

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
    # Redirect back to previous page if possible, otherwise dashboard
    return redirect(request.referrer or url_for('dashboard'))

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

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)
