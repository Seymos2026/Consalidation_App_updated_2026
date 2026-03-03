from flask import Flask, render_template, request, redirect, session, flash, url_for, jsonify, send_file
import pandas as pd
import os
import re
import math
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
import sqlite3
from datetime import datetime
from io import BytesIO

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['MASTER_FILE_FOLDER'] = 'master_files'
app.config['TEMPLATE_FOLDER'] = 'templates_files'

# Create necessary directories
for folder in [app.config['UPLOAD_FOLDER'], app.config['MASTER_FILE_FOLDER'], app.config['TEMPLATE_FOLDER']]:
    if not os.path.exists(folder):
        os.makedirs(folder)
        print(f"Created folder at: {os.path.abspath(folder)}")
    else:
        print(f"Folder found at: {os.path.abspath(folder)}")

#app.secret_key = 'heremysecretkey2023_strong_and_random'
app.secret_key = os.environ.get("SECRET_KEY", "dev-secret-key")

# Database initialization
def init_db():
    conn = sqlite3.connect('app.db')
    c = conn.cursor()
    
    # Users table
    c.execute('''CREATE TABLE IF NOT EXISTS users
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  username TEXT UNIQUE NOT NULL,
                  password_hash TEXT NOT NULL,
                  role TEXT NOT NULL,
                  full_name TEXT,
                  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                  password_changed BOOLEAN DEFAULT 0)''')
    
    # Submissions table to track instructor uploads
    c.execute('''CREATE TABLE IF NOT EXISTS submissions
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  instructor_id INTEGER NOT NULL,
                  filename TEXT NOT NULL,
                  course_name TEXT,
                  submitted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                  FOREIGN KEY (instructor_id) REFERENCES users(id))''')
    
    # Check if admin user exists, if not create default admin
    c.execute("SELECT COUNT(*) FROM users WHERE role = 'admin'")
    if c.fetchone()[0] == 0:
        default_admin_password = generate_password_hash('admin@2025', method='pbkdf2:sha256')
        c.execute("INSERT INTO users (username, password_hash, role, full_name) VALUES (?, ?, ?, ?)",
                  ('cecs@cud.ac.ae', default_admin_password, 'admin', 'Admin User'))
        print("Created default admin user: cecs@cud.ac.ae / admin@2025")
    
    conn.commit()
    conn.close()

init_db()

# --- Helper Functions ---
def get_db():
    conn = sqlite3.connect('app.db')
    conn.row_factory = sqlite3.Row
    return conn

def get_professor_and_course_from_filename(filename_with_ext):
    """Parses filename assuming format: CourseCode_CourseName_ProfessorName.ext"""
    print(f"\n[PARSER] Input Filename: {filename_with_ext}")
    if not filename_with_ext or '.' not in filename_with_ext:
        print("[PARSER] Invalid filename or no extension.")
        return "Other Files", filename_with_ext, "N/A"

    base_name_no_ext = filename_with_ext.rsplit('.', 1)[0]
    parts = base_name_no_ext.split('_')
    print(f"[PARSER] Base: {base_name_no_ext}, Parts: {parts}")

    if not parts:
        print("[PARSER] No parts after splitting by '_'.")
        return "Other Files", base_name_no_ext, "N/A"

    professor_name = "Other Files"
    course_code = "N/A"
    course_name_str = ""

    start_prof_idx = -1
    for i in range(len(parts) - 1, -1, -1):
        part_lower = parts[i].lower()
        if part_lower.startswith("dr") or part_lower.startswith("prof"):
            start_prof_idx = i
            break

    if start_prof_idx != -1:
        title_part = parts[start_prof_idx]
        name_parts_after_title = parts[start_prof_idx+1:]
        
        normalized_title = ""
        actual_name_from_title_part = ""

        if title_part.lower().startswith("dr"):
            normalized_title = "Dr."
            actual_name_from_title_part = title_part[2:].lstrip('._ ')
        elif title_part.lower().startswith("prof"):
            normalized_title = "Prof."
            actual_name_from_title_part = title_part[4:].lstrip('._ ')
            
        full_prof_name_parts = []
        if actual_name_from_title_part:
            full_prof_name_parts.append(actual_name_from_title_part)
        full_prof_name_parts.extend(name_parts_after_title)
        
        if full_prof_name_parts:
            professor_name = f"{normalized_title} {' '.join(full_prof_name_parts)}".strip()
        else:
            professor_name = normalized_title
        
        non_prof_segments = parts[:start_prof_idx]
        print(f"[PARSER] Professor (marker found): '{professor_name}', Remaining for course: {non_prof_segments}")

    elif len(parts) > 1:
        if parts[-1][0].isupper() and not re.match(r"^[A-Z0-9]+$", parts[-1]):
            professor_name = parts[-1].replace(".", " ").strip()
            non_prof_segments = parts[:-1]
            print(f"[PARSER] Professor (heuristic end): '{professor_name}', Remaining for course: {non_prof_segments}")
        else:
            non_prof_segments = parts
    else:
        non_prof_segments = parts

    if non_prof_segments:
        first_segment = non_prof_segments[0]
        code_match = re.match(r"^([A-Za-z]+[0-9]+[A-Za-z0-9]*)$", first_segment)
        if not code_match:
            code_match = re.match(r"^([A-Za-z]{2,4}[0-9]{2,4}[A-Za-z]?)$", first_segment)

        if code_match:
            course_code = first_segment
            course_name_str = " ".join(non_prof_segments[1:]) if len(non_prof_segments) > 1 else course_code
            print(f"[PARSER] Course Code: '{course_code}', Course Name String: '{course_name_str}'")
        else:
            course_name_str = " ".join(non_prof_segments)
            course_code = "N/A"
            print(f"[PARSER] No clear Course Code, Course Name String: '{course_name_str}'")
    else:
        course_name_str = base_name_no_ext
        print(f"[PARSER] No segments for course, Course Name String from base: '{course_name_str}'")

    if not course_name_str.strip() and course_code != "N/A":
        course_name_str = course_code

    final_course_display_name = course_name_str.replace("_", " ").strip()
    if not final_course_display_name:
        final_course_display_name = base_name_no_ext

    print(f"[PARSER] Final -> Prof: '{professor_name}', CourseDisplay: '{final_course_display_name}', Code: '{course_code}'")
    return professor_name, final_course_display_name, course_code

