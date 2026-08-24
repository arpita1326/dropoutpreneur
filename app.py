import os
import secrets
import sqlite3
from functools import wraps
from pathlib import Path

from flask import Flask, abort, flash, g, redirect, render_template, request, session, url_for
from flask_wtf.csrf import CSRFProtect
from werkzeug.security import check_password_hash, generate_password_hash

BASE_DIR = Path(__file__).resolve().parent
DATABASE = BASE_DIR / "dropoutpreneur.db"
app = Flask(__name__)
APP_ENV = os.environ.get("APP_ENV", "development").lower()
configured_secret = os.environ.get("SECRET_KEY")
if APP_ENV == "production" and not configured_secret:
    raise RuntimeError("SECRET_KEY must be set when APP_ENV=production")
app.config.update(
    SECRET_KEY=configured_secret or secrets.token_urlsafe(32),
    DATABASE=os.environ.get("DATABASE", str(DATABASE)),
    DEBUG=APP_ENV == "development" and os.environ.get("FLASK_DEBUG", "0").lower() in {"1", "true", "yes"},
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=os.environ.get("SESSION_COOKIE_SECURE", "0").lower() in {"1", "true", "yes"},
)
csrf = CSRFProtect(app)

PATHS = {
    "python": {"title": "Python Foundations", "eyebrow": "Build with code", "description": "Learn Python from your first variable to useful automation projects.", "color": "coral", "modules": [("Python fundamentals", ["Welcome to Python", "Variables and data types", "Input and operators", "Conditions and loops"]), ("Functions and collections", ["Functions", "Lists and tuples", "Dictionaries and sets", "Working with strings"]), ("Object-oriented Python", ["Objects and classes", "Constructors", "Inheritance", "Encapsulation"]), ("Projects", ["Build a calculator", "Create a to-do app", "Analyze a CSV", "Ship your Python project"])]},
    "web": {"title": "Web Development", "eyebrow": "Create for the web", "description": "Turn ideas into responsive websites and full-stack experiences.", "color": "blue", "modules": [("HTML and CSS", ["HTML foundations", "CSS foundations", "Layouts with Flexbox", "Responsive design"]), ("JavaScript", ["JavaScript essentials", "DOM interactions", "Forms and validation", "Fetch and APIs"]), ("Build and launch", ["Design a portfolio", "Build a landing page", "Backend basics with Flask", "Ship your web project"])]},
    "sql": {"title": "SQL and Databases", "eyebrow": "Make data useful", "description": "Query, shape, and model data with practical SQL skills.", "color": "lime", "modules": [("Database basics", ["Tables and relationships", "SELECT and INSERT", "Filtering and sorting", "Aggregations"]), ("Useful queries", ["Joins", "Subqueries", "Case expressions", "Window functions"]), ("Data design", ["Normalization", "Indexes", "Build a student database", "Ship a data project"])]},
    "ai": {"title": "AI and Machine Learning", "eyebrow": "Think with data", "description": "Understand the building blocks behind useful machine learning systems.", "color": "violet", "modules": [("AI essentials", ["What is AI?", "Python for ML", "NumPy and Pandas", "Explore a dataset"]), ("Machine learning", ["Prepare data", "Regression and classification", "Model evaluation", "Avoid overfitting"]), ("Deep learning project", ["Neural network basics", "Train a model", "Build a spam classifier", "Share your findings"])]},
    "analytics": {"title": "Data Analytics", "eyebrow": "Find the signal", "description": "Use spreadsheets, Python, and visual thinking to answer better questions.", "color": "amber", "modules": [("Data fluency", ["Data fundamentals", "Spreadsheets", "Statistics basics", "Ask a good question"]), ("Analyze and explain", ["Pandas", "Data visualization", "Dashboard concepts", "Tell a data story"]), ("Analytics project", ["Clean sales data", "Find patterns", "Build a dashboard", "Present your analysis"])]},
    "dsa": {"title": "Data Structures and Algorithms", "eyebrow": "Solve with confidence", "description": "Build problem-solving instincts with core structures and algorithms.", "color": "pink", "modules": [("Core structures", ["Complexity", "Arrays and strings", "Linked lists", "Stacks and queues"]), ("Algorithms", ["Searching", "Sorting", "Trees and graphs", "Greedy thinking"]), ("Problem solving", ["Dynamic programming", "Choose an approach", "Practice patterns", "Solve a challenge"])]},
}

