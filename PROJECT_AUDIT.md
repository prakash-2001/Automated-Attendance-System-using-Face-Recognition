# Legacy Project Audit (Before v2 Rebuild)

Date: 2026-03-02
Scope: Original `web.py` + legacy `templates/`

## Critical Failures Found

1. Duplicate function definitions (`fetch_start_end_times` defined twice), causing hidden behavior override.
2. Mixed and conflicting database strategies (`MySQLdb`, `mysql.connector`, and global shared `db` connection) without lifecycle control.
3. Global DB connection objects reused across requests (`db = mysql.connector.connect(...)`) causing stale-connection and concurrency failures.
4. Session keys were inconsistent (`loggedin`, `username`, `dept_id`, `staff_id`) and logout removed only `username`, leaving privileged state behind.
5. Many routes redirected to non-existing endpoint names (`url_for('dept_login')` while function name was `login`) causing runtime 500 errors.
6. Blocking webcam attendance loop in request thread (`/run_prg`) prevented responsive server behavior and made app unresponsive.
7. Missing routes referenced by UI (`/stop`) led to dead controls.
8. Error handling referenced undefined exceptions (`except Error as e`) and missing templates (`error.html` in old tree), creating crash cascades.
9. Business logic allowed duplicate attendance inserts and lacked uniqueness controls.
10. Credential storage and verification were plain-text in DB queries (no password hashing).

## Logic and Data Integrity Issues

1. Attendance date/time filtering logic used first row from `subject_log` globally instead of selected subject context.
2. Student/staff/subject operations did not consistently enforce branch and semester compatibility.
3. Subject and attendance queries were often unscoped (`SELECT * FROM subject_log`) causing data leakage across departments.
4. Face image file naming assumptions (`filename.split('_', 1)`) could break on unexpected filenames.
5. Duplicate unreachable code blocks existed (`return` followed by additional logic in same branch).
6. Multiple render paths returned templates without required context objects.
7. HTML forms frequently posted to routes that rendered unrelated views without fetching data, leading to empty/incorrect pages.

## Frontend and UX Issues

1. Most templates used absolute positioning and fixed widths, breaking on mobile and low-resolution displays.
2. Inline CSS/JS duplication across many templates increased maintenance cost and inconsistencies.
3. Broken nested `<title>` tags and malformed form markup in legacy pages.
4. Camera preview logic on add-student page did not send image frames to backend for profile creation.
5. Navigation references included deprecated/unused routes.

## Security and Reliability Gaps

1. No role-based authorization decorators; route checks were manual and inconsistent.
2. Missing consistent input validation and normalization for many fields.
3. No DB-level constraints to prevent duplicates or invalid attendance combinations.
4. No robust JSON API contracts for frontend/backend communication.
5. Error handling leaked internal exception text in responses.

## Conclusion

The legacy codebase had structural, logical, and operational issues severe enough that direct patching would remain fragile. Rebuilding a clean v2 architecture was the correct path for maintainability and reliability.