def create_professor_course_files_map(uploaded_files_list):
    professor_map = {}
    print(f"[MAPPER] Input files for map: {uploaded_files_list}")
    if not uploaded_files_list:
        print("[MAPPER] No files to map, returning empty professor_map.")
        return professor_map

    for f_name in uploaded_files_list:
        if f_name.startswith('.'): continue

        professor, display_course_name, _ = get_professor_and_course_from_filename(f_name)
        
        if professor not in professor_map:
            professor_map[professor] = []
        
        course_entry = {
            "filename": f_name,
            "display_coursename": display_course_name if display_course_name else f_name.rsplit('.',1)[0]
        }
        professor_map[professor].append(course_entry)
        print(f"[MAPPER] Added to map: Prof='{professor}', CourseEntry='{course_entry}'")
    
    for prof in professor_map:
        professor_map[prof].sort(key=lambda x: x['display_coursename'])
        
    print(f"[MAPPER] Generated professor_map: {professor_map}")
    return professor_map

def get_uploaded_files():
    upload_folder_path = app.config['UPLOAD_FOLDER']
    if not os.path.isdir(upload_folder_path):
        print(f"Error: UPLOAD_FOLDER '{upload_folder_path}' is not a directory or does not exist.")
        return []
    try:
        all_items = os.listdir(upload_folder_path)
        files_only = [
            f for f in all_items
            if os.path.isfile(os.path.join(upload_folder_path, f)) and not f.startswith('.')
        ]
        return sorted(files_only)
    except Exception as e:
        print(f"Error in get_uploaded_files for path {upload_folder_path}: {e}")
        return []

def load_master_file():
    """Load the master file containing student information"""
    master_folder = app.config['MASTER_FILE_FOLDER']
    master_files = [f for f in os.listdir(master_folder) if f.endswith(('.xlsx', '.xls', '.csv')) and not f.startswith('.')]
    
    if not master_files:
        return None
    
    # Use the most recent master file
    master_file = sorted(master_files, key=lambda x: os.path.getmtime(os.path.join(master_folder, x)), reverse=True)[0]
    master_path = os.path.join(master_folder, master_file)
    
    try:
        if master_file.lower().endswith(('.xlsx', '.xls')):
            df = pd.read_excel(master_path)
        elif master_file.lower().endswith('.csv'):
            df = pd.read_csv(master_path)
        else:
            return None
        
        # Normalize column names
        df.columns = df.columns.str.strip()
        
        # Try to find ID column
        id_col = None
        for col in df.columns:
            col_lower = str(col).lower()
            if any(keyword in col_lower for keyword in ['id', 'student id', 'student_id', 'student number']):
                id_col = col
                break
        
        if not id_col and len(df.columns) > 0:
            id_col = df.columns[0]
        
        if id_col:
            df[id_col] = df[id_col].astype(str).str.strip()
            return df, id_col
        return None
    except Exception as e:
        print(f"Error loading master file: {e}")
        return None

def merge_with_master(instructor_df, instructor_id_col):
    """Merge instructor data with master file data"""
    master_data = load_master_file()
    if master_data is None:
        return instructor_df, None
    
    master_df, master_id_col = master_data
    
    # Normalize ID column in instructor data
    instructor_df[instructor_id_col] = instructor_df[instructor_id_col].astype(str).str.strip()
    
    # Merge on ID
    merged_df = instructor_df.merge(
        master_df,
        left_on=instructor_id_col,
        right_on=master_id_col,
        how='left'
    )
    
    # Find Major, Status, Advisor columns in master
    major_col = None
    status_col = None
    advisor_col = None
    
    for col in master_df.columns:
        col_lower = str(col).lower()
        if 'major' in col_lower and not major_col:
            major_col = col
        if 'status' in col_lower and not status_col:
            status_col = col
        if 'advisor' in col_lower and not advisor_col:
            advisor_col = col
    
    return merged_df, {'major': major_col, 'status': status_col, 'advisor': advisor_col}

# --- Authentication Decorators ---
def login_required(func):
    def wrapper(*args, **kwargs):
        if not session.get('logged_in'):
            return redirect(url_for('login'))
        return func(*args, **kwargs)
    wrapper.__name__ = func.__name__
    return wrapper

def admin_required(func):
    def wrapper(*args, **kwargs):
        if not session.get('logged_in'):
            return redirect(url_for('login'))
        if session.get('role') != 'admin':
            flash('Admin access required', 'danger')
            return redirect(url_for('index'))
        return func(*args, **kwargs)
    wrapper.__name__ = func.__name__
    return wrapper