def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(app.config["DATABASE"])
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db

@app.teardown_appcontext
def close_db(_error=None):
    db = g.pop("db", None)
    if db:
        db.close()

def init_db():
    get_db().executescript("""
        CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY, name TEXT NOT NULL, email TEXT UNIQUE NOT NULL, password_hash TEXT NOT NULL, career_goal TEXT DEFAULT '', created_at TEXT DEFAULT CURRENT_TIMESTAMP);
        CREATE TABLE IF NOT EXISTS progress (id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL, path_key TEXT NOT NULL, lesson_index INTEGER NOT NULL, completed_at TEXT DEFAULT CURRENT_TIMESTAMP, UNIQUE(user_id, path_key, lesson_index), FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE);
        CREATE TABLE IF NOT EXISTS career_results (id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL, career TEXT NOT NULL, path_key TEXT NOT NULL, score INTEGER NOT NULL, answers TEXT NOT NULL, created_at TEXT DEFAULT CURRENT_TIMESTAMP, FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE);
    """)
    get_db().commit()

with app.app_context():
    init_db()

def current_user():
    if "user" not in g:
        user_id = session.get("user_id")
        g.user = get_db().execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone() if user_id else None
    return g.user

@app.context_processor
def inject_user():
    return {"current_user": current_user()}

def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not current_user():
            flash("Log in to continue your journey.", "notice")
            return redirect(url_for("login", next=request.path))
        return view(*args, **kwargs)
    return wrapped

def lessons_for(path_key):
    result = []
    lesson_index = 0
    for module_number, (module, module_lessons) in enumerate(PATHS[path_key]["modules"], 1):
        for title in module_lessons:
            result.append((module_number, module, lesson_index, title))
            lesson_index += 1
    return result

def path_stats(path_key, user_id):
    total = len(lessons_for(path_key))
    completed = get_db().execute("SELECT COUNT(*) FROM progress WHERE user_id = ? AND path_key = ?", (user_id, path_key)).fetchone()[0]
    return total, completed, round(completed / total * 100) if total else 0

@app.route("/")
def home():
    return render_template("home.html", paths=PATHS)

@app.route("/about")
def about():
    return render_template("about.html")

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        name = request.form.get("name", "").strip(); email = request.form.get("email", "").strip().lower(); password = request.form.get("password", ""); confirm = request.form.get("confirm", "")
        if not name or not email or len(password) < 8 or password != confirm:
            flash("Use a name, a valid email, and matching passwords of at least 8 characters.", "error")
        elif get_db().execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone():
            flash("That email is already registered. Try logging in.", "error")
        else:
            cursor = get_db().execute("INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)", (name, email, generate_password_hash(password))); get_db().commit(); session.clear(); session["user_id"] = cursor.lastrowid
            flash("Welcome to DROPoutpreneur. Your journey starts here.", "success"); return redirect(url_for("dashboard"))
    return render_template("auth.html", mode="register")

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        user = get_db().execute("SELECT * FROM users WHERE email = ?", (request.form.get("email", "").strip().lower(),)).fetchone()
        if not user or not check_password_hash(user["password_hash"], request.form.get("password", "")):
            flash("Email or password is incorrect.", "error")
        else:
            session.clear(); session["user_id"] = user["id"]
            next_url = request.args.get("next", "")
            if next_url.startswith("/") and not next_url.startswith("//"):
                return redirect(next_url)
            return redirect(url_for("dashboard"))
    return render_template("auth.html", mode="login")

@app.route("/logout")
def logout():
    session.clear(); flash("You have been logged out.", "notice"); return redirect(url_for("home"))

@app.route("/dashboard")
@login_required
def dashboard():
    stats = {key: path_stats(key, current_user()["id"]) for key in PATHS}; completed = sum(item[1] for item in stats.values())
    next_lesson = next(((key, index, lesson) for key in PATHS for _, _, index, lesson in lessons_for(key) if not get_db().execute("SELECT 1 FROM progress WHERE user_id = ? AND path_key = ? AND lesson_index = ?", (current_user()["id"], key, index)).fetchone()), None)
    return render_template("dashboard.html", paths=PATHS, stats=stats, completed=completed, next_lesson=next_lesson)

