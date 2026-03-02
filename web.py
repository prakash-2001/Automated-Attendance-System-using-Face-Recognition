from __future__ import annotations

import base64
import binascii
import csv
import io
import json
import os
import re
import sqlite3
from dataclasses import dataclass
from datetime import date, datetime
from functools import wraps
from pathlib import Path
from typing import Any, Optional

try:
    import cv2
except Exception:
    cv2 = None

try:
    import numpy as np
except Exception:
    np = None
from flask import Flask, Response, flash, g, jsonify, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

try:
    import face_recognition
except Exception:
    face_recognition = None

try:
    from openpyxl import Workbook
except Exception:
    Workbook = None

APP_ROOT = Path(__file__).resolve().parent
INSTANCE_DIR = APP_ROOT / "instance"
DB_PATH = Path(os.getenv("APP_DB_PATH", str(INSTANCE_DIR / "attendance.db")))

DEFAULT_BRANCHES = ("CSE", "ECE", "EEE", "ME", "CIVIL", "IT", "AIML")
SEMESTERS = tuple(range(1, 9))
USN_RE = re.compile(r"^[0-9][A-Z]{2}[0-9]{2}[A-Z]{2}[0-9]{3}$")
SUBJECT_CODE_RE = re.compile(r"^[A-Z0-9]{4,12}$")
USERNAME_RE = re.compile(r"^[a-zA-Z0-9_.-]{3,32}$")
NAME_RE = re.compile(r"^[A-Za-z .'-]{2,80}$")
PASSWORD_RE = re.compile(r"^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[^A-Za-z0-9]).{8,64}$")
BRANCH_RE = re.compile(r"^[A-Z][A-Z0-9_]{1,15}$")

SEGMENT_SUPER_ADMIN = "super_admin"
SEGMENT_PRINCIPAL = "principal"
SEGMENT_DEPARTMENT_HEAD = "department_head"
SEGMENT_TEACHER = "teacher"
SEGMENT_STUDENT = "student"

SEGMENTS = (
    SEGMENT_SUPER_ADMIN,
    SEGMENT_PRINCIPAL,
    SEGMENT_DEPARTMENT_HEAD,
    SEGMENT_TEACHER,
    SEGMENT_STUDENT,
)

SEGMENT_LABELS: dict[str, str] = {
    SEGMENT_SUPER_ADMIN: "Super Admin",
    SEGMENT_PRINCIPAL: "Principal",
    SEGMENT_DEPARTMENT_HEAD: "Department Head",
    SEGMENT_TEACHER: "Teacher",
    SEGMENT_STUDENT: "Student",
}

BASE_ROLE_BY_SEGMENT: dict[str, str] = {
    SEGMENT_SUPER_ADMIN: "admin",
    SEGMENT_PRINCIPAL: "admin",
    SEGMENT_DEPARTMENT_HEAD: "admin",
    SEGMENT_TEACHER: "staff",
    SEGMENT_STUDENT: "staff",
}

PERMISSION_STUDENTS_READ = "students.read"
PERMISSION_STUDENTS_WRITE = "students.write"
PERMISSION_SUBJECTS_READ = "subjects.read"
PERMISSION_SUBJECTS_WRITE = "subjects.write"
PERMISSION_ATTENDANCE_READ = "attendance.read"
PERMISSION_ATTENDANCE_WRITE = "attendance.write"
PERMISSION_ATTENDANCE_EXECUTE = "attendance.execute"
PERMISSION_REPORTS_READ = "reports.read"
PERMISSION_REPORTS_EXECUTE = "reports.execute"
PERMISSION_USERS_READ = "users.read"
PERMISSION_USERS_WRITE = "users.write"
PERMISSION_USERS_GRANT = "users.grant"
PERMISSION_STRUCTURE_READ = "structure.read"
PERMISSION_STRUCTURE_WRITE = "structure.write"

PERMISSIONS = (
    PERMISSION_STUDENTS_READ,
    PERMISSION_STUDENTS_WRITE,
    PERMISSION_SUBJECTS_READ,
    PERMISSION_SUBJECTS_WRITE,
    PERMISSION_ATTENDANCE_READ,
    PERMISSION_ATTENDANCE_WRITE,
    PERMISSION_ATTENDANCE_EXECUTE,
    PERMISSION_REPORTS_READ,
    PERMISSION_REPORTS_EXECUTE,
    PERMISSION_USERS_READ,
    PERMISSION_USERS_WRITE,
    PERMISSION_USERS_GRANT,
    PERMISSION_STRUCTURE_READ,
    PERMISSION_STRUCTURE_WRITE,
)

PERMISSION_LABELS: dict[str, str] = {
    PERMISSION_STUDENTS_READ: "Students: Read",
    PERMISSION_STUDENTS_WRITE: "Students: Write",
    PERMISSION_SUBJECTS_READ: "Subjects: Read",
    PERMISSION_SUBJECTS_WRITE: "Subjects: Write",
    PERMISSION_ATTENDANCE_READ: "Attendance: Read",
    PERMISSION_ATTENDANCE_WRITE: "Attendance: Write",
    PERMISSION_ATTENDANCE_EXECUTE: "Attendance: Execute",
    PERMISSION_REPORTS_READ: "Reports: Read",
    PERMISSION_REPORTS_EXECUTE: "Reports: Execute",
    PERMISSION_USERS_READ: "Users: Read",
    PERMISSION_USERS_WRITE: "Users: Write",
    PERMISSION_USERS_GRANT: "Users: Grant Permissions",
    PERMISSION_STRUCTURE_READ: "Branch/Sem: Read",
    PERMISSION_STRUCTURE_WRITE: "Branch/Sem: Write",
}

ROLE_PERMISSIONS: dict[str, set[str]] = {
    SEGMENT_SUPER_ADMIN: set(PERMISSIONS),
    SEGMENT_PRINCIPAL: {
        PERMISSION_STUDENTS_READ,
        PERMISSION_STUDENTS_WRITE,
        PERMISSION_SUBJECTS_READ,
        PERMISSION_SUBJECTS_WRITE,
        PERMISSION_ATTENDANCE_READ,
        PERMISSION_REPORTS_READ,
        PERMISSION_REPORTS_EXECUTE,
        PERMISSION_USERS_READ,
        PERMISSION_USERS_WRITE,
        PERMISSION_STRUCTURE_READ,
        PERMISSION_STRUCTURE_WRITE,
    },
    SEGMENT_DEPARTMENT_HEAD: {
        PERMISSION_STUDENTS_READ,
        PERMISSION_STUDENTS_WRITE,
        PERMISSION_SUBJECTS_READ,
        PERMISSION_SUBJECTS_WRITE,
        PERMISSION_ATTENDANCE_READ,
        PERMISSION_ATTENDANCE_WRITE,
        PERMISSION_ATTENDANCE_EXECUTE,
        PERMISSION_REPORTS_READ,
        PERMISSION_REPORTS_EXECUTE,
        PERMISSION_USERS_READ,
        PERMISSION_USERS_WRITE,
        PERMISSION_STRUCTURE_READ,
    },
    SEGMENT_TEACHER: {
        PERMISSION_STUDENTS_READ,
        PERMISSION_SUBJECTS_READ,
        PERMISSION_ATTENDANCE_READ,
        PERMISSION_ATTENDANCE_WRITE,
        PERMISSION_ATTENDANCE_EXECUTE,
        PERMISSION_REPORTS_READ,
        PERMISSION_REPORTS_EXECUTE,
    },
    SEGMENT_STUDENT: {
        PERMISSION_SUBJECTS_READ,
        PERMISSION_ATTENDANCE_READ,
        PERMISSION_REPORTS_READ,
    },
}

ROLE_SCOPE_DESCRIPTIONS: dict[str, str] = {
    SEGMENT_SUPER_ADMIN: "Global control, permission grants, and full execution rights.",
    SEGMENT_PRINCIPAL: "Institute-wide governance without permission-grant authority.",
    SEGMENT_DEPARTMENT_HEAD: "Branch-scoped academic and user management.",
    SEGMENT_TEACHER: "Assigned-subject attendance operations and reports.",
    SEGMENT_STUDENT: "Personal attendance and assigned subject visibility.",
}