def instructor_required(func):
    def wrapper(*args, **kwargs):
        if not session.get('logged_in'):
            return redirect(url_for('login'))
        if session.get('role') != 'instructor':
            flash('Instructor access required', 'danger')
            return redirect(url_for('index'))
        return func(*args, **kwargs)
    wrapper.__name__ = func.__name__
    return wrapper

# --- Routes ---
@app.route('/login', methods=['GET', 'POST'])
def login():
    if 'logged_in' in session:
        return redirect(url_for('index'))
    
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        conn = get_db()
        user = conn.execute('SELECT * FROM users WHERE username = ?', (username,)).fetchone()
        conn.close()
        
        if user and check_password_hash(user['password_hash'], password):
            session['logged_in'] = True
            session['user_id'] = user['id']
            session['username'] = user['username']
            session['role'] = user['role']
            session['full_name'] = user['full_name']
            session['password_changed'] = user['password_changed']
            
            # Redirect instructors to change password if not changed
            if user['role'] == 'instructor' and not user['password_changed']:
                flash('Please change your default password', 'warning')
                return redirect(url_for('change_password'))
            
            flash('Login successful!', 'success')
            return redirect(url_for('index'))
        else:
            flash('Invalid username or password', 'danger')
    
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    flash('You have been logged out.', 'info')
    return redirect(url_for('login'))

@app.route('/change-password', methods=['GET', 'POST'])
@login_required
def change_password():
    if request.method == 'POST':
        current_password = request.form.get('current_password', '').strip()
        new_password = request.form.get('new_password', '').strip()
        confirm_password = request.form.get('confirm_password', '').strip()
        
        if not current_password or not new_password or not confirm_password:
            flash('All fields are required', 'danger')
            return render_template('change_password.html')
        
        if new_password != confirm_password:
            flash('New passwords do not match', 'danger')
            return render_template('change_password.html')
        
        # Check password length after stripping whitespace
        if len(new_password) < 6:
            flash(f'Password must be at least 6 characters (you entered {len(new_password)} characters)', 'danger')
            return render_template('change_password.html')
        
        conn = get_db()
        user = conn.execute('SELECT * FROM users WHERE id = ?', (session['user_id'],)).fetchone()
        
        if user and check_password_hash(user['password_hash'], current_password):
            new_password_hash = generate_password_hash(new_password, method='pbkdf2:sha256')
            conn.execute('UPDATE users SET password_hash = ?, password_changed = 1 WHERE id = ?',
                        (new_password_hash, session['user_id']))
            conn.commit()
            conn.close()
            
            session['password_changed'] = 1
            flash('Password changed successfully!', 'success')
            return redirect(url_for('index'))
        else:
            conn.close()
            flash('Current password is incorrect', 'danger')
    
    return render_template('change_password.html')

@app.route('/')
@login_required
def index():
    if session.get('role') == 'admin':
        return redirect(url_for('admin_dashboard'))
    elif session.get('role') == 'instructor':
        return redirect(url_for('instructor_dashboard'))
    return redirect(url_for('login'))

# --- Admin Routes ---
@app.route('/admin')
@admin_required
def admin_dashboard():
    uploaded_files_list = get_uploaded_files()
    professor_course_files_map_data = create_professor_course_files_map(uploaded_files_list)
    
    # Get submission information
    conn = get_db()
    submissions = conn.execute('''
        SELECT s.*, u.username, u.full_name 
        FROM submissions s 
        JOIN users u ON s.instructor_id = u.id 
        ORDER BY s.submitted_at DESC
    ''').fetchall()
    
    # Get all instructors
    instructors = conn.execute('SELECT * FROM users WHERE role = ?', ('instructor',)).fetchall()
    
    # Get list of instructors who have submitted
    submitted_instructor_ids = set()
    for sub in submissions:
        submitted_instructor_ids.add(sub['instructor_id'])
    
    # Create instructor status list (submitted vs not submitted)
    instructor_status = []
    for instructor in instructors:
        has_submitted = instructor['id'] in submitted_instructor_ids
        # Get submission count for this instructor
        sub_count = conn.execute('SELECT COUNT(*) FROM submissions WHERE instructor_id = ?', 
                                (instructor['id'],)).fetchone()[0]
        instructor_status.append({
            'id': instructor['id'],
            'username': instructor['username'],
            'full_name': instructor['full_name'],
            'has_submitted': has_submitted,
            'submission_count': sub_count
        })
    
    conn.close()
    
    # Create a map of filename to instructor
    file_to_instructor = {}
    for sub in submissions:
        file_to_instructor[sub['filename']] = {
            'instructor': sub['full_name'] or sub['username'],
            'submitted_at': sub['submitted_at']
        }
    
    return render_template('admin_dashboard.html',
                         uploaded_files=uploaded_files_list,
                         selected_file=None,
                         professor_course_files_map=professor_course_files_map_data,
                         grouped_course_data=None,
                         selected_file_display_name=None,
                         course_display_name_for_title=None,
                         submissions=submissions,
                         instructors=instructors,
                         instructor_status=instructor_status,
                         file_to_instructor=file_to_instructor)

