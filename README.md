# Automated Attendance System Using Face Recognition (v2)

A rebuilt version of the project with a stable Flask backend, responsive animated frontend, and edge-case-safe attendance flows.

## What Changed in v2

1. Full backend rewrite (`web.py`) with SQLite local storage.
2. Segmented RBAC with `student`, `teacher`, `department_head`, `principal`, and `super_admin`.
3. New schema with foreign keys, uniqueness constraints, and safer CRUD flows.
4. Live attendance APIs for face scan and manual fallback marking.
5. Face profile enrollment per student via browser camera.
6. Modern responsive frontend with animation and mobile support.
7. Attendance report exports (CSV and XLSX).
8. Automated test suite for critical flows.

## Tech Stack

- Python 3.10+
- Flask
- SQLite (built-in)
- OpenCV (`opencv-python`)
- NumPy
- OpenPyXL (for XLSX export)
- Pytest (for automated tests)
- Optional: `face_recognition` for stronger matching

## Quick Start

1. Create virtual environment:

```bash
python -m venv .venv
```

2. Activate environment:

Windows PowerShell:

```powershell
.\.venv\Scripts\Activate.ps1
```

3. Install dependencies:

```bash
pip install -r requirements.txt
```

4. Run the app:

```bash
python web.py
```

5. Open:

```text
http://127.0.0.1:5000
```

## Default Login

- Username: `admin`
- Password: `Admin@123`

You should change credentials immediately in production use.

Default `admin` is seeded as `super_admin`.

## Optional Environment Variables

- `APP_SECRET_KEY`: Flask session secret.
- `APP_DB_PATH`: custom SQLite file path.
- `DEFAULT_ADMIN_USERNAME`: Seed admin username.
- `DEFAULT_ADMIN_PASSWORD`: Seed admin password.
- `DEFAULT_ADMIN_FULL_NAME`: Seed admin display name.

## Main Screens

1. Landing page with project overview.
2. Login.
3. Dashboard (role-aware stats).
4. Students (create/delete + face enrollment).
5. Access Control (account creation + role segments + grant/revoke permissions).
6. Subjects (create/delete + assignment).
7. Branch/Semester Matrix (activate/deactivate academic scopes).
8. Live Attendance (camera recognition + manual USN fallback).
9. Reports (filter by date/subject + CSV/XLSX export).

## Role Segments and Permissions

- `super_admin`: full read/write/execute plus permission grants.
- `principal`: institute-wide read/write/execute (no grant privileges).
- `department_head`: branch-scoped governance for users, students, subjects, attendance, reports.
- `teacher`: assigned-subject attendance execution and reports.
- `student`: read-only personal attendance and subjects.

Custom permission grants can be applied from `Access` by super admins.

## Dedicated Role Interfaces

`/dashboard` now renders a full dedicated interface per segment:

1. Super Admin Command Center.
2. Principal Strategy Deck.
3. Department Head Hub.
4. Teacher Operations Console.
5. Student Progress Desk.

Each workspace has:

- Role-specific KPIs and action cards.
- Scoped operational tables.
- Contextual alerts for edge-case monitoring.

## Report Export

Use the attendance report page and click:

- `Export CSV`
- `Export XLSX`

Both exports respect your role permissions and selected filters.

## Automated Tests

Run the test suite:

```bash
python -m pytest -q
```

Current tests cover:

1. Admin login/logout flow.
2. Teacher read-only student constraints.
3. Attendance duplicate guard.
4. CSV export output integrity.
5. XLSX export download behavior.
6. Student report read-only behavior.

## Face Recognition Behavior

The system chooses one backend automatically:

1. `face_recognition` if installed.
2. OpenCV fallback if not installed.

Fallback mode is designed to work on lower-end machines with minimal setup.

## Edge Cases Handled

1. Duplicate attendance for same day/subject/student.
2. Invalid or malformed inputs.
3. Unauthorized route/API access.
4. Branch/semester scope validation and activation guards.
5. Student not eligible for subject branch/semester.
6. Self-deactivation and last-super-admin lock prevention.
7. No face, multiple faces, or invalid frame payload.
8. Missing face profile for recognition attempts.
9. Camera permission denied in browser.

## Project Files

- `web.py`: app, DB schema, routes, auth, APIs, face engine.
- `templates/`: all rebuilt Jinja templates.
- `static/css/app.css`: animated responsive design.
- `static/js/students.js`: face profile capture flow.
- `static/js/live_attendance.js`: live attendance interactions.
- `tests/`: automated test suite.
- `PROJECT_AUDIT.md`: legacy issue list.
- `NEXT_VERSION_PLAN.md`: implementation plan and edge-case coverage.

## Health Check

Open:

```text
/health
```

Returns JSON with system status and selected face backend.
