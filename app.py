import os
from datetime import datetime, timezone
from pathlib import Path
from functools import wraps
from io import BytesIO
from zipfile import BadZipFile, ZipFile

from flask import Flask, render_template, redirect, url_for, flash, request, abort, send_from_directory
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from flask_wtf.csrf import CSRFProtect
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from sqlalchemy.exc import IntegrityError

BASE_DIR = Path(__file__).resolve().parent
UPLOAD_DIR = BASE_DIR / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)
ALLOWED_EXTENSIONS = {"pdf", "doc", "docx"}
MAX_CV_SIZE = 5 * 1024 * 1024

app = Flask(__name__)
app.config.update(
    SECRET_KEY=os.environ.get("SECRET_KEY") or "local-development-key-change-before-deployment",
    SQLALCHEMY_DATABASE_URI="sqlite:///" + str(BASE_DIR / "instance" / "hirehub.db"),
    SQLALCHEMY_TRACK_MODIFICATIONS=False,
    UPLOAD_FOLDER=str(UPLOAD_DIR),
    MAX_CONTENT_LENGTH=MAX_CV_SIZE + (256 * 1024),
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=os.environ.get("SESSION_COOKIE_SECURE", "0") == "1",
    REMEMBER_COOKIE_HTTPONLY=True,
    REMEMBER_COOKIE_SECURE=os.environ.get("SESSION_COOKIE_SECURE", "0") == "1",
)
Path(BASE_DIR / "instance").mkdir(exist_ok=True)

db = SQLAlchemy(app)
csrf = CSRFProtect(app)
login_manager = LoginManager(app)
login_manager.login_view = "login"
login_manager.login_message_category = "info"
login_manager.session_protection = "strong"


class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(160), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), nullable=False, default="candidate")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    jobs = db.relationship("Job", backref="employer", lazy=True)
    applications = db.relationship("Application", backref="candidate", lazy=True)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)


class Job(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(160), nullable=False)
    company = db.Column(db.String(160), nullable=False)
    location = db.Column(db.String(120), nullable=False)
    job_type = db.Column(db.String(40), nullable=False, default="Full-time")
    workplace = db.Column(db.String(30), nullable=False, default="Hybrid")
    category = db.Column(db.String(80), nullable=False, default="General")
    salary = db.Column(db.String(80))
    description = db.Column(db.Text, nullable=False)
    requirements = db.Column(db.Text)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    employer_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    applications = db.relationship("Application", backref="job", lazy=True, cascade="all, delete-orphan")