@app.route('/admin/create-instructor', methods=['GET', 'POST'])
@admin_required
def create_instructor():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password', 'instructor@2025')  # Default password
        full_name = request.form.get('full_name', '')
        
        if not username:
            flash('Username is required', 'danger')
            return render_template('create_instructor.html')
        
        conn = get_db()
        # Check if username exists
        existing = conn.execute('SELECT * FROM users WHERE username = ?', (username,)).fetchone()
        if existing:
            conn.close()
            flash('Username already exists', 'danger')
            return render_template('create_instructor.html')
        
        password_hash = generate_password_hash(password, method='pbkdf2:sha256')
        conn.execute('INSERT INTO users (username, password_hash, role, full_name) VALUES (?, ?, ?, ?)',
                    (username, password_hash, 'instructor', full_name))
        conn.commit()
        conn.close()
        
        flash(f'Instructor account created successfully! Default password: {password}', 'success')
        return redirect(url_for('admin_dashboard'))
    
    return render_template('create_instructor.html')

@app.route('/admin/manage-accounts', methods=['GET'])
@admin_required
def manage_accounts():
    """View and manage all instructor accounts"""
    conn = get_db()
    instructors = conn.execute('SELECT * FROM users WHERE role = ? ORDER BY created_at DESC', ('instructor',)).fetchall()
    
    # Get submission count for each instructor
    instructor_list = []
    for instructor in instructors:
        sub_count = conn.execute('SELECT COUNT(*) FROM submissions WHERE instructor_id = ?', 
                                (instructor['id'],)).fetchone()[0]
        instructor_list.append({
            'id': instructor['id'],
            'username': instructor['username'],
            'full_name': instructor['full_name'],
            'created_at': instructor['created_at'],
            'password_changed': instructor['password_changed'],
            'submission_count': sub_count
        })
    
    conn.close()
    return render_template('manage_accounts.html', instructors=instructor_list)

@app.route('/admin/delete-account/<int:user_id>', methods=['POST'])
@admin_required
def delete_account(user_id):
    """Delete an instructor account"""
    conn = get_db()
    
    # Check if user exists and is an instructor
    user = conn.execute('SELECT * FROM users WHERE id = ? AND role = ?', (user_id, 'instructor')).fetchone()
    
    if not user:
        conn.close()
        flash('User not found or cannot be deleted', 'danger')
        return redirect(url_for('manage_accounts'))
    
    # Prevent deleting own account if somehow an admin tries
    if user_id == session.get('user_id'):
        conn.close()
        flash('You cannot delete your own account', 'danger')
        return redirect(url_for('manage_accounts'))
    
    try:
        # Delete all submissions by this instructor
        conn.execute('DELETE FROM submissions WHERE instructor_id = ?', (user_id,))
        
        # Delete the user account
        conn.execute('DELETE FROM users WHERE id = ?', (user_id,))
        conn.commit()
        conn.close()
        
        flash(f'Account for {user["username"]} has been deleted successfully', 'success')
    except Exception as e:
        conn.rollback()
        conn.close()
        flash(f'Error deleting account: {str(e)}', 'danger')
        app.logger.error(f"Error deleting account {user_id}: {e}", exc_info=True)
    
    return redirect(url_for('manage_accounts'))

@app.route('/admin/upload-master', methods=['GET', 'POST'])
@admin_required
def upload_master():
    if request.method == 'POST':
        if 'file' not in request.files:
            flash('No file part', 'danger')
            return redirect(request.url)
        
        file = request.files['file']
        if file.filename == '':
            flash('No selected file', 'danger')
            return redirect(request.url)
        
        if file:
            filename = secure_filename(file.filename)
            file_path = os.path.join(app.config['MASTER_FILE_FOLDER'], filename)
            try:
                file.save(file_path)
                flash(f'Master file "{filename}" uploaded successfully.', 'success')
            except Exception as e:
                flash(f'Error saving file: {str(e)}', 'danger')
    
    return render_template('upload_master.html')

@app.route('/upload', methods=['GET', 'POST'])
@admin_required
def upload_file_route():
    """Admin manual upload route"""
    if request.method == 'POST':
        if 'file' not in request.files:
            flash('No file part', 'danger')
            return redirect(request.url)
        file = request.files['file']
        if file.filename == '':
            flash('No selected file', 'danger')
            return redirect(request.url)

        if file:
            filename = secure_filename(file.filename)
            if not filename:
                flash('Invalid filename after securing.', 'danger')
                return redirect(request.url)
            file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            try:
                file.save(file_path)
                flash(f'File "{filename}" successfully uploaded.', 'success')
                return redirect(url_for('view_file_route', filename=filename))
            except Exception as e:
                flash(f'Error saving file: {str(e)}', 'danger')
                app.logger.error(f"Error saving {filename}: {e}", exc_info=True)
    
    return redirect(url_for('admin_dashboard'))

# --- Instructor Routes ---
@app.route('/instructor')
@instructor_required
def instructor_dashboard():
    return render_template('instructor_dashboard.html')

@app.route('/instructor/download-template')
@instructor_required
def download_template():
    # Create a template Excel file with example row
    template_data = {
        'ID': ['12345'],
        'Name': ['Example Student'],
        'Course': ['Example Course'],
        'Grade': [85]
    }
    df = pd.DataFrame(template_data)
    
    # Create Excel file in memory
    output = BytesIO()
    try:
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name='Grades')
        output.seek(0)
        
        return send_file(output, mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                        as_attachment=True, download_name='Grade_Template.xlsx')
    except Exception as e:
        flash(f'Error creating template: {str(e)}', 'danger')
        return redirect(url_for('instructor_dashboard'))

