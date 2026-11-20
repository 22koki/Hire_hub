# Hire Hub

A Flask-powered job application portal connecting job seekers and employers.

## Features

- Browse and search active job listings
- Candidate and employer registration and login
- Employer job posting and applicant management
- Apply to jobs with a CV upload
- Candidate application tracking and employer status updates
- CSRF protection for form submissions
- Server-side CV extension and file-signature validation

## Requirements

- Python 3.10 or newer
- pip

## Run locally (Windows PowerShell)

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
$env:SECRET_KEY = "replace-this-with-a-long-random-local-secret"
python app.py
```

If PowerShell blocks virtual-environment activation, run the commands below instead:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe app.py
```

## Run locally (macOS / Linux)

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
export SECRET_KEY="$(python -c 'import secrets; print(secrets.token_hex(32))')"
python app.py
```

Open http://127.0.0.1:5000.

## Configuration

- `SECRET_KEY`: set a long, random secret in every environment. The built-in fallback is only for local development.
- `FLASK_DEBUG`: set to `1` only for local debugging; it is off by default.
- `SESSION_COOKIE_SECURE`: set to `1` when serving the site over HTTPS.

The SQLite database is created under `instance/`. CV uploads are stored under `uploads/` for local development and are excluded from Git. For production, use private object storage, malware scanning, and a managed database.

## Security notes

All state-changing HTML forms must include a Flask-WTF CSRF token. Uploaded CVs are limited to 5 MB and checked against their file signatures. These controls improve the MVP baseline but do not replace a production security review.