class Application(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    cover_letter = db.Column(db.Text, nullable=False)
    cv_filename = db.Column(db.String(255), nullable=False)
    status = db.Column(db.String(30), default="Submitted", nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    candidate_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    job_id = db.Column(db.Integer, db.ForeignKey("job.id"), nullable=False)
    __table_args__ = (db.UniqueConstraint("candidate_id", "job_id", name="unique_candidate_job"),)


@login_manager.user_loader
def load_user(user_id):
    try:
        return db.session.get(User, int(user_id))
    except (TypeError, ValueError):
        return None


def role_required(role):
    def decorator(view):
        @wraps(view)
        @login_required
        def wrapped(*args, **kwargs):
            if current_user.role != role:
                abort(403)
            return view(*args, **kwargs)
        return wrapped
    return decorator


def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def valid_cv_file(upload):
    """Check the file signature rather than trusting its name or browser MIME type."""
    header = upload.stream.read(8)
    upload.stream.seek(0)
    extension = upload.filename.rsplit(".", 1)[1].lower()

    if extension == "pdf":
        return header.startswith(b"%PDF-")
    if extension == "doc":
        return header.startswith(bytes.fromhex("D0CF11E0A1B11AE1"))
    if extension == "docx":
        if not header.startswith(b"PK"):
            return False
        try:
            with ZipFile(upload.stream) as archive:
                return "word/document.xml" in archive.namelist()
        except (BadZipFile, OSError):
            return False
        finally:
            upload.stream.seek(0)
    return False


@app.context_processor
def inject_year():
    return {"current_year": datetime.now(timezone.utc).year}


@app.route("/")
def index():
    search = request.args.get("q", "").strip()[:160]
    location = request.args.get("location", "").strip()[:120]
    query = Job.query.filter_by(is_active=True)
    if search:
        term = f"%{search}%"
        query = query.filter(db.or_(Job.title.ilike(term), Job.company.ilike(term), Job.category.ilike(term)))
    if location:
        query = query.filter(Job.location.ilike(f"%{location}%"))
    jobs = query.order_by(Job.created_at.desc()).all()
    return render_template("index.html", jobs=jobs, search=search, location=location)


@app.route("/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard"))
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        role = request.form.get("role", "candidate")
        if not name or len(name) > 120 or not email or len(email) > 160 or len(password) < 8 or role not in {"candidate", "employer"}:
            flash("Complete all fields. Your password must be at least 8 characters.", "error")
        elif User.query.filter_by(email=email).first():
            flash("An account with that email already exists.", "error")
        else:
            user = User(name=name, email=email, role=role)
            user.set_password(password)
            db.session.add(user)
            try:
                db.session.commit()
            except IntegrityError:
                db.session.rollback()
                flash("An account with that email already exists.", "error")
                return render_template("register.html")
            login_user(user)
            flash("Welcome to Hire Hub. Your account is ready!", "success")
            return redirect(url_for("dashboard"))
    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard"))
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        user = User.query.filter_by(email=email).first()
        if user and user.check_password(password):
            login_user(user)
            flash("You are now signed in.", "success")
            return redirect(url_for("dashboard"))
        flash("Email or password is incorrect.", "error")
    return render_template("login.html")


@app.post("/logout")
@login_required
def logout():
    logout_user()
    flash("You have been signed out.", "success")
    return redirect(url_for("index"))


@app.route("/jobs/<int:job_id>")
def job_detail(job_id):
    job = Job.query.filter_by(id=job_id, is_active=True).first_or_404()
    existing = None
    if current_user.is_authenticated and current_user.role == "candidate":
        existing = Application.query.filter_by(candidate_id=current_user.id, job_id=job.id).first()
    return render_template("job_detail.html", job=job, existing=existing)


@app.route("/jobs/new", methods=["GET", "POST"])
@role_required("employer")
def post_job():
    if request.method == "POST":
        fields = {key: request.form.get(key, "").strip() for key in
                  ("title", "company", "location", "job_type", "workplace", "category", "salary", "description", "requirements")}
        limits = {"title": 160, "company": 160, "location": 120, "job_type": 40,
                  "workplace": 30, "category": 80, "salary": 80}
        too_long = any(len(fields[key]) > limit for key, limit in limits.items())
        if not fields["title"] or not fields["company"] or not fields["location"] or not fields["description"] or too_long:
            flash("Complete the required job details and check that fields are within their length limits.", "error")
        else:
            job = Job(**fields, employer_id=current_user.id)
            db.session.add(job)
            db.session.commit()
            flash("Your job listing is now live.", "success")
            return redirect(url_for("dashboard"))
    return render_template("post_job.html")


@app.post("/jobs/<int:job_id>/apply")
@role_required("candidate")
def apply(job_id):
    job = Job.query.filter_by(id=job_id, is_active=True).first_or_404()
    if Application.query.filter_by(candidate_id=current_user.id, job_id=job.id).first():
        flash("You have already applied for this role.", "info")
        return redirect(url_for("job_detail", job_id=job.id))

    cover_letter = request.form.get("cover_letter", "").strip()
    cv = request.files.get("cv")
    if not cover_letter or len(cover_letter) > 10000 or not cv or not cv.filename:
        flash("Add a cover letter and a PDF, DOC or DOCX CV (maximum 5 MB).", "error")
        return redirect(url_for("job_detail", job_id=job.id))
    if not allowed_file(cv.filename) or not valid_cv_file(cv):
        flash("The CV must be a valid PDF, DOC or DOCX file.", "error")
        return redirect(url_for("job_detail", job_id=job.id))

    safe_name = secure_filename(cv.filename)
    if not safe_name:
        flash("Please choose a valid CV filename.", "error")
        return redirect(url_for("job_detail", job_id=job.id))
    stored_name = f"{current_user.id}_{int(datetime.now(timezone.utc).timestamp())}_{safe_name}"
    destination = UPLOAD_DIR / stored_name
    cv.save(destination)

    application = Application(cover_letter=cover_letter, cv_filename=stored_name,
                              candidate_id=current_user.id, job_id=job.id)
    db.session.add(application)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        destination.unlink(missing_ok=True)
        flash("You have already applied for this role.", "info")
        return redirect(url_for("job_detail", job_id=job.id))
    except Exception:
        db.session.rollback()
        destination.unlink(missing_ok=True)
        raise

    flash("Application submitted successfully. You can track it from your dashboard.", "success")
    return redirect(url_for("dashboard"))


@app.route("/dashboard")
@login_required
def dashboard():
    if current_user.role == "employer":
        jobs = Job.query.filter_by(employer_id=current_user.id).order_by(Job.created_at.desc()).all()
        return render_template("dashboard_employer.html", jobs=jobs)
    applications = Application.query.filter_by(candidate_id=current_user.id).order_by(Application.created_at.desc()).all()
    return render_template("dashboard_candidate.html", applications=applications)


@app.get("/applications/<int:application_id>/cv")
@role_required("employer")
def download_cv(application_id):
    application = Application.query.get_or_404(application_id)
    if application.job.employer_id != current_user.id:
        abort(403)
    return send_from_directory(UPLOAD_DIR, application.cv_filename, as_attachment=True)


@app.post("/applications/<int:application_id>/status")
@role_required("employer")
def update_application_status(application_id):
    application = Application.query.get_or_404(application_id)
    if application.job.employer_id != current_user.id:
        abort(403)
    status = request.form.get("status")
    if status not in {"Submitted", "Reviewing", "Shortlisted", "Rejected", "Hired"}:
        abort(400)
    application.status = status
    db.session.commit()
    flash("Application status updated.", "success")
    return redirect(url_for("dashboard"))


@app.errorhandler(400)
def bad_request(_error):
    return render_template("error.html", code=400, message="Your request could not be processed. Please refresh and try again."), 400


@app.errorhandler(403)
def forbidden(_error):
    return render_template("error.html", code=403, message="You do not have permission to view this page."), 403


@app.errorhandler(404)
def not_found(_error):
    return render_template("error.html", code=404, message="We couldn't find that page."), 404


@app.errorhandler(413)
def file_too_large(_error):
    flash("The uploaded file is too large. CV files must be no larger than 5 MB.", "error")
    return redirect(request.referrer or url_for("index"))


with app.app_context():
    db.create_all()


if __name__ == "__main__":
    app.run(debug=os.environ.get("FLASK_DEBUG", "0") == "1")