def validate_filename_format(filename):
    """
    Validate filename follows format: CourseCode_CourseName_InstructorName.ext
    Returns (is_valid, error_message)
    """
    if not filename or '.' not in filename:
        return False, "Filename must have an extension"
    
    base_name = filename.rsplit('.', 1)[0]
    parts = base_name.split('_')
    
    if len(parts) < 3:
        return False, "Filename must follow format: CourseCode_CourseName_InstructorName (e.g., BCS201_LogicForComputerScience_DrHamza)"
    
    # Check if first part looks like a course code (letters followed by numbers)
    course_code_match = re.match(r"^[A-Za-z]{2,6}[0-9]{2,4}[A-Za-z0-9]*$", parts[0])
    if not course_code_match:
        return False, f"First part '{parts[0]}' does not look like a valid course code (e.g., BCS201, ENG102)"
    
    # Check if last part looks like an instructor name (should have letters)
    instructor_part = parts[-1]
    if not re.search(r'[A-Za-z]', instructor_part):
        return False, f"Last part '{instructor_part}' does not look like an instructor name"
    
    return True, None

@app.route('/instructor/upload', methods=['GET', 'POST'])
@instructor_required
def instructor_upload():
    if request.method == 'POST':
        if 'file' not in request.files:
            flash('No file part', 'danger')
            return redirect(request.url)
        
        file = request.files['file']
        if file.filename == '':
            flash('No selected file', 'danger')
            return redirect(request.url)
        
        if file:
            filename = secure_filename(file.filename)
            
            # Validate filename format
            is_valid, error_msg = validate_filename_format(filename)
            if not is_valid:
                flash(f'Invalid filename format: {error_msg}. Please use format: CourseCode_CourseName_InstructorName (e.g., BCS201_LogicForComputerScience_DrHamza.xlsx)', 'danger')
                return redirect(request.url)
            
            file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            
            try:
                # Save the file temporarily to process it
                temp_path = os.path.join(app.config['UPLOAD_FOLDER'], 'temp_' + filename)
                file.save(temp_path)
                
                # Read the instructor file
                if filename.lower().endswith(('.xlsx', '.xls')):
                    df = pd.read_excel(temp_path)
                elif filename.lower().endswith('.csv'):
                    df = pd.read_csv(temp_path)
                else:
                    os.remove(temp_path)
                    flash('Unsupported file type', 'danger')
                    return redirect(request.url)
                
                # Find ID column
                id_col = None
                for col in df.columns:
                    col_lower = str(col).lower()
                    if any(keyword in col_lower for keyword in ['id', 'student id', 'student_id', 'student number']):
                        id_col = col
                        break
                
                if not id_col and len(df.columns) > 0:
                    id_col = df.columns[0]
                
                if not id_col:
                    os.remove(temp_path)
                    flash('Could not identify ID column in file', 'danger')
                    return redirect(request.url)
                
                # Merge with master file
                merged_df, master_cols = merge_with_master(df, id_col)
                
                # Save merged file
                if filename.lower().endswith('.csv'):
                    merged_df.to_csv(file_path, index=False)
                else:
                    merged_df.to_excel(file_path, index=False)
                
                # Remove temp file
                os.remove(temp_path)
                
                # Record submission
                professor, course_display, _ = get_professor_and_course_from_filename(filename)
                conn = get_db()
                conn.execute('INSERT INTO submissions (instructor_id, filename, course_name) VALUES (?, ?, ?)',
                           (session['user_id'], filename, course_display))
                conn.commit()
                conn.close()
                
                flash(f'File "{filename}" uploaded and merged successfully!', 'success')
                return redirect(url_for('instructor_dashboard'))
                
            except Exception as e:
                if os.path.exists(temp_path):
                    os.remove(temp_path)
                flash(f'Error processing file: {str(e)}', 'danger')
                app.logger.error(f"Error processing {filename}: {e}", exc_info=True)
    
    return render_template('instructor_upload.html')

