from datetime import date

import web


def login(client, username="admin", password="Admin@123"):
    return client.post(
        "/login",
        data={"username": username, "password": password},
        follow_redirects=False,
    )


def seed_subject_student_and_mark(client):
    login(client)

    client.post(
        "/staff/create",
        data={
            "username": "staff1",
            "full_name": "Staff One",
            "branch": "CSE",
            "password": "Strong@123",
        },
    )

    with web.app.app_context():
        staff_row = web.get_db().execute("SELECT id FROM users WHERE username = ?", ("staff1",)).fetchone()
        assert staff_row is not None
        staff_id = staff_row["id"]

    client.post(
        "/subjects/create",
        data={
            "code": "CS101",
            "name": "Data Structures",
            "branch": "CSE",
            "semester": "3",
            "start_time": "09:00",
            "end_time": "10:00",
            "staff_id": str(staff_id),
        },
    )

    client.post(
        "/students/create",
        data={
            "usn": "1AB23CD456",
            "full_name": "Alice Test",
            "branch": "CSE",
            "semester": "3",
        },
    )

    with web.app.app_context():
        subject_row = web.get_db().execute("SELECT id FROM subjects WHERE code = ?", ("CS101",)).fetchone()
        assert subject_row is not None
        subject_id = subject_row["id"]

    mark_response = client.post(
        "/api/attendance/manual",
        json={"subject_id": subject_id, "usn": "1AB23CD456"},
    )
    assert mark_response.status_code == 200

    return subject_id


def test_admin_login_and_logout_flow(client):
    dashboard_response = client.get("/dashboard")
    assert dashboard_response.status_code == 302
    assert "/login" in dashboard_response.headers["Location"]

    login_response = login(client)
    assert login_response.status_code == 302
    assert "/dashboard" in login_response.headers["Location"]

    dashboard_response = client.get("/dashboard")
    assert dashboard_response.status_code == 200

    logout_response = client.post("/logout")
    assert logout_response.status_code == 302
    assert logout_response.headers["Location"].endswith("/")


def test_teacher_has_students_read_but_no_write(client):
    login(client)
    client.post(
        "/staff/create",
        data={
            "username": "staff2",
            "full_name": "Staff Two",
            "branch": "CSE",
            "password": "Strong@123",
        },
    )
    client.post("/logout")

    staff_login_response = login(client, username="staff2", password="Strong@123")
    assert staff_login_response.status_code == 302

    students_response = client.get("/students")
    assert students_response.status_code == 200

    create_response = client.post(
        "/students/create",
        data={
            "usn": "1AB23CD457",
            "full_name": "Blocked Create",
            "branch": "CSE",
            "semester": "3",
        },
        follow_redirects=False,
    )
    assert create_response.status_code == 302
    assert "/dashboard" in create_response.headers["Location"]


def test_manual_attendance_duplicate_guard(client):
    subject_id = seed_subject_student_and_mark(client)

    duplicate_response = client.post(
        "/api/attendance/manual",
        json={"subject_id": subject_id, "usn": "1AB23CD456"},
    )
    assert duplicate_response.status_code == 409
    assert duplicate_response.json["status"] == "error"


def test_csv_export_contains_marked_record(client):
    seed_subject_student_and_mark(client)
    report_date = date.today().isoformat()

    response = client.get(f"/attendance/report.csv?date={report_date}")
    assert response.status_code == 200
    assert "text/csv" in response.content_type
    assert "attachment; filename=attendance_report_" in response.headers.get("Content-Disposition", "")

    text = response.data.decode("utf-8-sig")
    assert "Subject Code" in text
    assert "CS101" in text
    assert "1AB23CD456" in text


def test_xlsx_export_download(client):
    seed_subject_student_and_mark(client)
    report_date = date.today().isoformat()

    response = client.get(f"/attendance/report.xlsx?date={report_date}")
    if response.status_code == 302:
        assert "/attendance/report" in response.headers["Location"]
        return

    assert response.status_code == 200
    assert response.headers["Content-Disposition"].endswith(".xlsx")
    assert response.data[:2] == b"PK"


def test_student_report_read_only_access(client):
    login(client)
    client.post(
        "/students/create",
        data={
            "usn": "1AB23CD458",
            "full_name": "Student Readonly",
            "branch": "CSE",
            "semester": "3",
            "create_account": "on",
            "account_password": "Strong@123",
        },
    )
    client.post("/logout")

    student_login = login(client, username="1ab23cd458", password="Strong@123")
    assert student_login.status_code == 302

    report_response = client.get("/attendance/report")
    assert report_response.status_code == 200

    csv_response = client.get("/attendance/report.csv")
    assert csv_response.status_code == 302
    assert "/dashboard" in csv_response.headers["Location"]

    live_response = client.get("/attendance/live")
    assert live_response.status_code == 302
    assert "/dashboard" in live_response.headers["Location"]


def test_role_specific_dashboard_interfaces(client):
    login(client)
    client.post(
        "/staff/create",
        data={
            "segment": "principal",
            "username": "principal1",
            "full_name": "Principal One",
            "password": "Strong@123",
        },
    )
    client.post(
        "/staff/create",
        data={
            "segment": "department_head",
            "username": "hod1",
            "full_name": "Hod One",
            "branch": "CSE",
            "password": "Strong@123",
        },
    )
    client.post(
        "/staff/create",
        data={
            "segment": "teacher",
            "username": "teacher1",
            "full_name": "Teacher One",
            "branch": "CSE",
            "password": "Strong@123",
        },
    )
    client.post(
        "/students/create",
        data={
            "usn": "1AB23CD459",
            "full_name": "Student Interface",
            "branch": "CSE",
            "semester": "3",
            "create_account": "on",
            "account_password": "Strong@123",
        },
    )
    client.post("/logout")

    assert login(client, username="principal1", password="Strong@123").status_code == 302
    principal_dashboard = client.get("/dashboard")
    assert principal_dashboard.status_code == 200
    assert b"Principal Strategy Deck" in principal_dashboard.data
    client.post("/logout")

    assert login(client, username="hod1", password="Strong@123").status_code == 302
    hod_dashboard = client.get("/dashboard")
    assert hod_dashboard.status_code == 200
    assert b"Department Hub" in hod_dashboard.data
    client.post("/logout")

    assert login(client, username="teacher1", password="Strong@123").status_code == 302
    teacher_dashboard = client.get("/dashboard")
    assert teacher_dashboard.status_code == 200
    assert b"Teacher Operations Console" in teacher_dashboard.data
    client.post("/logout")

    assert login(client, username="1ab23cd459", password="Strong@123").status_code == 302
    student_dashboard = client.get("/dashboard")
    assert student_dashboard.status_code == 200
    assert b"Student Progress Desk" in student_dashboard.data