SEGMENTS_WITH_BRANCH = {SEGMENT_DEPARTMENT_HEAD, SEGMENT_TEACHER, SEGMENT_STUDENT}

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    full_name TEXT NOT NULL,
    role TEXT NOT NULL CHECK(role IN ('admin', 'staff')),
    branch TEXT,
    is_active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS students (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    usn TEXT NOT NULL UNIQUE,
    full_name TEXT NOT NULL,
    branch TEXT NOT NULL,
    semester INTEGER NOT NULL,
    is_active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS subjects (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    branch TEXT NOT NULL,
    semester INTEGER NOT NULL,
    staff_id INTEGER,
    start_time TEXT NOT NULL,
    end_time TEXT NOT NULL,
    is_active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (staff_id) REFERENCES users(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS face_profiles (
    student_id INTEGER PRIMARY KEY,
    embedding TEXT NOT NULL,
    backend TEXT NOT NULL,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (student_id) REFERENCES students(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS attendance_records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    attendance_date TEXT NOT NULL,
    subject_id INTEGER NOT NULL,
    student_id INTEGER NOT NULL,
    marked_by INTEGER NOT NULL,
    marked_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    method TEXT NOT NULL CHECK(method IN ('face', 'manual')),
    confidence REAL,
    FOREIGN KEY (subject_id) REFERENCES subjects(id) ON DELETE CASCADE,
    FOREIGN KEY (student_id) REFERENCES students(id) ON DELETE CASCADE,
    FOREIGN KEY (marked_by) REFERENCES users(id) ON DELETE RESTRICT,
    UNIQUE(attendance_date, subject_id, student_id)
);

CREATE INDEX IF NOT EXISTS idx_subject_staff ON subjects(staff_id);
CREATE INDEX IF NOT EXISTS idx_student_branch_sem ON students(branch, semester);
CREATE INDEX IF NOT EXISTS idx_attendance_date ON attendance_records(attendance_date);

CREATE TABLE IF NOT EXISTS user_segments (
    user_id INTEGER PRIMARY KEY,
    segment TEXT NOT NULL CHECK(segment IN ('super_admin', 'principal', 'department_head', 'teacher', 'student')),
    semester INTEGER,
    student_id INTEGER UNIQUE,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (student_id) REFERENCES students(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS user_permissions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    permission TEXT NOT NULL,
    granted_by INTEGER NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (granted_by) REFERENCES users(id) ON DELETE RESTRICT,
    UNIQUE(user_id, permission)
);

CREATE TABLE IF NOT EXISTS branch_semesters (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    branch TEXT NOT NULL,
    semester INTEGER NOT NULL,
    is_active INTEGER NOT NULL DEFAULT 1,
    created_by INTEGER,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (created_by) REFERENCES users(id) ON DELETE SET NULL,
    UNIQUE(branch, semester)
);

CREATE INDEX IF NOT EXISTS idx_user_segment_segment ON user_segments(segment);
CREATE INDEX IF NOT EXISTS idx_user_permissions_user ON user_permissions(user_id);
CREATE INDEX IF NOT EXISTS idx_branch_sem_active ON branch_semesters(branch, semester, is_active);
"""


@dataclass
class MatchResult:
    matched: bool
    score: float
    confidence: float


class FaceEngine:
    def __init__(self) -> None:
        self.backend = "disabled"
        self.distance_threshold = 0.58
        self.similarity_threshold = 0.86
        self.haar = None

        if cv2 is None:
            return

        self.backend = "opencv-fallback"
        self.haar = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")

        if face_recognition is not None:
            self.backend = "face_recognition"

    @staticmethod
    def decode_data_url(data_url: str) -> np.ndarray:
        if cv2 is None or np is None:
            raise ValueError("Face pipeline is disabled. Install opencv-python and numpy to enable it.")

        if not data_url:
            raise ValueError("Image payload is empty.")

        payload = data_url
        if "," in data_url:
            payload = data_url.split(",", 1)[1]

        try:
            image_bytes = base64.b64decode(payload, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise ValueError("Invalid image encoding.") from exc

        array = np.frombuffer(image_bytes, dtype=np.uint8)
        image = cv2.imdecode(array, cv2.IMREAD_COLOR)
        if image is None:
            raise ValueError("Could not decode image frame.")
        return image

    def extract_embedding(self, image: np.ndarray) -> tuple[Optional[np.ndarray], Optional[str]]:
        if np is None:
            return None, "NumPy is not available for face processing."
        if self.backend == "face_recognition":
            return self._extract_face_recognition_embedding(image)
        return self._extract_opencv_embedding(image)

    def _extract_face_recognition_embedding(self, image: np.ndarray) -> tuple[Optional[np.ndarray], Optional[str]]:
        if cv2 is None or np is None or face_recognition is None:
            return None, "Face recognition backend is not available."

        rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        locations = face_recognition.face_locations(rgb, model="hog")

        if not locations:
            return None, "No face detected. Keep one face clearly in the frame."
        if len(locations) > 1:
            return None, "Multiple faces detected. Keep only one face in the frame."

        encodings = face_recognition.face_encodings(rgb, known_face_locations=locations)
        if not encodings:
            return None, "Could not extract a stable face encoding."

        embedding = np.asarray(encodings[0], dtype=np.float32)
        norm = np.linalg.norm(embedding)
        if norm == 0:
            return None, "Invalid encoding extracted. Try better lighting."

        return embedding / norm, None

    def _extract_opencv_embedding(self, image: np.ndarray) -> tuple[Optional[np.ndarray], Optional[str]]:
        if cv2 is None or np is None or self.haar is None:
            return None, "OpenCV backend is not available."

        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        faces = self.haar.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5, minSize=(64, 64))

        if len(faces) == 0:
            return None, "No face detected. Keep your face centered and well lit."
        if len(faces) > 1:
            return None, "Multiple faces detected. Keep one face in frame."

        x, y, w, h = max(faces, key=lambda box: box[2] * box[3])
        face = gray[y : y + h, x : x + w]
        face = cv2.equalizeHist(face)
        face = cv2.resize(face, (64, 64), interpolation=cv2.INTER_AREA)

        embedding = face.astype(np.float32).reshape(-1) / 255.0
        norm = np.linalg.norm(embedding)
        if norm == 0:
            return None, "Invalid face sample captured."

        return embedding / norm, None

    def compare(self, probe: np.ndarray, candidate: np.ndarray) -> MatchResult:
        if np is None:
            return MatchResult(matched=False, score=0.0, confidence=0.0)
        if probe.size != candidate.size:
            return MatchResult(matched=False, score=0.0, confidence=0.0)

        if self.backend == "face_recognition":
            distance = float(np.linalg.norm(probe - candidate))
            score = 1.0 / (1.0 + distance)
            matched = distance <= self.distance_threshold
            confidence = max(0.0, min(1.0, 1.0 - (distance / self.distance_threshold)))
            return MatchResult(matched=matched, score=score, confidence=confidence)

        similarity = float(np.dot(probe, candidate))
        matched = similarity >= self.similarity_threshold
        confidence = max(0.0, min(1.0, (similarity - self.similarity_threshold) / (1.0 - self.similarity_threshold)))
        return MatchResult(matched=matched, score=similarity, confidence=confidence)


face_engine = FaceEngine()

app = Flask(__name__, template_folder="templates", static_folder="static")
app.config.update(
    SECRET_KEY=os.getenv("APP_SECRET_KEY", "change-me-in-production"),
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
)


def utc_now_str() -> str:
    return datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")


def today_str() -> str:
    return date.today().isoformat()


def normalize_name(value: str) -> str:
    return " ".join(value.strip().split())


def parse_semester(value: Any) -> Optional[int]:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed in SEMESTERS else None


def parse_time_hhmm(value: str) -> Optional[str]:
    try:
        return datetime.strptime(value, "%H:%M").strftime("%H:%M")
    except (TypeError, ValueError):
        return None


def get_db() -> sqlite3.Connection:
    if "db" not in g:
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(DB_PATH)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        g.db = connection
    return g.db


def close_db(_: Optional[BaseException] = None) -> None:
    db = g.pop("db", None)
    if db is not None:
        db.close()


app.teardown_appcontext(close_db)


def query_one(sql: str, params: tuple[Any, ...] = ()) -> Optional[sqlite3.Row]:
    return get_db().execute(sql, params).fetchone()


def query_all(sql: str, params: tuple[Any, ...] = ()) -> list[sqlite3.Row]:
    return get_db().execute(sql, params).fetchall()


def migrate_legacy_staff_rows() -> None:
    # Older versions had no segment table and only admin/staff roles.
    db = get_db()
    missing_segments = query_all(
        """
        SELECT u.id, u.role
        FROM users u
        LEFT JOIN user_segments us ON us.user_id = u.id
        WHERE us.user_id IS NULL
        """
    )
    for row in missing_segments:
        segment = SEGMENT_SUPER_ADMIN if row["role"] == "admin" else SEGMENT_TEACHER
        db.execute(
            """
            INSERT INTO user_segments (user_id, segment, semester, student_id)
            VALUES (?, ?, NULL, NULL)
            """,
            (row["id"], segment),
        )
    if missing_segments:
        db.commit()


def seed_default_scope_matrix() -> None:
    db = get_db()
    for branch in DEFAULT_BRANCHES:
        for semester in SEMESTERS:
            db.execute(
                """
                INSERT INTO branch_semesters (branch, semester, is_active)
                VALUES (?, ?, 1)
                ON CONFLICT(branch, semester) DO NOTHING
                """,
                (branch, semester),
            )
    db.commit()


def ensure_default_super_admin() -> None:
    username = os.getenv("DEFAULT_ADMIN_USERNAME", "admin").strip().lower()
    password = os.getenv("DEFAULT_ADMIN_PASSWORD", "Admin@123")
    full_name = os.getenv("DEFAULT_ADMIN_FULL_NAME", "System Admin")

    db = get_db()
    account = query_one("SELECT id FROM users WHERE username = ?", (username,))
    if account is None:
        cursor = db.execute(
            """
            INSERT INTO users (username, password_hash, full_name, role, branch, is_active)
            VALUES (?, ?, ?, 'admin', NULL, 1)
            """,
            (username, generate_password_hash(password), full_name),
        )
        account_id = cursor.lastrowid
        db.execute(
            """
            INSERT INTO user_segments (user_id, segment, semester, student_id)
            VALUES (?, ?, NULL, NULL)
            ON CONFLICT(user_id) DO UPDATE SET segment = excluded.segment, semester = NULL, student_id = NULL
            """,
            (account_id, SEGMENT_SUPER_ADMIN),
        )
        db.commit()
        return

    db.execute("UPDATE users SET role = 'admin' WHERE id = ?", (account["id"],))
    db.execute(
        """
        INSERT INTO user_segments (user_id, segment, semester, student_id)
        VALUES (?, ?, NULL, NULL)
        ON CONFLICT(user_id) DO UPDATE SET segment = excluded.segment, semester = NULL, student_id = NULL
        """,
        (account["id"], SEGMENT_SUPER_ADMIN),
    )
    db.commit()


def init_db() -> None:
    db = get_db()
    db.executescript(SCHEMA_SQL)
    db.commit()
    seed_default_scope_matrix()
    migrate_legacy_staff_rows()
    ensure_default_super_admin()

def get_available_branches(active_only: bool = True) -> tuple[str, ...]:
    try:
        rows = query_all(
            f"""
            SELECT DISTINCT branch
            FROM branch_semesters
            {"WHERE is_active = 1" if active_only else ""}
            ORDER BY branch ASC
            """
        )
        branches = tuple(row["branch"] for row in rows if row["branch"])
        if branches:
            return branches
    except sqlite3.Error:
        pass
    return DEFAULT_BRANCHES


def get_available_semesters(active_only: bool = True) -> tuple[int, ...]:
    try:
        rows = query_all(
            f"""
            SELECT DISTINCT semester
            FROM branch_semesters
            {"WHERE is_active = 1" if active_only else ""}
            ORDER BY semester ASC
            """
        )
        semesters = tuple(row["semester"] for row in rows if row["semester"] is not None)
        if semesters:
            return semesters
    except sqlite3.Error:
        pass
    return SEMESTERS


def is_scope_active(branch: str, semester: int) -> bool:
    row = query_one(
        """
        SELECT id
        FROM branch_semesters
        WHERE branch = ? AND semester = ? AND is_active = 1
        """,
        (branch, semester),
    )
    return row is not None


def role_display_name(segment: str) -> str:
    return SEGMENT_LABELS.get(segment, segment.replace("_", " ").title())


def get_effective_permissions(user_id: int, segment: str) -> set[str]:
    effective = set(ROLE_PERMISSIONS.get(segment, set()))
    extras = query_all("SELECT permission FROM user_permissions WHERE user_id = ?", (user_id,))
    for row in extras:
        if row["permission"] in PERMISSIONS:
            effective.add(row["permission"])
    return effective


def current_user() -> Optional[dict[str, Any]]:
    if "user_id" not in session:
        return None

    row = query_one(
        """
        SELECT u.id, u.username, u.full_name, u.branch, u.is_active, u.role,
               us.segment, us.semester, us.student_id,
               st.branch AS student_branch, st.semester AS student_semester
        FROM users u
        LEFT JOIN user_segments us ON us.user_id = u.id
        LEFT JOIN students st ON st.id = us.student_id
        WHERE u.id = ?
        """,
        (session["user_id"],),
    )
    if row is None or row["is_active"] != 1:
        session.clear()
        return None

    segment = row["segment"]
    if segment not in SEGMENTS:
        segment = SEGMENT_SUPER_ADMIN if row["role"] == "admin" else SEGMENT_TEACHER

    branch = row["student_branch"] if segment == SEGMENT_STUDENT else row["branch"]
    semester = row["student_semester"] if segment == SEGMENT_STUDENT else row["semester"]
    permissions = get_effective_permissions(row["id"], segment)

    return {
        "id": row["id"],
        "username": row["username"],
        "full_name": row["full_name"],
        "role": segment,
        "role_label": role_display_name(segment),
        "branch": branch,
        "semester": semester,
        "student_id": row["student_id"],
        "permissions": permissions,
    }


def has_permission(user: Optional[dict[str, Any]], permission: str) -> bool:
    return user is not None and permission in user.get("permissions", set())


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if current_user() is None:
            flash("Please login to continue.", "warning")
            return redirect(url_for("login"))
        return view(*args, **kwargs)

    return wrapped


def permission_required(permission: str):
    def decorator(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            user = current_user()
            if user is None:
                if request.path.startswith("/api/"):
                    return jsonify({"status": "error", "message": "Authentication required."}), 401
                flash("Please login to continue.", "warning")
                return redirect(url_for("login"))
            if not has_permission(user, permission):
                if request.path.startswith("/api/"):
                    return jsonify({"status": "error", "message": "Not authorized."}), 403
                flash("You are not authorized for this action.", "danger")
                return redirect(url_for("dashboard"))
            return view(*args, **kwargs)

        return wrapped

    return decorator


def roles_required(*roles: str):
    # Compatibility helper for older route decorators.
    def decorator(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            user = current_user()
            if user is None:
                flash("Please login to continue.", "warning")
                return redirect(url_for("login"))
            if user["role"] not in roles:
                flash("You are not authorized for this action.", "danger")
                return redirect(url_for("dashboard"))
            return view(*args, **kwargs)

        return wrapped

    return decorator


def can_access_branch(user: dict[str, Any], branch: Optional[str]) -> bool:
    if branch is None:
        return False
    if user["role"] in {SEGMENT_SUPER_ADMIN, SEGMENT_PRINCIPAL}:
        return True
    return user.get("branch") == branch


def get_access_scope_clause(user: dict[str, Any], subject_alias: str = "s", attendance_alias: str = "ar") -> tuple[str, list[Any]]:
    role = user["role"]
    if role in {SEGMENT_SUPER_ADMIN, SEGMENT_PRINCIPAL}:
        return "", []
    if role == SEGMENT_DEPARTMENT_HEAD:
        return f" AND {subject_alias}.branch = ?", [user["branch"]]
    if role == SEGMENT_TEACHER:
        return f" AND {subject_alias}.staff_id = ?", [user["id"]]
    if role == SEGMENT_STUDENT:
        return f" AND {attendance_alias}.student_id = ?", [user["student_id"]]
    return " AND 1 = 0", []


def get_accessible_subjects(user: dict[str, Any]) -> list[sqlite3.Row]:
    if not has_permission(user, PERMISSION_SUBJECTS_READ):
        return []

    role = user["role"]
    if role in {SEGMENT_SUPER_ADMIN, SEGMENT_PRINCIPAL}:
        return query_all(
            """
            SELECT s.*, u.full_name AS staff_name
            FROM subjects s
            LEFT JOIN users u ON u.id = s.staff_id
            WHERE s.is_active = 1
            ORDER BY s.code ASC
            """
        )

    if role == SEGMENT_DEPARTMENT_HEAD:
        return query_all(
            """
            SELECT s.*, u.full_name AS staff_name
            FROM subjects s
            LEFT JOIN users u ON u.id = s.staff_id
            WHERE s.is_active = 1 AND s.branch = ?
            ORDER BY s.code ASC
            """,
            (user["branch"],),
        )

    if role == SEGMENT_STUDENT:
        if user["branch"] is None or user["semester"] is None:
            return []
        return query_all(
            """
            SELECT s.*, u.full_name AS staff_name
            FROM subjects s
            LEFT JOIN users u ON u.id = s.staff_id
            WHERE s.is_active = 1 AND s.branch = ? AND s.semester = ?
            ORDER BY s.code ASC
            """,
            (user["branch"], user["semester"]),
        )

    return query_all(
        """
        SELECT s.*, u.full_name AS staff_name
        FROM subjects s
        LEFT JOIN users u ON u.id = s.staff_id
        WHERE s.is_active = 1 AND s.staff_id = ?
        ORDER BY s.code ASC
        """,
        (user["id"],),
    )


def get_subject_for_user(subject_id: int, user: dict[str, Any]) -> Optional[sqlite3.Row]:
    role = user["role"]
    if role in {SEGMENT_SUPER_ADMIN, SEGMENT_PRINCIPAL}:
        return query_one(
            """
            SELECT s.*, u.full_name AS staff_name
            FROM subjects s
            LEFT JOIN users u ON u.id = s.staff_id
            WHERE s.id = ? AND s.is_active = 1
            """,
            (subject_id,),
        )

    if role == SEGMENT_DEPARTMENT_HEAD:
        return query_one(
            """
            SELECT s.*, u.full_name AS staff_name
            FROM subjects s
            LEFT JOIN users u ON u.id = s.staff_id
            WHERE s.id = ? AND s.is_active = 1 AND s.branch = ?
            """,
            (subject_id, user["branch"]),
        )

    if role == SEGMENT_STUDENT:
        if user["branch"] is None or user["semester"] is None:
            return None
        return query_one(
            """
            SELECT s.*, u.full_name AS staff_name
            FROM subjects s
            LEFT JOIN users u ON u.id = s.staff_id
            WHERE s.id = ? AND s.is_active = 1 AND s.branch = ? AND s.semester = ?
            """,
            (subject_id, user["branch"], user["semester"]),
        )

    return query_one(
        """
        SELECT s.*, u.full_name AS staff_name
        FROM subjects s
        LEFT JOIN users u ON u.id = s.staff_id
        WHERE s.id = ? AND s.is_active = 1 AND s.staff_id = ?
        """,
        (subject_id, user["id"]),
    )


def parse_embedding(raw_value: str) -> Optional[np.ndarray]:
    if np is None:
        return None

    try:
        values = json.loads(raw_value)
    except (TypeError, json.JSONDecodeError):
        return None

    embedding = np.asarray(values, dtype=np.float32).reshape(-1)
    if embedding.size < 16:
        return None

    norm = np.linalg.norm(embedding)
    if norm == 0:
        return None

    return embedding / norm


def validate_student_input(usn: str, full_name: str, branch: str, semester: Any) -> list[str]:
    errors: list[str] = []

    if not USN_RE.match(usn):
        errors.append("USN must follow format: 1AB23CD456.")

    if not NAME_RE.match(full_name):
        errors.append("Student name can include letters, spaces, . and '.")

    if branch not in set(get_available_branches(active_only=False)):
        errors.append("Select a valid branch.")

    parsed_semester = parse_semester(semester)
    if parsed_semester is None:
        errors.append("Semester must be between 1 and 8.")
    elif not is_scope_active(branch, parsed_semester):
        errors.append("Selected branch/semester is currently inactive.")

    return errors


def validate_staff_input(username: str, full_name: str, branch: str, password: str) -> list[str]:
    errors: list[str] = []

    if not USERNAME_RE.match(username):
        errors.append("Username must be 3-32 chars and may include letters, digits, . _ -")

    if not NAME_RE.match(full_name):
        errors.append("Staff name can include letters, spaces, . and '.")

    if branch not in set(get_available_branches(active_only=False)):
        errors.append("Select a valid branch.")

    if not PASSWORD_RE.match(password):
        errors.append("Password must be 8+ chars with uppercase, lowercase, digit and special character.")

    return errors


def validate_subject_input(
    code: str,
    name: str,
    branch: str,
    semester: Any,
    start_time: str,
    end_time: str,
) -> list[str]:
    errors: list[str] = []

    if not SUBJECT_CODE_RE.match(code):
        errors.append("Subject code must be 4-12 uppercase letters/numbers.")

    if len(name.strip()) < 2 or len(name.strip()) > 80:
        errors.append("Subject name must be between 2 and 80 characters.")

    if branch not in set(get_available_branches(active_only=False)):
        errors.append("Select a valid branch.")

    parsed_semester = parse_semester(semester)
    if parsed_semester is None:
        errors.append("Semester must be between 1 and 8.")
    elif not is_scope_active(branch, parsed_semester):
        errors.append("Selected branch/semester is currently inactive.")

    start = parse_time_hhmm(start_time)
    end = parse_time_hhmm(end_time)
    if start is None or end is None:
        errors.append("Start and end time must be valid HH:MM values.")
    elif start >= end:
        errors.append("End time must be later than start time.")

    return errors


def can_assign_segment(actor: dict[str, Any], segment: str, branch: Optional[str]) -> bool:
    if actor["role"] == SEGMENT_SUPER_ADMIN:
        return True
    if actor["role"] == SEGMENT_PRINCIPAL:
        return segment in {SEGMENT_DEPARTMENT_HEAD, SEGMENT_TEACHER, SEGMENT_STUDENT}
    if actor["role"] == SEGMENT_DEPARTMENT_HEAD:
        return segment in {SEGMENT_TEACHER, SEGMENT_STUDENT} and branch == actor["branch"]
    return False


def can_manage_user(actor: dict[str, Any], target: dict[str, Any]) -> bool:
    if actor["role"] == SEGMENT_SUPER_ADMIN:
        return True
    if actor["role"] == SEGMENT_PRINCIPAL:
        return target["role"] in {SEGMENT_DEPARTMENT_HEAD, SEGMENT_TEACHER, SEGMENT_STUDENT}
    if actor["role"] == SEGMENT_DEPARTMENT_HEAD:
        return target["role"] in {SEGMENT_TEACHER, SEGMENT_STUDENT} and target["branch"] == actor["branch"]
    return False


def count_active_super_admins() -> int:
    row = query_one(
        """
        SELECT COUNT(*) AS total
        FROM users u
        JOIN user_segments us ON us.user_id = u.id
        WHERE us.segment = ? AND u.is_active = 1
        """,
        (SEGMENT_SUPER_ADMIN,),
    )
    return int(row["total"]) if row else 0


def get_visible_users(viewer: dict[str, Any]) -> list[dict[str, Any]]:
    rows = query_all(
        """
        SELECT u.id, u.username, u.full_name, u.branch, u.is_active, u.created_at,
               us.segment, us.semester, us.student_id,
               (SELECT COUNT(*) FROM user_permissions up WHERE up.user_id = u.id) AS extra_permission_count
        FROM users u
        LEFT JOIN user_segments us ON us.user_id = u.id
        ORDER BY u.created_at DESC
        """
    )
    users: list[dict[str, Any]] = []
    for row in rows:
        segment = row["segment"] if row["segment"] in SEGMENTS else SEGMENT_TEACHER
        item = {
            "id": row["id"],
            "username": row["username"],
            "full_name": row["full_name"],
            "branch": row["branch"],
            "is_active": row["is_active"],
            "created_at": row["created_at"],
            "role": segment,
            "role_label": role_display_name(segment),
            "semester": row["semester"],
            "student_id": row["student_id"],
            "extra_permission_count": row["extra_permission_count"],
        }
        if viewer["role"] == SEGMENT_DEPARTMENT_HEAD and item["branch"] != viewer["branch"] and item["id"] != viewer["id"]:
            continue
        item["can_manage"] = can_manage_user(viewer, item)
        users.append(item)
    return users


def mark_attendance(
    subject_id: int,
    student_id: int,
    method: str,
    confidence: Optional[float],
    user: dict[str, Any],
) -> tuple[bool, str, int]:
    if not has_permission(user, PERMISSION_ATTENDANCE_WRITE):
        return False, "You are not allowed to mark attendance.", 403

    subject = get_subject_for_user(subject_id, user)
    if subject is None:
        return False, "Subject not found or inaccessible.", 404

    student = query_one(
        """
        SELECT id, usn, full_name, branch, semester
        FROM students
        WHERE id = ? AND is_active = 1
        """,
        (student_id,),
    )
    if student is None:
        return False, "Student does not exist.", 404

    if student["branch"] != subject["branch"] or student["semester"] != subject["semester"]:
        return False, "Student is not eligible for this subject.", 400

    db = get_db()
    try:
        db.execute(
            """
            INSERT INTO attendance_records
            (attendance_date, subject_id, student_id, marked_by, marked_at, method, confidence)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                today_str(),
                subject_id,
                student_id,
                user["id"],
                utc_now_str(),
                method,
                confidence,
            ),
        )
        db.commit()
    except sqlite3.IntegrityError:
        return False, "Attendance already marked for today.", 409

    return True, "Attendance marked successfully.", 200


def sanitize_export_cell(value: Any) -> str:
    if value is None:
        return ""

    text = str(value)
    if text and text[0] in ("=", "+", "-", "@"):
        return "'" + text
    return text


def resolve_report_filters(user: dict[str, Any]) -> tuple[list[sqlite3.Row], str, Optional[int], bool, bool]:
    subjects = get_accessible_subjects(user)
    allowed_subject_ids = {row["id"] for row in subjects}

    selected_date = request.args.get("date", today_str())
    invalid_date = False
    try:
        datetime.strptime(selected_date, "%Y-%m-%d")
    except ValueError:
        selected_date = today_str()
        invalid_date = True

    selected_subject_id = request.args.get("subject_id", type=int)
    invalid_subject = False
    if selected_subject_id and selected_subject_id not in allowed_subject_ids:
        selected_subject_id = None
        invalid_subject = True

    return subjects, selected_date, selected_subject_id, invalid_date, invalid_subject


def fetch_attendance_report_data(
    user: dict[str, Any],
    selected_date: str,
    selected_subject_id: Optional[int],
) -> tuple[list[sqlite3.Row], list[sqlite3.Row]]:
    sql = """
        SELECT ar.attendance_date, ar.marked_at, ar.method, ar.confidence,
               sub.code AS subject_code, sub.name AS subject_name,
               st.usn, st.full_name, st.branch, st.semester
        FROM attendance_records ar
        JOIN subjects sub ON sub.id = ar.subject_id
        JOIN students st ON st.id = ar.student_id
        WHERE ar.attendance_date = ?
    """
    params: list[Any] = [selected_date]
    role = user["role"]
    if role == SEGMENT_TEACHER:
        sql += " AND sub.staff_id = ?"
        params.append(user["id"])
    elif role == SEGMENT_DEPARTMENT_HEAD:
        sql += " AND sub.branch = ?"
        params.append(user["branch"])
    elif role == SEGMENT_STUDENT:
        sql += " AND ar.student_id = ?"
        params.append(user["student_id"])

    if selected_subject_id is not None:
        sql += " AND sub.id = ?"
        params.append(selected_subject_id)

    sql += " ORDER BY sub.code ASC, st.usn ASC"
    records = query_all(sql, tuple(params))

    summary_sql = """
        SELECT sub.code AS subject_code, COUNT(*) AS total
        FROM attendance_records ar
        JOIN subjects sub ON sub.id = ar.subject_id
        WHERE ar.attendance_date = ?
    """
    summary_params: list[Any] = [selected_date]
    if role == SEGMENT_TEACHER:
        summary_sql += " AND sub.staff_id = ?"
        summary_params.append(user["id"])
    elif role == SEGMENT_DEPARTMENT_HEAD:
        summary_sql += " AND sub.branch = ?"
        summary_params.append(user["branch"])
    elif role == SEGMENT_STUDENT:
        summary_sql += " AND ar.student_id = ?"
        summary_params.append(user["student_id"])

    if selected_subject_id is not None:
        summary_sql += " AND sub.id = ?"
        summary_params.append(selected_subject_id)

    summary_sql += " GROUP BY sub.code ORDER BY sub.code ASC"
    summary = query_all(summary_sql, tuple(summary_params))

    return records, summary


def dashboard_data_for_user(user: dict[str, Any]) -> tuple[list[dict[str, Any]], list[sqlite3.Row]]:
    role = user["role"]

    if role in {SEGMENT_SUPER_ADMIN, SEGMENT_PRINCIPAL}:
        row = query_one(
            """
            SELECT
                (SELECT COUNT(*) FROM students WHERE is_active = 1) AS students,
                (SELECT COUNT(*) FROM users u JOIN user_segments us ON us.user_id = u.id
                 WHERE us.segment = 'teacher' AND u.is_active = 1) AS teachers,
                (SELECT COUNT(*) FROM users u JOIN user_segments us ON us.user_id = u.id
                 WHERE us.segment = 'department_head' AND u.is_active = 1) AS heads,
                (SELECT COUNT(*) FROM subjects WHERE is_active = 1) AS subjects,
                (SELECT COUNT(*) FROM attendance_records WHERE attendance_date = ?) AS today_marks
            """,
            (today_str(),),
        )
        metrics = [
            {"label": "Active Students", "value": row["students"]},
            {"label": "Active Teachers", "value": row["teachers"]},
            {"label": "Department Heads", "value": row["heads"]},
            {"label": "Active Subjects", "value": row["subjects"]},
            {"label": "Today's Marks", "value": row["today_marks"]},
        ]
        recent = query_all(
            """
            SELECT ar.attendance_date, ar.marked_at, ar.method, ar.confidence,
                   sub.code AS subject_code, st.usn, st.full_name
            FROM attendance_records ar
            JOIN subjects sub ON sub.id = ar.subject_id
            JOIN students st ON st.id = ar.student_id
            ORDER BY ar.marked_at DESC
            LIMIT 12
            """
        )
        return metrics, recent

    if role == SEGMENT_DEPARTMENT_HEAD:
        row = query_one(
            """
            SELECT
                (SELECT COUNT(*) FROM students WHERE is_active = 1 AND branch = ?) AS students,
                (SELECT COUNT(*) FROM users u JOIN user_segments us ON us.user_id = u.id
                 WHERE us.segment = 'teacher' AND u.is_active = 1 AND u.branch = ?) AS teachers,
                (SELECT COUNT(*) FROM subjects WHERE is_active = 1 AND branch = ?) AS subjects,
                (SELECT COUNT(*) FROM attendance_records ar
                 JOIN subjects s ON s.id = ar.subject_id
                 WHERE s.branch = ? AND ar.attendance_date = ?) AS today_marks
            """,
            (user["branch"], user["branch"], user["branch"], user["branch"], today_str()),
        )
        metrics = [
            {"label": f"{user['branch']} Students", "value": row["students"]},
            {"label": f"{user['branch']} Teachers", "value": row["teachers"]},
            {"label": f"{user['branch']} Subjects", "value": row["subjects"]},
            {"label": "Today's Marks", "value": row["today_marks"]},
        ]
        recent = query_all(
            """
            SELECT ar.attendance_date, ar.marked_at, ar.method, ar.confidence,
                   sub.code AS subject_code, st.usn, st.full_name
            FROM attendance_records ar
            JOIN subjects sub ON sub.id = ar.subject_id
            JOIN students st ON st.id = ar.student_id
            WHERE sub.branch = ?
            ORDER BY ar.marked_at DESC
            LIMIT 12
            """,
            (user["branch"],),
        )
        return metrics, recent

    if role == SEGMENT_TEACHER:
        row = query_one(
            """
            SELECT
                (SELECT COUNT(*) FROM subjects WHERE staff_id = ? AND is_active = 1) AS subjects,
                (SELECT COUNT(*) FROM attendance_records ar
                 JOIN subjects s ON s.id = ar.subject_id
                 WHERE s.staff_id = ? AND ar.attendance_date = ?) AS today_marks,
                (SELECT COUNT(*) FROM attendance_records ar
                 JOIN subjects s ON s.id = ar.subject_id
                 WHERE s.staff_id = ?) AS total_marks
            """,
            (user["id"], user["id"], today_str(), user["id"]),
        )
        metrics = [
            {"label": "Assigned Subjects", "value": row["subjects"]},
            {"label": "Today's Marks", "value": row["today_marks"]},
            {"label": "Total Marks", "value": row["total_marks"]},
        ]
        recent = query_all(
            """
            SELECT ar.attendance_date, ar.marked_at, ar.method, ar.confidence,
                   sub.code AS subject_code, st.usn, st.full_name
            FROM attendance_records ar
            JOIN subjects sub ON sub.id = ar.subject_id
            JOIN students st ON st.id = ar.student_id
            WHERE sub.staff_id = ?
            ORDER BY ar.marked_at DESC
            LIMIT 12
            """,
            (user["id"],),
        )
        return metrics, recent

    row = query_one(
        """
        SELECT
            (SELECT COUNT(*) FROM subjects WHERE is_active = 1 AND branch = ? AND semester = ?) AS subjects,
            (SELECT COUNT(*) FROM attendance_records WHERE student_id = ?) AS total_marks,
            (SELECT COUNT(*) FROM attendance_records WHERE student_id = ? AND attendance_date = ?) AS today_marks
        """,
        (user["branch"], user["semester"], user["student_id"], user["student_id"], today_str()),
    )
    metrics = [
        {"label": "Current Semester Subjects", "value": row["subjects"] if row else 0},
        {"label": "Attendance Records", "value": row["total_marks"] if row else 0},
        {"label": "Marked Today", "value": row["today_marks"] if row else 0},
    ]
    recent = query_all(
        """
        SELECT ar.attendance_date, ar.marked_at, ar.method, ar.confidence,
               sub.code AS subject_code, st.usn, st.full_name
        FROM attendance_records ar
        JOIN subjects sub ON sub.id = ar.subject_id
        JOIN students st ON st.id = ar.student_id
        WHERE ar.student_id = ?
        ORDER BY ar.marked_at DESC
        LIMIT 12
        """,
        (user["student_id"],),
    )
    return metrics, recent


def build_quick_actions(user: dict[str, Any]) -> list[dict[str, str]]:
    actions: list[dict[str, str]] = []

    def add_action(label: str, endpoint: str, permission: str, style: str, description: str) -> None:
        if has_permission(user, permission):
            actions.append(
                {
                    "label": label,
                    "url": url_for(endpoint),
                    "style": style,
                    "description": description,
                }
            )

    add_action("Access Control", "staff_page", PERMISSION_USERS_READ, "primary", "Manage accounts, segments, and privilege grants.")
    add_action("Students", "students_page", PERMISSION_STUDENTS_READ, "outline", "Review and maintain student records.")
    add_action("Subjects", "subjects_page", PERMISSION_SUBJECTS_READ, "ghost", "Plan and assign teaching subjects.")
    add_action("Branch/Semester", "structure_page", PERMISSION_STRUCTURE_READ, "outline", "Control branch-semester activation matrix.")
    add_action("Live Attendance", "attendance_live", PERMISSION_ATTENDANCE_EXECUTE, "primary", "Run real-time attendance operations.")
    add_action("Attendance Reports", "attendance_report", PERMISSION_REPORTS_READ, "ghost", "Audit attendance and export analytics.")

    return actions


def build_role_workspace(user: dict[str, Any]) -> dict[str, Any]:
    role = user["role"]
    workspace: dict[str, Any] = {
        "title": f"{user['role_label']} Workspace",
        "subtitle": "Role-specific control center with scoped data and actions.",
        "alerts": [],
    }

    if role == SEGMENT_SUPER_ADMIN:
        scope_counts = query_one(
            """
            SELECT
                SUM(CASE WHEN is_active = 1 THEN 1 ELSE 0 END) AS active_scopes,
                SUM(CASE WHEN is_active = 0 THEN 1 ELSE 0 END) AS inactive_scopes
            FROM branch_semesters
            """
        )
        oversight = query_one(
            """
            SELECT
                (SELECT COUNT(*) FROM subjects WHERE is_active = 1 AND staff_id IS NULL) AS unassigned_subjects,
                (SELECT COUNT(*) FROM users WHERE is_active = 0) AS disabled_accounts,
                (SELECT COUNT(*) FROM students WHERE is_active = 1 AND id NOT IN (SELECT student_id FROM face_profiles)) AS students_without_face
            """
        )
        segment_distribution = query_all(
            """
            SELECT us.segment, COUNT(*) AS total
            FROM users u
            JOIN user_segments us ON us.user_id = u.id
            WHERE u.is_active = 1
            GROUP BY us.segment
            ORDER BY us.segment ASC
            """
        )
        workspace.update(
            {
                "title": "Super Admin Command Center",
                "subtitle": "Global governance, privilege control, and operational risk view.",
                "governance": {
                    "active_scopes": scope_counts["active_scopes"] if scope_counts and scope_counts["active_scopes"] is not None else 0,
                    "inactive_scopes": scope_counts["inactive_scopes"] if scope_counts and scope_counts["inactive_scopes"] is not None else 0,
                    "unassigned_subjects": oversight["unassigned_subjects"] if oversight else 0,
                    "disabled_accounts": oversight["disabled_accounts"] if oversight else 0,
                    "students_without_face": oversight["students_without_face"] if oversight else 0,
                },
                "segment_distribution": segment_distribution,
            }
        )
        if oversight and oversight["unassigned_subjects"] > 0:
            workspace["alerts"].append("Some active subjects are unassigned. Allocate faculty to avoid execution gaps.")
        if oversight and oversight["students_without_face"] > 0:
            workspace["alerts"].append("Face profile coverage is incomplete. Enrollment follow-up is required.")
        return workspace

    if role == SEGMENT_PRINCIPAL:
        branch_health = query_all(
            """
            SELECT bs.branch,
                   SUM(CASE WHEN bs.is_active = 1 THEN 1 ELSE 0 END) AS active_scopes,
                   (SELECT COUNT(*) FROM students st WHERE st.branch = bs.branch AND st.is_active = 1) AS students,
                   (SELECT COUNT(*) FROM subjects sub WHERE sub.branch = bs.branch AND sub.is_active = 1) AS subjects,
                   (SELECT COUNT(*)
                    FROM attendance_records ar
                    JOIN subjects s ON s.id = ar.subject_id
                    WHERE s.branch = bs.branch AND ar.attendance_date = ?) AS today_marks
            FROM branch_semesters bs
            GROUP BY bs.branch
            ORDER BY bs.branch ASC
            """,
            (today_str(),),
        )
        low_activity = [row for row in branch_health if row["students"] > 0 and row["today_marks"] == 0]
        workspace.update(
            {
                "title": "Principal Strategy Deck",
                "subtitle": "Institute-wide monitoring for branch health and attendance throughput.",
                "branch_health": branch_health,
            }
        )
        for row in low_activity:
            workspace["alerts"].append(f"{row['branch']} has active students but no marks today.")
        return workspace

    if role == SEGMENT_DEPARTMENT_HEAD:
        semester_status = query_all(
            """
            SELECT bs.semester, bs.is_active,
                   (SELECT COUNT(*) FROM students st
                    WHERE st.branch = ? AND st.semester = bs.semester AND st.is_active = 1) AS students,
                   (SELECT COUNT(*) FROM subjects sub
                    WHERE sub.branch = ? AND sub.semester = bs.semester AND sub.is_active = 1) AS subjects,
                   (SELECT COUNT(*)
                    FROM attendance_records ar
                    JOIN subjects s ON s.id = ar.subject_id
                    WHERE s.branch = ? AND s.semester = bs.semester AND ar.attendance_date = ?) AS today_marks
            FROM branch_semesters bs
            WHERE bs.branch = ?
            ORDER BY bs.semester ASC
            """,
            (user["branch"], user["branch"], user["branch"], today_str(), user["branch"]),
        )
        teacher_load = query_all(
            """
            SELECT u.full_name,
                   (SELECT COUNT(*) FROM subjects s WHERE s.staff_id = u.id AND s.is_active = 1) AS subjects,
                   (SELECT COUNT(*)
                    FROM attendance_records ar
                    JOIN subjects s ON s.id = ar.subject_id
                    WHERE s.staff_id = u.id AND ar.attendance_date = ?) AS today_marks
            FROM users u
            JOIN user_segments us ON us.user_id = u.id
            WHERE us.segment = 'teacher' AND u.is_active = 1 AND u.branch = ?
            ORDER BY u.full_name ASC
            """,
            (today_str(), user["branch"]),
        )
        workspace.update(
            {
                "title": f"{user['branch']} Department Hub",
                "subtitle": "Branch-scoped execution board for semester readiness and team load.",
                "semester_status": semester_status,
                "teacher_load": teacher_load,
            }
        )
        inactive_semesters = [row for row in semester_status if row["is_active"] == 0 and (row["students"] > 0 or row["subjects"] > 0)]
        if inactive_semesters:
            workspace["alerts"].append("Inactive semester scope has linked data. Review activation policy.")
        return workspace

    if role == SEGMENT_TEACHER:
        teaching_queue = query_all(
            """
            SELECT s.id, s.code, s.name, s.branch, s.semester, s.start_time, s.end_time,
                   (SELECT COUNT(*) FROM students st WHERE st.branch = s.branch AND st.semester = s.semester AND st.is_active = 1) AS eligible_students,
                   (SELECT COUNT(*) FROM attendance_records ar WHERE ar.subject_id = s.id AND ar.attendance_date = ?) AS today_marks
            FROM subjects s
            WHERE s.staff_id = ? AND s.is_active = 1
            ORDER BY s.start_time ASC, s.code ASC
            """,
            (today_str(), user["id"]),
        )
        workspace.update(
            {
                "title": "Teacher Operations Console",
                "subtitle": "Assigned subject workflow, attendance execution, and same-day output tracking.",
                "teaching_queue": teaching_queue,
            }
        )
        if not teaching_queue:
            workspace["alerts"].append("No active subjects assigned. Contact department head for assignment.")
        return workspace

    # Student experience
    progress = []
    trend = []
    if user["student_id"] is not None and user["branch"] is not None and user["semester"] is not None:
        progress = query_all(
            """
            SELECT sub.code, sub.name, COUNT(ar.id) AS marks
            FROM subjects sub
            LEFT JOIN attendance_records ar ON ar.subject_id = sub.id AND ar.student_id = ?
            WHERE sub.is_active = 1 AND sub.branch = ? AND sub.semester = ?
            GROUP BY sub.id
            ORDER BY sub.code ASC
            """,
            (user["student_id"], user["branch"], user["semester"]),
        )
        trend = query_all(
            """
            SELECT attendance_date, COUNT(*) AS total
            FROM attendance_records
            WHERE student_id = ?
            GROUP BY attendance_date
            ORDER BY attendance_date DESC
            LIMIT 10
            """,
            (user["student_id"],),
        )
    workspace.update(
        {
            "title": "Student Progress Desk",
            "subtitle": "Personal subject visibility and attendance history in one place.",
            "progress": progress,
            "trend": trend,
        }
    )
    if user["student_id"] is None:
        workspace["alerts"].append("Your account is not linked to a student profile. Contact administration.")
    return workspace


def dashboard_template_for_role(role: str) -> str:
    return {
        SEGMENT_SUPER_ADMIN: "dashboard_super_admin.html",
        SEGMENT_PRINCIPAL: "dashboard_principal.html",
        SEGMENT_DEPARTMENT_HEAD: "dashboard_department_head.html",
        SEGMENT_TEACHER: "dashboard_teacher.html",
        SEGMENT_STUDENT: "dashboard_student.html",
    }.get(role, "dashboard_teacher.html")


def can(permission: str) -> bool:
    return has_permission(current_user(), permission)


@app.context_processor
def inject_globals() -> dict[str, Any]:
    role_permissions_matrix = [
        {
            "role": segment,
            "label": role_display_name(segment),
            "scope": ROLE_SCOPE_DESCRIPTIONS.get(segment, ""),
            "permissions": sorted(ROLE_PERMISSIONS.get(segment, set())),
        }
        for segment in SEGMENTS
    ]
    return {
        "current_user": current_user(),
        "branches": get_available_branches(active_only=True),
        "semesters": get_available_semesters(active_only=True),
        "today": today_str(),
        "face_backend": face_engine.backend,
        "segments": SEGMENTS,
        "segment_labels": SEGMENT_LABELS,
        "permission_labels": PERMISSION_LABELS,
        "permission_keys": PERMISSIONS,
        "role_permissions_matrix": role_permissions_matrix,
        "can": can,
    }


@app.route("/")
def landing() -> str:
    if current_user():
        return redirect(url_for("dashboard"))
    return render_template("landing.html")


@app.route("/login", methods=["GET", "POST"])
def login() -> str:
    if current_user():
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        username = request.form.get("username", "").strip().lower()
        password = request.form.get("password", "")
        expected_role = request.form.get("expected_role", "").strip()
        if not username or not password:
            flash("Enter both username and password.", "danger")
            return render_template("login.html")
        if expected_role and expected_role not in SEGMENTS:
            flash("Select a valid role segment.", "danger")
            return render_template("login.html")

        user = query_one(
            """
            SELECT u.id, u.username, u.full_name, u.password_hash, u.is_active,
                   u.role AS legacy_role, us.segment
            FROM users u
            LEFT JOIN user_segments us ON us.user_id = u.id
            WHERE u.username = ?
            """,
            (username,),
        )
        if user is None or user["is_active"] != 1 or not check_password_hash(user["password_hash"], password):
            flash("Invalid credentials.", "danger")
            return render_template("login.html")

        actual_role = user["segment"]
        if actual_role not in SEGMENTS:
            actual_role = SEGMENT_SUPER_ADMIN if user["legacy_role"] == "admin" else SEGMENT_TEACHER

        if expected_role and expected_role != actual_role:
            flash(f"This account is mapped to {role_display_name(actual_role)}.", "warning")
            return render_template("login.html")

        session.clear()
        session["user_id"] = user["id"]
        flash(f"Welcome, {user['full_name']}.", "success")
        return redirect(url_for("dashboard"))

    return render_template("login.html")


@app.route("/logout", methods=["GET", "POST"])
def logout() -> Any:
    session.clear()
    flash("You have been logged out.", "info")
    return redirect(url_for("landing"))


@app.route("/dashboard")
@login_required
def dashboard() -> str:
    user = current_user()
    assert user is not None
    subjects = get_accessible_subjects(user)
    metrics, recent = dashboard_data_for_user(user)
    workspace = build_role_workspace(user)
    action_cards = build_quick_actions(user)
    return render_template(
        dashboard_template_for_role(user["role"]),
        metrics=metrics,
        subjects=subjects,
        recent=recent,
        workspace=workspace,
        action_cards=action_cards,
    )


@app.route("/students")
@permission_required(PERMISSION_STUDENTS_READ)
def students_page() -> str:
    user = current_user()
    assert user is not None

    sql = """
        SELECT st.id, st.usn, st.full_name, st.branch, st.semester, st.created_at,
               CASE WHEN fp.student_id IS NULL THEN 0 ELSE 1 END AS has_profile,
               CASE WHEN us.student_id IS NULL THEN 0 ELSE 1 END AS has_account
        FROM students st
        LEFT JOIN face_profiles fp ON fp.student_id = st.id
        LEFT JOIN user_segments us ON us.student_id = st.id
        WHERE st.is_active = 1
    """
    params: list[Any] = []
    if user["role"] == SEGMENT_TEACHER:
        sql += """
            AND EXISTS (
                SELECT 1
                FROM subjects s
                WHERE s.staff_id = ? AND s.is_active = 1 AND s.branch = st.branch AND s.semester = st.semester
            )
        """
        params.append(user["id"])
    elif user["role"] == SEGMENT_DEPARTMENT_HEAD:
        sql += " AND st.branch = ?"
        params.append(user["branch"])
    elif user["role"] == SEGMENT_STUDENT:
        if user["student_id"] is None:
            flash("Student account is not linked to a profile.", "warning")
            return render_template("students.html", students=[])
        sql += " AND st.id = ?"
        params.append(user["student_id"])
    sql += " ORDER BY st.created_at DESC"

    students = query_all(sql, tuple(params))
    return render_template("students.html", students=students)


@app.route("/students/create", methods=["POST"])
@permission_required(PERMISSION_STUDENTS_WRITE)
def create_student() -> Any:
    user = current_user()
    assert user is not None

    usn = request.form.get("usn", "").strip().upper()
    full_name = normalize_name(request.form.get("full_name", ""))
    branch = request.form.get("branch", "").strip().upper()
    semester_raw = request.form.get("semester", "")
    create_account = request.form.get("create_account") == "on"
    account_password = request.form.get("account_password", "")

    errors = validate_student_input(usn, full_name, branch, semester_raw)
    semester = parse_semester(semester_raw)
    if not can_access_branch(user, branch):
        errors.append("You cannot create student records for this branch.")
    if create_account and not PASSWORD_RE.match(account_password):
        errors.append("Student account password must be strong (8+ with uppercase, lowercase, digit, special).")

    if errors:
        for error in errors:
            flash(error, "danger")
        return redirect(url_for("students_page"))

    assert semester is not None
    db = get_db()
    try:
        db.execute("BEGIN")
        cursor = db.execute(
            """
            INSERT INTO students (usn, full_name, branch, semester, is_active)
            VALUES (?, ?, ?, ?, 1)
            """,
            (usn, full_name, branch, semester),
        )
        student_id = cursor.lastrowid

        if create_account:
            username = usn.lower()
            user_cursor = db.execute(
                """
                INSERT INTO users (username, password_hash, full_name, role, branch, is_active)
                VALUES (?, ?, ?, ?, ?, 1)
                """,
                (username, generate_password_hash(account_password), full_name, BASE_ROLE_BY_SEGMENT[SEGMENT_STUDENT], branch),
            )
            db.execute(
                """
                INSERT INTO user_segments (user_id, segment, semester, student_id)
                VALUES (?, ?, ?, ?)
                """,
                (user_cursor.lastrowid, SEGMENT_STUDENT, semester, student_id),
            )

        db.commit()
        flash(f"Student {usn} created successfully.", "success")
    except sqlite3.IntegrityError:
        db.rollback()
        flash("USN or linked account username already exists.", "danger")

    return redirect(url_for("students_page"))


@app.route("/students/<int:student_id>/delete", methods=["POST"])
@permission_required(PERMISSION_STUDENTS_WRITE)
def delete_student(student_id: int) -> Any:
    user = current_user()
    assert user is not None

    student = query_one("SELECT id, usn, branch, is_active FROM students WHERE id = ?", (student_id,))
    if student is None:
        flash("Student not found.", "warning")
        return redirect(url_for("students_page"))
    if not can_access_branch(user, student["branch"]):
        flash("You cannot modify this student's branch.", "danger")
        return redirect(url_for("students_page"))
    if student["is_active"] != 1:
        flash("Student already inactive.", "info")
        return redirect(url_for("students_page"))

    db = get_db()
    db.execute("UPDATE students SET is_active = 0 WHERE id = ?", (student_id,))
    db.execute(
        """
        UPDATE users
        SET is_active = 0
        WHERE id IN (SELECT user_id FROM user_segments WHERE student_id = ?)
        """,
        (student_id,),
    )
    db.commit()
    flash(f"Student {student['usn']} deactivated.", "info")
    return redirect(url_for("students_page"))


@app.route("/api/students/<int:student_id>/face-profile", methods=["POST"])
@permission_required(PERMISSION_STUDENTS_WRITE)
def save_face_profile(student_id: int) -> Any:
    user = current_user()
    assert user is not None

    student = query_one("SELECT id, usn, branch FROM students WHERE id = ? AND is_active = 1", (student_id,))
    if student is None:
        return jsonify({"status": "error", "message": "Student not found."}), 404
    if not can_access_branch(user, student["branch"]):
        return jsonify({"status": "error", "message": "You cannot modify this student profile."}), 403

    payload = request.get_json(silent=True) or {}
    image_data = payload.get("image_data", "")

    try:
        image = face_engine.decode_data_url(image_data)
    except ValueError as exc:
        return jsonify({"status": "error", "message": str(exc)}), 400

    embedding, error_message = face_engine.extract_embedding(image)
    if error_message:
        return jsonify({"status": "error", "message": error_message}), 422

    serialized = json.dumps(embedding.tolist())
    now = utc_now_str()
    db = get_db()
    db.execute(
        """
        INSERT INTO face_profiles (student_id, embedding, backend, updated_at)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(student_id)
        DO UPDATE SET embedding = excluded.embedding,
                      backend = excluded.backend,
                      updated_at = excluded.updated_at
        """,
        (student_id, serialized, face_engine.backend, now),
    )
    db.commit()

    return jsonify(
        {
            "status": "ok",
            "message": f"Face profile updated for {student['usn']}.",
            "backend": face_engine.backend,
        }
    )


@app.route("/staff")
@permission_required(PERMISSION_USERS_READ)
def staff_page() -> str:
    user = current_user()
    assert user is not None
    staff_members = get_visible_users(user)
    return render_template("staff.html", staff_members=staff_members)


@app.route("/staff/create", methods=["POST"])
@permission_required(PERMISSION_USERS_WRITE)
def create_staff() -> Any:
    actor = current_user()
    assert actor is not None

    segment = request.form.get("segment", SEGMENT_TEACHER).strip()
    username = request.form.get("username", "").strip().lower()
    full_name = normalize_name(request.form.get("full_name", ""))
    branch = request.form.get("branch", "").strip().upper()
    password = request.form.get("password", "")
    student_usn = request.form.get("student_usn", "").strip().upper()

    errors: list[str] = []
    if segment not in SEGMENTS:
        errors.append("Invalid role segment.")

    linked_student = None
    semester: Optional[int] = None

    if segment == SEGMENT_STUDENT:
        if not USN_RE.match(student_usn):
            errors.append("Provide a valid student USN for student accounts.")
        else:
            linked_student = query_one(
                """
                SELECT id, usn, full_name, branch, semester
                FROM students
                WHERE usn = ? AND is_active = 1
                """,
                (student_usn,),
            )
            if linked_student is None:
                errors.append("Student profile not found for the given USN.")
            else:
                existing_link = query_one("SELECT user_id FROM user_segments WHERE student_id = ?", (linked_student["id"],))
                if existing_link is not None:
                    errors.append("A user account already exists for this student.")
                branch = linked_student["branch"]
                semester = linked_student["semester"]
                if not full_name:
                    full_name = linked_student["full_name"]
                if not username:
                    username = linked_student["usn"].lower()
    else:
        if segment in SEGMENTS_WITH_BRANCH:
            if branch not in set(get_available_branches(active_only=False)):
                errors.append("Select a valid branch.")
        else:
            branch = ""

    if not username or not USERNAME_RE.match(username):
        errors.append("Username must be 3-32 chars and may include letters, digits, . _ -")
    if not NAME_RE.match(full_name):
        errors.append("Full name can include letters, spaces, . and '.")
    if not PASSWORD_RE.match(password):
        errors.append("Password must be 8+ chars with uppercase, lowercase, digit and special character.")
    if segment in SEGMENTS and not can_assign_segment(actor, segment, branch if branch else None):
        errors.append("You are not allowed to create this role for the selected scope.")

    if errors:
        for error in errors:
            flash(error, "danger")
        return redirect(url_for("staff_page"))

    base_role = BASE_ROLE_BY_SEGMENT[segment]
    db = get_db()
    try:
        db.execute("BEGIN")
        cursor = db.execute(
            """
            INSERT INTO users (username, password_hash, full_name, role, branch, is_active)
            VALUES (?, ?, ?, ?, ?, 1)
            """,
            (username, generate_password_hash(password), full_name, base_role, branch if branch else None),
        )
        db.execute(
            """
            INSERT INTO user_segments (user_id, segment, semester, student_id)
            VALUES (?, ?, ?, ?)
            """,
            (cursor.lastrowid, segment, semester, linked_student["id"] if linked_student else None),
        )
        db.commit()
        flash(f"Account {username} created as {role_display_name(segment)}.", "success")
    except sqlite3.IntegrityError:
        db.rollback()
        flash("Username already exists.", "danger")

    return redirect(url_for("staff_page"))


@app.route("/staff/<int:staff_id>/toggle-active", methods=["POST"])
@permission_required(PERMISSION_USERS_WRITE)
def toggle_staff_active(staff_id: int) -> Any:
    actor = current_user()
    assert actor is not None

    target_row = query_one(
        """
        SELECT u.id, u.username, u.branch, u.is_active, us.segment
        FROM users u
        LEFT JOIN user_segments us ON us.user_id = u.id
        WHERE u.id = ?
        """,
        (staff_id,),
    )
    if target_row is None:
        flash("Account not found.", "warning")
        return redirect(url_for("staff_page"))

    target = {
        "id": target_row["id"],
        "username": target_row["username"],
        "branch": target_row["branch"],
        "is_active": target_row["is_active"],
        "role": target_row["segment"] if target_row["segment"] in SEGMENTS else SEGMENT_TEACHER,
    }

    if staff_id == actor["id"] and target["is_active"] == 1:
        flash("You cannot deactivate your own account.", "danger")
        return redirect(url_for("staff_page"))
    if not can_manage_user(actor, target):
        flash("You cannot modify this account.", "danger")
        return redirect(url_for("staff_page"))

    new_state = 0 if target["is_active"] == 1 else 1
    if target["role"] == SEGMENT_SUPER_ADMIN and new_state == 0 and count_active_super_admins() <= 1:
        flash("At least one active super admin is required.", "danger")
        return redirect(url_for("staff_page"))

    db = get_db()
    db.execute("UPDATE users SET is_active = ? WHERE id = ?", (new_state, staff_id))
    db.commit()

    flash("Account status updated.", "info")
    return redirect(url_for("staff_page"))


@app.route("/staff/<int:staff_id>/grant", methods=["POST"])
@permission_required(PERMISSION_USERS_GRANT)
def grant_permission(staff_id: int) -> Any:
    actor = current_user()
    assert actor is not None

    permission = request.form.get("permission", "").strip()
    if permission not in PERMISSIONS:
        flash("Invalid permission key.", "danger")
        return redirect(url_for("staff_page"))

    target = query_one("SELECT id FROM users WHERE id = ?", (staff_id,))
    if target is None:
        flash("Target account not found.", "warning")
        return redirect(url_for("staff_page"))

    db = get_db()
    db.execute(
        """
        INSERT INTO user_permissions (user_id, permission, granted_by)
        VALUES (?, ?, ?)
        ON CONFLICT(user_id, permission) DO NOTHING
        """,
        (staff_id, permission, actor["id"]),
    )
    db.commit()
    flash(f"Permission '{permission}' granted.", "success")
    return redirect(url_for("staff_page"))


@app.route("/staff/<int:staff_id>/revoke", methods=["POST"])
@permission_required(PERMISSION_USERS_GRANT)
def revoke_permission(staff_id: int) -> Any:
    permission = request.form.get("permission", "").strip()
    if permission not in PERMISSIONS:
        flash("Invalid permission key.", "danger")
        return redirect(url_for("staff_page"))

    db = get_db()
    result = db.execute("DELETE FROM user_permissions WHERE user_id = ? AND permission = ?", (staff_id, permission))
    db.commit()
    if result.rowcount == 0:
        flash("Permission grant was not present.", "info")
    else:
        flash(f"Permission '{permission}' revoked.", "info")
    return redirect(url_for("staff_page"))


@app.route("/subjects")
@permission_required(PERMISSION_SUBJECTS_READ)
def subjects_page() -> str:
    user = current_user()
    assert user is not None

    subjects = get_accessible_subjects(user)
    staff_sql = """
        SELECT u.id, u.full_name, u.branch, us.segment
        FROM users u
        JOIN user_segments us ON us.user_id = u.id
        WHERE u.is_active = 1 AND us.segment IN ('teacher', 'department_head')
    """
    params: list[Any] = []
    if user["role"] == SEGMENT_DEPARTMENT_HEAD:
        staff_sql += " AND u.branch = ?"
        params.append(user["branch"])
    staff_sql += " ORDER BY u.full_name ASC"
    staff_members = query_all(staff_sql, tuple(params))
    return render_template("subjects.html", subjects=subjects, staff_members=staff_members)


@app.route("/subjects/create", methods=["POST"])
@permission_required(PERMISSION_SUBJECTS_WRITE)
def create_subject() -> Any:
    actor = current_user()
    assert actor is not None

    code = request.form.get("code", "").strip().upper()
    name = normalize_name(request.form.get("name", ""))
    branch = request.form.get("branch", "").strip().upper()
    semester_raw = request.form.get("semester", "")
    start_time_raw = request.form.get("start_time", "")
    end_time_raw = request.form.get("end_time", "")
    staff_id_raw = request.form.get("staff_id", "")

    errors = validate_subject_input(code, name, branch, semester_raw, start_time_raw, end_time_raw)
    if not can_access_branch(actor, branch):
        errors.append("You cannot create subjects for this branch.")

    staff_id: Optional[int] = None
    if staff_id_raw:
        try:
            staff_id = int(staff_id_raw)
        except ValueError:
            errors.append("Invalid staff selection.")

    semester = parse_semester(semester_raw)
    start_time = parse_time_hhmm(start_time_raw)
    end_time = parse_time_hhmm(end_time_raw)

    if staff_id is not None:
        staff_member = query_one(
            """
            SELECT u.id, u.branch, u.is_active, us.segment
            FROM users u
            JOIN user_segments us ON us.user_id = u.id
            WHERE u.id = ?
            """,
            (staff_id,),
        )
        if staff_member is None or staff_member["is_active"] != 1:
            errors.append("Selected user account is not active.")
        elif staff_member["segment"] not in {SEGMENT_TEACHER, SEGMENT_DEPARTMENT_HEAD}:
            errors.append("Subject can only be assigned to teacher/department head accounts.")
        elif staff_member["branch"] != branch:
            errors.append("Assigned faculty branch must match subject branch.")

    if errors:
        for error in errors:
            flash(error, "danger")
        return redirect(url_for("subjects_page"))

    db = get_db()
    try:
        db.execute(
            """
            INSERT INTO subjects (code, name, branch, semester, staff_id, start_time, end_time, is_active)
            VALUES (?, ?, ?, ?, ?, ?, ?, 1)
            """,
            (code, name, branch, semester, staff_id, start_time, end_time),
        )
        db.commit()
        flash(f"Subject {code} created.", "success")
    except sqlite3.IntegrityError:
        flash("Subject code already exists.", "danger")

    return redirect(url_for("subjects_page"))


@app.route("/subjects/<int:subject_id>/delete", methods=["POST"])
@permission_required(PERMISSION_SUBJECTS_WRITE)
def delete_subject(subject_id: int) -> Any:
    user = current_user()
    assert user is not None
    subject = get_subject_for_user(subject_id, user)
    if subject is None:
        flash("Subject not found or inaccessible.", "warning")
        return redirect(url_for("subjects_page"))

    db = get_db()
    result = db.execute("UPDATE subjects SET is_active = 0 WHERE id = ? AND is_active = 1", (subject_id,))
    db.commit()

    if result.rowcount == 0:
        flash("Subject already inactive.", "info")
    else:
        flash("Subject deactivated.", "info")

    return redirect(url_for("subjects_page"))


@app.route("/structure")
@permission_required(PERMISSION_STRUCTURE_READ)
def structure_page() -> str:
    scopes = query_all(
        """
        SELECT bs.id, bs.branch, bs.semester, bs.is_active,
               (SELECT COUNT(*) FROM students st WHERE st.branch = bs.branch AND st.semester = bs.semester AND st.is_active = 1) AS students,
               (SELECT COUNT(*) FROM subjects sub WHERE sub.branch = bs.branch AND sub.semester = bs.semester AND sub.is_active = 1) AS subjects
        FROM branch_semesters bs
        ORDER BY bs.branch ASC, bs.semester ASC
        """
    )
    return render_template("structure.html", scopes=scopes)


@app.route("/structure/create", methods=["POST"])
@permission_required(PERMISSION_STRUCTURE_WRITE)
def create_structure_scope() -> Any:
    actor = current_user()
    assert actor is not None

    branch = request.form.get("branch", "").strip().upper()
    semester_raw = request.form.get("semester", "")
    semester = parse_semester(semester_raw)
    if not BRANCH_RE.match(branch):
        flash("Branch must be 2-16 uppercase letters/digits/underscore.", "danger")
        return redirect(url_for("structure_page"))
    if semester is None:
        flash("Semester must be between 1 and 8.", "danger")
        return redirect(url_for("structure_page"))
    if actor["role"] == SEGMENT_DEPARTMENT_HEAD and actor["branch"] != branch:
        flash("Department heads can manage only their own branch scopes.", "danger")
        return redirect(url_for("structure_page"))

    db = get_db()
    db.execute(
        """
        INSERT INTO branch_semesters (branch, semester, is_active, created_by)
        VALUES (?, ?, 1, ?)
        ON CONFLICT(branch, semester) DO UPDATE SET is_active = 1
        """,
        (branch, semester, actor["id"]),
    )
    db.commit()
    flash("Branch/semester scope saved and activated.", "success")
    return redirect(url_for("structure_page"))


@app.route("/structure/<int:scope_id>/toggle-active", methods=["POST"])
@permission_required(PERMISSION_STRUCTURE_WRITE)
def toggle_structure_scope(scope_id: int) -> Any:
    actor = current_user()
    assert actor is not None
    scope = query_one("SELECT id, branch, semester, is_active FROM branch_semesters WHERE id = ?", (scope_id,))
    if scope is None:
        flash("Scope not found.", "warning")
        return redirect(url_for("structure_page"))
    if actor["role"] == SEGMENT_DEPARTMENT_HEAD and actor["branch"] != scope["branch"]:
        flash("Department heads can manage only their own branch scopes.", "danger")
        return redirect(url_for("structure_page"))

    new_state = 0 if scope["is_active"] == 1 else 1
    if new_state == 0:
        linked = query_one(
            """
            SELECT
                (SELECT COUNT(*) FROM students WHERE branch = ? AND semester = ? AND is_active = 1) AS students,
                (SELECT COUNT(*) FROM subjects WHERE branch = ? AND semester = ? AND is_active = 1) AS subjects
            """,
            (scope["branch"], scope["semester"], scope["branch"], scope["semester"]),
        )
        if linked and (linked["students"] > 0 or linked["subjects"] > 0):
            flash("Cannot deactivate scope with active students or subjects.", "danger")
            return redirect(url_for("structure_page"))

        active_count = query_one("SELECT COUNT(*) AS total FROM branch_semesters WHERE is_active = 1")
        if active_count and active_count["total"] <= 1:
            flash("At least one active branch/semester scope is required.", "danger")
            return redirect(url_for("structure_page"))

    db = get_db()
    db.execute("UPDATE branch_semesters SET is_active = ? WHERE id = ?", (new_state, scope_id))
    db.commit()
    flash("Scope status updated.", "info")
    return redirect(url_for("structure_page"))


@app.route("/attendance/live")
@permission_required(PERMISSION_ATTENDANCE_EXECUTE)
def attendance_live() -> str:
    user = current_user()
    assert user is not None

    subjects = get_accessible_subjects(user)
    selected_subject_id = request.args.get("subject_id", type=int)

    selected_subject = None
    if subjects:
        if selected_subject_id is None:
            selected_subject = subjects[0]
        else:
            selected_subject = next((subject for subject in subjects if subject["id"] == selected_subject_id), None)
            if selected_subject is None:
                selected_subject = subjects[0]
    else:
        flash("No subjects assigned yet.", "warning")

    eligible_count = 0
    marked_today = 0
    if selected_subject is not None:
        eligible_count_row = query_one(
            """
            SELECT COUNT(*) AS total
            FROM students
            WHERE is_active = 1 AND branch = ? AND semester = ?
            """,
            (selected_subject["branch"], selected_subject["semester"]),
        )
        marked_today_row = query_one(
            """
            SELECT COUNT(*) AS total
            FROM attendance_records
            WHERE attendance_date = ? AND subject_id = ?
            """,
            (today_str(), selected_subject["id"]),
        )
        eligible_count = eligible_count_row["total"]
        marked_today = marked_today_row["total"]

    return render_template(
        "attendance_live.html",
        subjects=subjects,
        selected_subject=selected_subject,
        eligible_count=eligible_count,
        marked_today=marked_today,
    )


@app.route("/attendance/report")
@permission_required(PERMISSION_REPORTS_READ)
def attendance_report() -> str:
    user = current_user()
    assert user is not None

    subjects, selected_date, selected_subject_id, invalid_date, invalid_subject = resolve_report_filters(user)
    if invalid_date:
        flash("Invalid date. Showing today instead.", "warning")
    if invalid_subject:
        flash("Selected subject is not accessible.", "warning")

    records, summary = fetch_attendance_report_data(user, selected_date, selected_subject_id)

    return render_template(
        "attendance_report.html",
        records=records,
        summary=summary,
        subjects=subjects,
        selected_date=selected_date,
        selected_subject_id=selected_subject_id,
    )


@app.route("/attendance/report.csv")
@permission_required(PERMISSION_REPORTS_EXECUTE)
def attendance_report_csv() -> Response:
    user = current_user()
    assert user is not None

    _, selected_date, selected_subject_id, _, _ = resolve_report_filters(user)
    records, summary = fetch_attendance_report_data(user, selected_date, selected_subject_id)

    output = io.StringIO()
    writer = csv.writer(output)

    writer.writerow(["Date", "Marked At", "Subject Code", "Subject Name", "USN", "Student Name", "Branch", "Semester", "Method", "Confidence"])
    for row in records:
        writer.writerow(
            [
                sanitize_export_cell(row["attendance_date"]),
                sanitize_export_cell(row["marked_at"]),
                sanitize_export_cell(row["subject_code"]),
                sanitize_export_cell(row["subject_name"]),
                sanitize_export_cell(row["usn"]),
                sanitize_export_cell(row["full_name"]),
                sanitize_export_cell(row["branch"]),
                sanitize_export_cell(row["semester"]),
                sanitize_export_cell(row["method"]),
                sanitize_export_cell(row["confidence"]),
            ]
        )

    writer.writerow([])
    writer.writerow(["Summary"])
    writer.writerow(["Subject Code", "Total Attendance"])
    for row in summary:
        writer.writerow([sanitize_export_cell(row["subject_code"]), sanitize_export_cell(row["total"])])

    csv_content = "\ufeff" + output.getvalue()
    filename = f"attendance_report_{selected_date}.csv"

    return Response(
        csv_content,
        mimetype="text/csv; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@app.route("/attendance/report.xlsx")
@permission_required(PERMISSION_REPORTS_EXECUTE)
def attendance_report_xlsx() -> Any:
    user = current_user()
    assert user is not None

    _, selected_date, selected_subject_id, _, _ = resolve_report_filters(user)
    records, summary = fetch_attendance_report_data(user, selected_date, selected_subject_id)

    if Workbook is None:
        flash("Excel export requires openpyxl. Install dependencies and retry.", "warning")
        params: dict[str, Any] = {"date": selected_date}
        if selected_subject_id is not None:
            params["subject_id"] = selected_subject_id
        return redirect(url_for("attendance_report", **params))

    workbook = Workbook()
    details_sheet = workbook.active
    details_sheet.title = "Attendance"
    details_sheet.append(["Date", "Marked At", "Subject Code", "Subject Name", "USN", "Student Name", "Branch", "Semester", "Method", "Confidence"])

    for row in records:
        details_sheet.append(
            [
                sanitize_export_cell(row["attendance_date"]),
                sanitize_export_cell(row["marked_at"]),
                sanitize_export_cell(row["subject_code"]),
                sanitize_export_cell(row["subject_name"]),
                sanitize_export_cell(row["usn"]),
                sanitize_export_cell(row["full_name"]),
                sanitize_export_cell(row["branch"]),
                sanitize_export_cell(row["semester"]),
                sanitize_export_cell(row["method"]),
                sanitize_export_cell(row["confidence"]),
            ]
        )

    summary_sheet = workbook.create_sheet("Summary")
    summary_sheet.append(["Subject Code", "Total Attendance"])
    for row in summary:
        summary_sheet.append([sanitize_export_cell(row["subject_code"]), sanitize_export_cell(row["total"])])

    content = io.BytesIO()
    workbook.save(content)
    content.seek(0)

    filename = f"attendance_report_{selected_date}.xlsx"
    return Response(
        content.getvalue(),
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@app.route("/api/recognize", methods=["POST"])
@permission_required(PERMISSION_ATTENDANCE_EXECUTE)
def recognize_face() -> Any:
    user = current_user()
    assert user is not None

    payload = request.get_json(silent=True) or {}
    subject_id_raw = payload.get("subject_id")
    image_data = payload.get("image_data", "")

    try:
        subject_id = int(subject_id_raw)
    except (TypeError, ValueError):
        return jsonify({"status": "error", "message": "Invalid subject id."}), 400

    subject = get_subject_for_user(subject_id, user)
    if subject is None:
        return jsonify({"status": "error", "message": "Subject not found or inaccessible."}), 404

    try:
        frame = face_engine.decode_data_url(image_data)
    except ValueError as exc:
        return jsonify({"status": "error", "message": str(exc)}), 400

    probe, extract_error = face_engine.extract_embedding(frame)
    if extract_error is not None:
        return jsonify({"status": "error", "message": extract_error}), 422

    candidates = query_all(
        """
        SELECT st.id, st.usn, st.full_name, fp.embedding
        FROM students st
        JOIN face_profiles fp ON fp.student_id = st.id
        WHERE st.is_active = 1 AND st.branch = ? AND st.semester = ?
        """,
        (subject["branch"], subject["semester"]),
    )

    if not candidates:
        return jsonify(
            {
                "status": "error",
                "message": "No enrolled face profiles found for this subject.",
            }
        ), 404

    best: Optional[tuple[sqlite3.Row, MatchResult]] = None
    for candidate in candidates:
        embedding = parse_embedding(candidate["embedding"])
        if embedding is None:
            continue

        result = face_engine.compare(probe, embedding)
        if best is None or result.score > best[1].score:
            best = (candidate, result)

    if best is None or not best[1].matched:
        return jsonify(
            {
                "status": "unknown",
                "message": "No matching student found.",
                "backend": face_engine.backend,
            }
        )

    candidate, result = best
    already_marked = query_one(
        """
        SELECT id
        FROM attendance_records
        WHERE attendance_date = ? AND subject_id = ? AND student_id = ?
        """,
        (today_str(), subject_id, candidate["id"]),
    )

    return jsonify(
        {
            "status": "matched",
            "backend": face_engine.backend,
            "student": {
                "id": candidate["id"],
                "usn": candidate["usn"],
                "full_name": candidate["full_name"],
            },
            "confidence": round(result.confidence * 100.0, 2),
            "already_marked": already_marked is not None,
        }
    )


@app.route("/api/attendance/mark", methods=["POST"])
@permission_required(PERMISSION_ATTENDANCE_WRITE)
def api_mark_attendance() -> Any:
    user = current_user()
    assert user is not None

    payload = request.get_json(silent=True) or {}

    try:
        subject_id = int(payload.get("subject_id"))
        student_id = int(payload.get("student_id"))
    except (TypeError, ValueError):
        return jsonify({"status": "error", "message": "subject_id and student_id must be integers."}), 400

    method = payload.get("method", "manual")
    if method not in {"face", "manual"}:
        return jsonify({"status": "error", "message": "Invalid mark method."}), 400

    confidence = payload.get("confidence")
    if confidence is not None:
        try:
            confidence = float(confidence)
        except (TypeError, ValueError):
            confidence = None

    success, message, status_code = mark_attendance(subject_id, student_id, method, confidence, user)

    if not success:
        return jsonify({"status": "error", "message": message}), status_code

    return jsonify({"status": "ok", "message": message}), status_code


@app.route("/api/attendance/manual", methods=["POST"])
@permission_required(PERMISSION_ATTENDANCE_WRITE)
def api_manual_attendance() -> Any:
    user = current_user()
    assert user is not None

    payload = request.get_json(silent=True) or {}
    usn = payload.get("usn", "").strip().upper()

    try:
        subject_id = int(payload.get("subject_id"))
    except (TypeError, ValueError):
        return jsonify({"status": "error", "message": "Invalid subject id."}), 400

    if not USN_RE.match(usn):
        return jsonify({"status": "error", "message": "USN format is invalid."}), 400

    student = query_one("SELECT id FROM students WHERE usn = ? AND is_active = 1", (usn,))
    if student is None:
        return jsonify({"status": "error", "message": "Student not found."}), 404

    success, message, status_code = mark_attendance(subject_id, student["id"], "manual", None, user)
    if not success:
        return jsonify({"status": "error", "message": message}), status_code

    return jsonify({"status": "ok", "message": message}), status_code


@app.route("/health")
def health() -> Any:
    return jsonify(
        {
            "status": "ok",
            "face_backend": face_engine.backend,
            "date": today_str(),
        }
    )


@app.errorhandler(404)
def not_found(_: Any) -> tuple[str, int]:
    return render_template("error.html", message="Page not found."), 404


@app.errorhandler(500)
def internal_error(_: Any) -> tuple[str, int]:
    return render_template("error.html", message="Unexpected server error."), 500


with app.app_context():
    init_db()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