# --- Shared Routes (for both admin and instructor) ---
@app.route('/view-file', methods=['GET'])
@login_required
def view_file_route():
    uploaded_files_list = get_uploaded_files()
    professor_course_files_map_data = create_professor_course_files_map(uploaded_files_list)
    filename = request.args.get('filename')
    
    current_professor_for_title = None
    current_course_display_name_for_title = None

    if filename and filename in uploaded_files_list:
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        try:
            df = None
            if filename.lower().endswith(('.xlsx', '.xls')):
                df = pd.read_excel(file_path)
            elif filename.lower().endswith('.csv'):
                df = pd.read_csv(file_path)
            else:
                flash(f"Unsupported file type: {filename}", "warning")
                return render_template('upload.html', uploaded_files=uploaded_files_list, selected_file=filename, 
                                    professor_course_files_map=professor_course_files_map_data, 
                                    grouped_course_data=None, selected_file_display_name=filename, 
                                    course_display_name_for_title="Unsupported File")

            current_professor_for_title, current_course_display_name_for_title, _ = get_professor_and_course_from_filename(filename)

            grouped_course_data_for_view = {
                current_professor_for_title: [{
                    "course_name": current_course_display_name_for_title,
                    "table_html": df.to_html(classes='data dataframe', index=False, escape=False)
                }]
            }
            
            # Get submission info if admin
            file_to_instructor = {}
            if session.get('role') == 'admin':
                conn = get_db()
                sub = conn.execute('SELECT s.*, u.username, u.full_name FROM submissions s JOIN users u ON s.instructor_id = u.id WHERE s.filename = ?', 
                                 (filename,)).fetchone()
                conn.close()
                if sub:
                    file_to_instructor[filename] = {
                        'instructor': sub['full_name'] or sub['username'],
                        'submitted_at': sub['submitted_at']
                    }
            
            return render_template('upload.html',
                               grouped_course_data=grouped_course_data_for_view,
                               uploaded_files=uploaded_files_list,
                               selected_file=filename,
                               professor_course_files_map=professor_course_files_map_data,
                               selected_file_display_name=current_course_display_name_for_title,
                               course_display_name_for_title=current_course_display_name_for_title,
                               file_to_instructor=file_to_instructor)
        except Exception as e:
            flash(f"Error processing file {filename}: {str(e)}", "danger")
            app.logger.error(f"Error viewing {filename}: {e}", exc_info=True)
            prof_temp, course_temp, _ = get_professor_and_course_from_filename(filename)
            current_professor_for_title = prof_temp
            current_course_display_name_for_title = course_temp

    # Get submission info for fallback case
    file_to_instructor = {}
    if session.get('role') == 'admin' and filename:
        conn = get_db()
        sub = conn.execute('SELECT s.*, u.username, u.full_name FROM submissions s JOIN users u ON s.instructor_id = u.id WHERE s.filename = ?', 
                         (filename,)).fetchone()
        conn.close()
        if sub:
            file_to_instructor[filename] = {
                'instructor': sub['full_name'] or sub['username'],
                'submitted_at': sub['submitted_at']
            }
    
    return render_template('upload.html',
                       uploaded_files=uploaded_files_list,
                       selected_file=filename if filename and filename in uploaded_files_list else None,
                       professor_course_files_map=professor_course_files_map_data,
                       grouped_course_data=None,
                       selected_file_display_name=current_course_display_name_for_title,
                       course_display_name_for_title=current_course_display_name_for_title,
                       file_to_instructor=file_to_instructor)

@app.route('/risk-analysis', methods=['GET'])
@login_required
def risk_analysis_route():
    students_at_risk = analyze_student_data()
    return render_template('risk_analysis.html', students_at_risk=students_at_risk)

def analyze_borderline_students():
    """Analyze all borderline students across all courses"""
    all_files = get_uploaded_files()
    borderline_students = []
    SPECIFIC_BORDERLINE_GRADES = [54, 59, 64, 69, 74, 79, 88, 89]
    
    # Get instructor information from submissions
    conn = get_db()
    submissions_map = {}
    for sub in conn.execute('SELECT s.filename, u.full_name, u.username FROM submissions s JOIN users u ON s.instructor_id = u.id').fetchall():
        submissions_map[sub['filename']] = sub['full_name'] or sub['username']
    conn.close()

    for file_name in all_files:
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], file_name)
        try:
            df = None
            if file_name.lower().endswith(('.xlsx', '.xls')):
                df = pd.read_excel(file_path)
            elif file_name.lower().endswith('.csv'):
                df = pd.read_csv(file_path)
            else:
                continue
            
            if df is None or df.empty: continue

            # Robust grade column identification
            grade_col_name = None
            grade_keywords = ['numerical grade', 'final mark', 'final grade', 'overall grade', 'total mark', 'total', 'grade']
            for col in df.columns:
                col_lower = str(col).lower()
                if any(keyword in col_lower for keyword in grade_keywords):
                    grade_col_name = col
                    break
            
            if not grade_col_name:
                if df.shape[1] >= 4:
                    grade_col_name = df.columns[df.shape[1] - 4]
                else:
                    continue
            
            df[grade_col_name] = pd.to_numeric(df[grade_col_name], errors='coerce')
            df.dropna(subset=[grade_col_name], inplace=True)

            # Filter for borderline grades
            borderline_in_file = df[df[grade_col_name].apply(lambda x: x >= 0 and math.floor(x) in SPECIFIC_BORDERLINE_GRADES if pd.notna(x) else False)]

            professor, course_display, _ = get_professor_and_course_from_filename(file_name)
            
            # Get instructor from submissions map, fallback to professor name from filename
            instructor_name = submissions_map.get(file_name, professor)

            for record in borderline_in_file.to_dict(orient='records'):
                record['professor'] = professor
                record['course'] = course_display
                record['source_file'] = file_name
                record['Instructor'] = instructor_name
                
                # Normalize column names for display
                for key in list(record.keys()):
                    if 'major' in str(key).lower():
                        record['Major'] = record.pop(key)
                    elif 'status' in str(key).lower():
                        record['Status'] = record.pop(key)
                    elif 'advisor' in str(key).lower():
                        record['Advisor'] = record.pop(key)
                    elif 'id' in str(key).lower() and 'ID' not in record:
                        record['ID'] = record.pop(key)
                    elif 'name' in str(key).lower() and 'Name' not in record:
                        record['Name'] = record.pop(key)
                    elif 'grade' in str(key).lower() and 'Grade' not in record:
                        record['Grade'] = record.pop(key)
                
                borderline_students.append(record)
            
        except Exception as e:
            print(f"Error processing file {file_name} for borderline analysis: {e}")
            app.logger.error(f"Borderline analysis error in {file_name}: {e}", exc_info=True)
    return borderline_students