@app.route("/learning")
def learning():
    user_id = current_user()["id"] if current_user() else None; stats = {key: path_stats(key, user_id) if user_id else (len(lessons_for(key)), 0, 0) for key in PATHS}
    return render_template("learning.html", paths=PATHS, stats=stats)

@app.route("/learning/<path_key>")
def path_overview(path_key):
    if path_key not in PATHS: abort(404)
    user_id = current_user()["id"] if current_user() else None; stats = path_stats(path_key, user_id) if user_id else (len(lessons_for(path_key)), 0, 0)
    return render_template("path.html", path_key=path_key, path=PATHS[path_key], stats=stats, lessons=lessons_for(path_key))

@app.route("/learning/<path_key>/lesson/<int:lesson_index>", methods=["GET", "POST"])
@login_required
def lesson(path_key, lesson_index):
    if path_key not in PATHS or lesson_index < 0 or lesson_index >= len(lessons_for(path_key)): abort(404)
    lessons = lessons_for(path_key); module_number, module, _, title = lessons[lesson_index]
    if request.method == "POST":
        get_db().execute("INSERT OR IGNORE INTO progress (user_id, path_key, lesson_index) VALUES (?, ?, ?)", (current_user()["id"], path_key, lesson_index)); get_db().commit(); flash("Lesson marked complete.", "success")
        if lesson_index < len(lessons) - 1: return redirect(url_for("lesson", path_key=path_key, lesson_index=lesson_index + 1))
    done = bool(get_db().execute("SELECT 1 FROM progress WHERE user_id = ? AND path_key = ? AND lesson_index = ?", (current_user()["id"], path_key, lesson_index)).fetchone()); stats = path_stats(path_key, current_user()["id"])
    return render_template("lesson.html", path_key=path_key, path=PATHS[path_key], module=module, module_number=module_number, title=title, index=lesson_index, lessons=lessons, done=done, stats=stats)

@app.route("/career", methods=["GET", "POST"])
@login_required
def career():
    if request.method == "POST":
        answers = {key: request.form.get(key, "") for key in ("enjoy", "work", "level", "build")}; choices = {"Software Developer": ("python", "coding"), "Web Developer": ("web", "design"), "Data Analyst": ("analytics", "data"), "AI / ML Engineer": ("ai", "ai"), "Backend Developer": ("python", "problem")}
        career_name, (path_key, focus) = max(choices.items(), key=lambda pair: sum(value in answers.values() for value in pair[1])); score = 64 + sum(value in answers.values() for value in (path_key, focus)) * 12
        get_db().execute("INSERT INTO career_results (user_id, career, path_key, score, answers) VALUES (?, ?, ?, ?, ?)", (current_user()["id"], career_name, path_key, score, str(answers))); get_db().commit(); return redirect(url_for("career_result"))
    return render_template("career.html")

@app.route("/career/result")
@login_required
def career_result():
    result = get_db().execute("SELECT * FROM career_results WHERE user_id = ? ORDER BY id DESC LIMIT 1", (current_user()["id"],)).fetchone()
    return render_template("career_result.html", result=result, path=PATHS[result["path_key"]] if result else None)

@app.route("/profile", methods=["GET", "POST"])
@login_required
def profile():
    if request.method == "POST":
        get_db().execute("UPDATE users SET name = ?, career_goal = ? WHERE id = ?", (request.form.get("name", "").strip(), request.form.get("career_goal", "").strip(), current_user()["id"])); get_db().commit(); flash("Profile updated.", "success"); return redirect(url_for("profile"))
    return render_template("profile.html", stats={key: path_stats(key, current_user()["id"]) for key in PATHS})

@app.route("/settings")
@login_required
def settings():
    return render_template("settings.html")

@app.errorhandler(404)
def not_found(_error): return render_template("error.html", code=404, message="That page took a different path."), 404

@app.errorhandler(500)
def server_error(_error): return render_template("error.html", code=500, message="Something went wrong on our side."), 500

if __name__ == "__main__":
    app.run(debug=app.config["DEBUG"])