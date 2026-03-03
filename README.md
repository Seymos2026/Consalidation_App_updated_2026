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
├── app.db                 # SQLite database (created automatically)
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
