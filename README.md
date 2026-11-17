# Hire Hub

A Flask-powered job application portal connecting job seekers and employers.

## MVP features
- Browse and search job listings
- Candidate registration and login
- Employer registration and job posting
- Apply to jobs with a CV upload
- Candidate application tracking
- Employer applicant management

## Run locally

```bash
python -m venv venv
# Windows: venv\\Scripts\\activate
# macOS/Linux: source venv/bin/activate
pip install -r requirements.txt
python app.py
```

Open http://127.0.0.1:5000.

Set `SECRET_KEY` in your environment before deployment. Uploaded CVs are stored locally for development; use private object storage for production.
