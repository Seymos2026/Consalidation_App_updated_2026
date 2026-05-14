# Student Grade Analysis System

A Flask-based application for managing student grades with role-based access control for administrators and instructors.

## Features

### Admin Features
- View all uploaded grade files
- Create instructor accounts with default passwords
- Upload master file containing student information (ID, Major, Status, Advisor)
- View instructor submissions with tracking
- Risk analysis across all courses
- Search student records across all courses
- Manual file upload capability

### Instructor Features
- Download grade template (Excel format)
- Upload grade files (automatically merged with master file)
- Change password after first login
- View uploaded files

## Installation

1. Install required dependencies:
```bash
pip install -r requirements.txt
```

2. Run the application:
```bash
python app.py
```

3. Access the application at: `http://192.168.0.146:6001` (or the configured host/port)

## Pushing to GitHub

1. Create a new empty repository on [GitHub](https://github.com/new) (no README required if you already have files locally).
2. In your project folder:
   ```bash
   git init   # only if this folder is not already a git repository
   git add .
   git commit -m "Initial commit"
   git remote add origin https://github.com/YOUR_USER/YOUR_REPO.git
   git branch -M main
   git push -u origin main
   ```
3. Use a **Personal Access Token** (HTTPS) or **SSH keys** when GitHub prompts for authentication.
4. Do **not** commit secrets: add `.env`, local `app.db`, and `uploads/` (if they contain private data) to `.gitignore`. Set `SECRET_KEY` and `DATABASE_URL` only in Render’s environment, not in the repo.

## Deploying on Render (with PostgreSQL)

On Render, the server disk is **temporary**. Users and submissions are stored in the database when you use PostgreSQL; uploaded grade files still live on disk unless you add persistent storage or object storage later.

### 1. Create the PostgreSQL database

1. In the [Render Dashboard](https://dashboard.render.com), click **New +** → **PostgreSQL**.
2. Choose a name, region, and instance type, then create the database.
3. Wait until the database shows as **Available**. You do not need to copy the URL by hand if you link the service in the next section.

### 2. Create the Web Service from GitHub

1. **New +** → **Web Service**.
2. Connect your **GitHub** account and select this repository.
3. Configure the service:
   - **Name**: any name (e.g. `grade-analysis`).
   - **Region**: pick the **same region** as the PostgreSQL instance when possible (lower latency).
   - **Branch**: `main` (or the branch you deploy from).
   - **Root directory**: leave blank if `app.py` and `requirements.txt` are at the repo root.
   - **Runtime**: Python 3.
   - **Build command**: `pip install -r requirements.txt` (Render often fills this automatically).
   - **Start command**: leave default if Render detects the `Procfile` (`web: gunicorn app:app`). Otherwise set: `gunicorn app:app`.

### 3. Attach Postgres and set environment variables

1. Open your **Web Service** → **Environment**.
2. Under **Link database**, select the PostgreSQL instance you created. Render injects **`DATABASE_URL`** into the web service automatically. The app uses this for PostgreSQL and keeps **`app.db` (SQLite)** only when `DATABASE_URL` is not set (local development).
3. Add **`SECRET_KEY`**: a long random string (used for Flask sessions). Example generation on your Mac: `python3 -c "import secrets; print(secrets.token_hex(32))"`.
4. Save and trigger a **Manual Deploy** (or push a new commit) so the service restarts with the new variables.

### 4. First deploy and smoke test

1. After the deploy finishes, open the service **URL** Render shows (e.g. `https://your-service.onrender.com`).
2. Log in with the default admin account (see below). If this is a **new** database, the app creates tables and the default admin on first startup.
3. Create a test instructor, confirm it still exists after you click **Restart** on the service or after a new deploy (data should remain in Postgres).

### 5. Ongoing updates

1. Push changes to GitHub (`git add`, `git commit`, `git push`).
2. Render redeploys from the connected branch (depending on your **auto-deploy** setting), or deploy manually from the service **Deploy** tab.

### Notes

- **Uploaded files** (`uploads/`, `master_files/`, etc.) are still on the web service’s ephemeral disk and can disappear after redeploys or idle spin-down on the free tier. The **database** (users, submission rows) persists with PostgreSQL.
- If the app fails to start, check **Logs** on the Web Service for import errors or database connection errors (wrong `DATABASE_URL`, firewall, or region mismatch).

## Default Login Credentials

**Admin:**
- Username: `cecs@cud.ac.ae`
- Password: `admin@2025`

**Instructor:**
- Default password for new instructors: `instructor@2025`
- Instructors must change password on first login

## Usage Guide

### For Administrators

1. **Login** with admin credentials
2. **Upload Master File:**
   - Go to "Upload Master File"
   - Upload an Excel/CSV file containing:
     - ID (Student ID)
     - Major
     - Status
     - Advisor
   - This file will be used to automatically merge with instructor submissions

3. **Create Instructor Accounts:**
   - Go to "Create Instructor Account"
   - Enter instructor email (username)
   - Optionally enter full name
   - Default password: `instructor@2025`
   - Instructor will be prompted to change password on first login

4. **View Submissions:**
   - Dashboard shows all instructor submissions
   - Each submission shows instructor name, course, filename, and submission time

5. **View and Analyze Files:**
   - Select a course file to view detailed data
   - Access risk analysis for students at risk
   - Search for specific students across all courses

### For Instructors

1. **Login** with instructor credentials (change password if prompted)

2. **Download Template:**
   - Click "Download Template"
   - Template contains columns: ID, Name, Course, Grade
   - Fill in your student grades

3. **Special Grades:**
   - `-1` = Incomplete
   - `-2` = FNA (Failure to Attend)

4. **Upload Grades:**
   - Upload your completed template
   - System automatically merges with master file to add:
     - Major
     - Status
     - Advisor
   - Admin will be notified of your submission

## File Structure

```
APP_Updates_Final_2026_Updated/
├── app.py                 # Main application file
├── app.db                 # SQLite database (local only; created when DATABASE_URL is not set)
├── requirements.txt       # Python dependencies
├── uploads/              # Instructor uploaded files
├── master_files/         # Master student information file
├── templates/            # HTML templates
│   ├── login.html
│   ├── admin_dashboard.html
│   ├── instructor_dashboard.html
│   ├── create_instructor.html
│   ├── upload_master.html
│   ├── change_password.html
│   ├── upload.html
│   └── risk_analysis.html
└── templates_files/      # Template files (if needed)
```

## Database Schema

### Users Table
- `id`: Primary key
- `username`: Email address (unique)
- `password_hash`: Hashed password
- `role`: 'admin' or 'instructor'
- `full_name`: Display name
- `created_at`: Account creation timestamp
- `password_changed`: Boolean flag for password change

### Submissions Table
- `id`: Primary key
- `instructor_id`: Foreign key to users table
- `filename`: Uploaded filename
- `course_name`: Parsed course name
- `submitted_at`: Submission timestamp

## Master File Format

The master file should be an Excel (.xlsx, .xls) or CSV file with the following columns:
- **ID**: Student ID (must match IDs in instructor files)
- **Major**: Student's major
- **Status**: Student status
- **Advisor**: Student's advisor name

## Instructor File Format

Instructor files should contain:
- **ID**: Student ID
- **Name**: Student name
- **Course**: Course name
- **Grade**: Numerical grade (or -1 for Incomplete, -2 for FNA)

## Security Notes

- Passwords are hashed using Werkzeug's password hashing
- Session-based authentication
- Role-based access control
- Secure file upload handling

## Troubleshooting

1. **Database errors**: Delete `app.db` and restart the application (will recreate with default admin)

2. **Master file not merging**: Ensure master file has correct column names (ID, Major, Status, Advisor)

3. **Template download fails**: Ensure `openpyxl` is installed: `pip install openpyxl`

4. **File upload errors**: Check file permissions on `uploads/` and `master_files/` directories

## Configuration

Edit `app.py` to change:
- Host and port (line 841)
- Secret key (line 18)
- Upload folder paths (lines 8-13)