@app.route('/admin/view-all-borders')
@admin_required
def view_all_borders():
    """View all borderline students across all courses"""
    borderline_students = analyze_borderline_students()
    return render_template('view_all_borders.html', borderline_students=borderline_students)

@app.route('/admin/delete-courses', methods=['GET', 'POST'])
@admin_required
def delete_courses():
    """Delete courses with checkbox selection"""
    if request.method == 'POST':
        selected_files = request.form.getlist('selected_files')
        
        if not selected_files:
            flash('No courses selected for deletion', 'warning')
            return redirect(url_for('delete_courses'))
        
        deleted_count = 0
        failed_count = 0
        failed_files = []
        
        # Open database connection once
        conn = get_db()
        
        try:
            for filename in selected_files:
                try:
                    # Delete file from uploads folder
                    file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                    if os.path.exists(file_path):
                        os.remove(file_path)
                        print(f"Deleted file: {file_path}")
                    
                    # Delete from database submissions
                    conn.execute('DELETE FROM submissions WHERE filename = ?', (filename,))
                    deleted_count += 1
                    print(f"Deleted database record for: {filename}")
                    
                except Exception as e:
                    print(f"Error deleting file {filename}: {e}")
                    failed_count += 1
                    failed_files.append(filename)
                    app.logger.error(f"Error deleting {filename}: {e}", exc_info=True)
            
            # Commit all database deletions at once
            conn.commit()
            
        except Exception as e:
            conn.rollback()
            print(f"Database error during deletion: {e}")
            flash(f'Database error during deletion: {str(e)}', 'danger')
        finally:
            conn.close()
        
        if failed_count == 0:
            flash(f'Successfully deleted {deleted_count} course file(s)', 'success')
        else:
            flash(f'Deleted {deleted_count} file(s), {failed_count} failed: {", ".join(failed_files)}', 'warning')
        
        return redirect(url_for('delete_courses'))
    
    # GET request - show list of courses
    uploaded_files_list = get_uploaded_files()
    professor_course_files_map_data = create_professor_course_files_map(uploaded_files_list)
    
    # Get submission info for each file
    conn = get_db()
    file_to_instructor = {}
    for sub in conn.execute('SELECT s.*, u.username, u.full_name FROM submissions s JOIN users u ON s.instructor_id = u.id').fetchall():
        file_to_instructor[sub['filename']] = {
            'instructor': sub['full_name'] or sub['username'],
            'submitted_at': sub['submitted_at'],
            'course_name': sub['course_name']
        }
    conn.close()
    
    # Create a flat list of all courses with their info
    all_courses = []
    for professor, course_list in professor_course_files_map_data.items():
        for course_info in course_list:
            filename = course_info['filename']
            submission_info = file_to_instructor.get(filename, {})
            all_courses.append({
                'filename': filename,
                'display_name': course_info['display_coursename'],
                'professor': professor,
                'instructor': submission_info.get('instructor', 'N/A'),
                'submitted_at': submission_info.get('submitted_at', 'N/A'),
                'course_name': submission_info.get('course_name', 'N/A')
            })
    
    return render_template('delete_courses.html', all_courses=all_courses)

@app.route('/admin/view-all-submissions')
@admin_required
def view_all_submissions():
    """View all instructor submissions in detail"""
    conn = get_db()
    submissions = conn.execute('''
        SELECT s.*, u.username, u.full_name 
        FROM submissions s 
        JOIN users u ON s.instructor_id = u.id 
        ORDER BY s.submitted_at DESC
    ''').fetchall()
    
    # Get all instructors with their submission status
    instructors = conn.execute('SELECT * FROM users WHERE role = ?', ('instructor',)).fetchall()
    submitted_instructor_ids = set()
    for sub in submissions:
        submitted_instructor_ids.add(sub['instructor_id'])
    
    instructor_status = []
    for instructor in instructors:
        has_submitted = instructor['id'] in submitted_instructor_ids
        sub_count = conn.execute('SELECT COUNT(*) FROM submissions WHERE instructor_id = ?', 
                                (instructor['id'],)).fetchone()[0]
        instructor_status.append({
            'id': instructor['id'],
            'username': instructor['username'],
            'full_name': instructor['full_name'],
            'has_submitted': has_submitted,
            'submission_count': sub_count
        })
    
    conn.close()
    
    return render_template('view_all_submissions.html', 
                         submissions=submissions,
                         instructor_status=instructor_status)

def analyze_student_data():
    all_files = get_uploaded_files()
    students_at_risk = []
    
    # Get instructor information from submissions
    conn = get_db()
    submissions_map = {}
    for sub in conn.execute('SELECT s.filename, u.full_name, u.username FROM submissions s JOIN users u ON s.instructor_id = u.id').fetchall():
        submissions_map[sub['filename']] = sub['full_name'] or sub['username']
    conn.close()

    for file_name in all_files:
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], file_name)
        try:
            df = None
            if file_name.lower().endswith(('.xlsx', '.xls')):
                df = pd.read_excel(file_path)
            elif file_name.lower().endswith('.csv'):
                df = pd.read_csv(file_path)
            else:
                continue
            
            if df is None or df.empty: continue

            # Robust grade column identification
            grade_col_name = None
            grade_keywords = ['numerical grade', 'final mark', 'final grade', 'overall grade', 'total mark', 'total', 'grade']
            for col in df.columns:
                col_lower = str(col).lower()
                if any(keyword in col_lower for keyword in grade_keywords):
                    grade_col_name = col
                    break
            
            if not grade_col_name:
                if df.shape[1] >= 4:
                    grade_col_name = df.columns[df.shape[1] - 4]
                    print(f"Warning: Grade column not found by name in {file_name}. Using fallback: {grade_col_name}")
                else:
                    print(f"Error: Not enough columns or grade column not found in {file_name} for risk analysis.")
                    continue
            
            df[grade_col_name] = pd.to_numeric(df[grade_col_name], errors='coerce')
            df.dropna(subset=[grade_col_name], inplace=True)

            at_risk_in_file = df[df[grade_col_name] < 50]

            professor, course_display, _ = get_professor_and_course_from_filename(file_name)
            
            # Get instructor from submissions map, fallback to professor name from filename
            instructor_name = submissions_map.get(file_name, professor)

            for record in at_risk_in_file.to_dict(orient='records'):
                # Try to get Major, Status, Advisor from merged data
                record['professor'] = professor
                record['course'] = course_display
                record['source_file'] = file_name
                record['Instructor'] = instructor_name  # Add instructor column
                
                # Normalize column names for display
                for key in list(record.keys()):
                    if 'major' in str(key).lower():
                        record['Major'] = record.pop(key)
                    elif 'status' in str(key).lower():
                        record['Status'] = record.pop(key)
                    elif 'advisor' in str(key).lower():
                        record['Advisor'] = record.pop(key)
                    elif 'id' in str(key).lower() and 'ID' not in record:
                        record['ID'] = record.pop(key)
                    elif 'name' in str(key).lower() and 'Name' not in record:
                        record['Name'] = record.pop(key)
                    elif 'grade' in str(key).lower() and 'Grade' not in record:
                        record['Grade'] = record.pop(key)
                
                students_at_risk.append(record)
            
        except Exception as e:
            print(f"Error processing file {file_name} for risk analysis: {e}")
            app.logger.error(f"Risk analysis error in {file_name}: {e}", exc_info=True)
    return students_at_risk

@app.route('/api/search-student/<student_id>', methods=['GET'])
@login_required
def api_search_student(student_id):
    all_uploaded_files = get_uploaded_files()
    found_records = []

    for file_name in all_uploaded_files:
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], file_name)
        try:
            df = None
            if file_name.lower().endswith(('.xlsx', '.xls')):
                df = pd.read_excel(file_path)
            elif file_name.lower().endswith('.csv'):
                df = pd.read_csv(file_path)
            else: continue
            if df is None or df.empty: continue

            student_id_col_name, student_name_col_name, grade_col_name = None, None, None
            id_keywords = ['student id', 'id', 'student_id', 'student number', 'student no']
            name_keywords = ['student name', 'name']
            grade_keywords = ['numerical grade', 'final mark', 'final grade', 'overall grade', 'total mark', 'total', 'grade']

            for col in df.columns:
                col_lower = str(col).lower()
                if not student_id_col_name and any(keyword in col_lower for keyword in id_keywords):
                    student_id_col_name = col
                if not student_name_col_name and any(keyword in col_lower for keyword in name_keywords):
                    student_name_col_name = col
                if not grade_col_name and any(keyword in col_lower for keyword in grade_keywords):
                    grade_col_name = col
            
            if not student_id_col_name and len(df.columns) > 0: student_id_col_name = df.columns[0]
            if not student_name_col_name and len(df.columns) > 1: student_name_col_name = df.columns[1]
            if not grade_col_name and len(df.columns) >= 4: grade_col_name = df.columns[df.shape[1] - 4]

            if not student_id_col_name or not grade_col_name:
                print(f"Skipping {file_name} for student search: Critical columns (ID or Grade) not identified.")
                continue
            
            df[student_id_col_name] = df[student_id_col_name].astype(str).str.strip()
            student_rows = df[df[student_id_col_name] == str(student_id).strip()]

            if not student_rows.empty:
                professor, course_display, _ = get_professor_and_course_from_filename(file_name)
                for index, row_data in student_rows.iterrows():
                    num_grade = pd.to_numeric(row_data.get(grade_col_name), errors='coerce')
                    s_name = str(row_data.get(student_name_col_name, "N/A")).strip() if student_name_col_name else "N/A"
                    
                    record = {
                        "studentId": str(row_data.get(student_id_col_name)).strip(),
                        "studentName": s_name,
                        "professor": professor,
                        "course": course_display,
                        "numericalGrade": float(num_grade) if pd.notna(num_grade) else None,
                    }
                    found_records.append(record)
        except Exception as e_file:
            print(f"Error processing file {file_name} for student search: {e_file}")
            app.logger.error(f"Student search error in {file_name}: {e_file}", exc_info=True)

    if not found_records:
        return jsonify({"error": f"No records found for Student ID {student_id}"}), 404
    return jsonify(found_records)

if __name__ == '__main__':
    app.run(debug=True, host='192.168.0.152', port=6001, use_reloader=False)

    #flask run -h 10.100.81.52 -p 5005
    #find . -name '*.DS_Store' -type f -delete
    #ngrok http http://10.100.81.42:5005  
    #ipconfig getifaddr en0  