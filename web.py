import subprocess
import os
import MySQLdb
import cv2
from flask import Flask, redirect, render_template, jsonify, request, session, url_for, flash
import re
from flask_mysqldb import MySQL
from python.data_set import open_camera
from collections import Counter
import face_recognition
import numpy as np
import csv
from datetime import datetime, timedelta
import time
import face_recognition
import mysql.connector
# from app import app

app = Flask(__name__, static_url_path="/static")
app.secret_key = 'your_secret_key'

#database connection start
app.config['MYSQL_HOST']="localhost"
app.config['MYSQL_USER']="root"
app.config['MYSQL_PASSWORD']=""
app.config['MYSQL_DB']="face_rec_db"

db_config = {
            'host': 'localhost',
            'user': 'root',
            'password': '',  # your MySQL password
            'database': 'face_rec_db'
            }


#main page
@app.route("/")
def main_page():
    return render_template("main_page.html")

#external staff login navigation
@app.route("/nav_staff_login")
def nav_staff_login():
    return render_template("staff_login.html")


#navigate login
@app.route("/nav_dept_login")
def nav_dept_login():
    return render_template("dept_login.html")

#attendance_data nav
@app.route('/attendance_data')
def attendance_data():

    # Check if the user is logged in as a department
    if 'loggedin' not in session or not session['loggedin']:
        # Redirect to login page if not logged in
        return redirect(url_for('dept_login'))

    # Get the logged-in department's branch from the session
    dept_branch = session['dept_branch']

    # Establish a connection to the database
    mysql_connection = mysql.connector.connect(**db_config)
    cursor = mysql_connection.cursor()

    # Query the subject_log table to get subject codes that match the department's branch
    cursor.execute('SELECT subject_code FROM subject_log WHERE branch_allot = %s', (dept_branch,))
    # Fetch all results
    subject_codes = cursor.fetchall()

    # Close the cursor and connection
    cursor.close()
    mysql_connection.close()

    # Process fetched subject codes if necessary
    # You can extract subject codes from the fetched rows and pass them to the template

    # Render the 'attendance_data.html' template and pass the subject codes
    # as part of the context
    return render_template('attendance_data.html', subject_codes=subject_codes)


@app.route("/delete_student")
def delete_student():
    # Check if the user is logged in as a department
    if 'loggedin' not in session or not session['loggedin']:
        # Redirect to login page if not logged in
        return redirect(url_for('dept_login'))

    # Get the logged-in department's branch from the session
    dept_branch = session['dept_branch']

    # Establish a connection to the database
    mysql_connection = mysql.connector.connect(**db_config)
    cursor = mysql_connection.cursor()

    # Query the student_db table to get USNs that match the department's branch
    cursor.execute('SELECT usn FROM student_db WHERE branch = %s', (dept_branch,))
    # Fetch all results
    usns = cursor.fetchall()

    # Close the cursor and connection
    cursor.close()
    mysql_connection.close()

    # Render the 'attendance_data.html' template and pass the USNs
    # as part of the context
    return render_template('delete_student.html', usns=usns)


# delete operation
@app.route("/delete_student_data", methods=['POST'])
def delete_student_data():
    # Check if the user is logged in as a department
    if 'loggedin' not in session or not session['loggedin']:
        # Redirect to login page if not logged in
        return redirect(url_for('dept_login'))

    # Get the selected USN from the form
    selected_usn = request.form['selected_usn']

    # Establish a connection to the database
    mysql_connection = mysql.connector.connect(**db_config)
    cursor = mysql_connection.cursor()

    try:
        # Execute a SQL DELETE query to remove the row where the USN matches the selected USN
        cursor.execute('DELETE FROM student_db WHERE usn = %s', (selected_usn,))
        cursor.execute('DELETE FROM attendance_log WHERE usn = %s', (selected_usn,))
         
        # Commit the changes to the database
        mysql_connection.commit()

        # Close the cursor and connection
        cursor.close()
        mysql_connection.close()

        # Redirect to the student_view.html page after successfully deleting the student data
        return redirect(url_for('student_view'))

    except Exception as e:
        # If an error occurs, rollback the transaction and handle the error
        mysql_connection.rollback()
        # Handle the error, you can render an error page or redirect to another page
        return render_template('error.html', error=str(e))


# delete operation
@app.route("/delete_staff_data", methods=['POST'])
def delete_staff_data():
    # Check if the user is logged in as a department
    if 'loggedin' not in session or not session['loggedin']:
        # Redirect to login page if not logged in
        return redirect(url_for('dept_login'))

    # Get the selected USN from the form
    selected_staff = request.form['selected_staff']

    # Establish a connection to the database
    mysql_connection = mysql.connector.connect(**db_config)
    cursor = mysql_connection.cursor()

    try:
        # Execute a SQL DELETE query to remove the row where the USN matches the selected USN
        cursor.execute('DELETE FROM faculty_db WHERE staff_name = %s', (selected_staff,))
         
        # Commit the changes to the database
        mysql_connection.commit()

        # Close the cursor and connection
        cursor.close()
        mysql_connection.close()

        # Redirect to the student_view.html page after successfully deleting the student data
        return redirect(url_for('staff_view'))

    except Exception as e:
        # If an error occurs, rollback the transaction and handle the error
        mysql_connection.rollback()
        # Handle the error, you can render an error page or redirect to another page
        return render_template('error.html', error=str(e))



app.static_folder = os.path.join(app.root_path, '/photos')
@app.route("/staff_student_view")
def staff_student_view():
    if 'loggedin' not in session:
        return redirect(url_for('login'))

    try:
        # Connect to MySQL database
        mysql_connection = mysql.connector.connect(**db_config)
        cur = mysql_connection.cursor(dictionary=True)

        # Execute query to get students from the same branch as the staff
        cur.execute('SELECT * FROM student_db WHERE branch = %s', (session['staff_branch'],))
        staff_student_dbs = cur.fetchall()

        # Dictionary to map each student's USN to their first image file
        usn_to_image = {}

        # Path to the photos folder
        photos_folder = os.path.join(app.root_path, 'photos')
        
        # Iterate over the files in the 'photos' folder
        for filename in os.listdir(photos_folder):
            # Split the filename at the underscore
            usn, suffix = filename.split('_', 1)
            if suffix.startswith('1'):
                # Map the USN to the first image file path
                usn_to_image[usn] = os.path.join('photos', filename)

        # Close the cursor and connection
        cur.close()
        mysql_connection.close()

        # Debug: Print the USN-to-image mapping
        print("USN-to-image mapping:", usn_to_image)

        # Render the template with the list of students and their corresponding first images
        return render_template('staff_student_view.html', staff_student_dbs=staff_student_dbs, usn_to_image=usn_to_image)

    except mysql.connector.Error as e:
        print(f"Database error: {e}")
        return render_template('error.html', error='Database error occurred.')


#dept login
@app.route("/dept_login", methods=['POST','GET'])
# @app.route('/pythonlogin/', methods=['GET', 'POST'])
def login():
    # Output a message if something goes wrong...
    msg = ''
                   # Check if "dept_id" and "dept_passwd" POST requests exist (user submitted form)
    if request.method == 'POST' and 'dept_id' in request.form and 'dept_passwd' in request.form:
        # Create variables for easy access
        dept_id = request.form['dept_id']
        dept_passwd = request.form['dept_passwd']           

        # Establish the connection
        mysql_connection = mysql.connector.connect(**db_config)

        # Create a dictionary cursor
        cursor = mysql_connection.cursor(dictionary=True)
        # Check if dept exists using MySQL
        
        cursor.execute('SELECT * FROM dept_login WHERE dept_id = %s AND dept_passwd = %s', (dept_id, dept_passwd,))
        # Fetch one record and return result
        dept = cursor.fetchone()
        # If dept exists in dept_login table in out database
        if dept:
            # Create session data, we can access this data in other routes
            session['loggedin'] = True
            session['dept_id'] = dept['dept_id']
            session['dept_head_name']=dept['dept_head_name']
            session['dept_branch']=dept['dept_branch']
            session['dept_passwd'] = dept['dept_passwd']
            # Redirect to home page
            msg="logged in sucessfully !"
            return render_template('index.html', msg=msg, dept=dept)
        else:
            # dept doesnt exist or dept_id/dept_passwd incorrect
            msg = 'Incorrect dept_id/dept_passwd!'
    # Show the login form with message (if any)
            return render_template('dept_login.html', msg=msg)
    return render_template('dept_login.html', msg=msg)


#staff login
@app.route("/staff_login", methods=['POST','GET'])
# @app.route('/pythonlogin/', methods=['GET', 'POST'])
def staff_login():
    # Output a message if something goes wrong...
    msg = ''
                   # Check if "dept_id" and "dept_passwd" POST requests exist (user submitted form)
    if request.method == 'POST' and 'staff_id' in request.form and 'staff_passwd' in request.form:
        # Create variables for easy access
        staff_id = request.form['staff_id']
        staff_passwd = request.form['staff_passwd']

        # Establish the connection
        mysql_connection = mysql.connector.connect(**db_config)

        # Create a dictionary cursor
        cursor = mysql_connection.cursor(dictionary=True)
        # Check if dept exists using MySQL
        
        cursor.execute('SELECT * FROM faculty_db WHERE staff_id = %s AND staff_passwd = %s', (staff_id, staff_passwd,))
        # Fetch one record and return result
        staff = cursor.fetchone()
        # If dept exists in dept_login table in out database
        if staff:
            # Create session data, we can access this data in other routes
            session['loggedin'] = True
            session['staff_id'] = staff['staff_id']
            session['staff_name']=staff['staff_name']
            session['staff_branch']=staff['staff_branch']
            session['staff_passwd'] = staff['staff_passwd']
            # Redirect to home page
            msg="logged in sucessfully !"
            return render_template('staff_index.html', msg=msg, staff=staff)
        else:
            # dept doesnt exist or dept_id/dept_passwd incorrect
            msg = 'Incorrect staff_id/staff_passwd!'
    # Show the login form with message (if any)
            return render_template('staff_login.html', msg=msg)
    return render_template('staff_login.html', msg=msg)


#logout session
@app.route("/logout")
def logout():
    session.pop('username', None)
    return redirect(url_for('main_page'))


#home navigation
@app.route("/index")
def index():
    if 'loggedin' in session and session['loggedin']:
        # You can access session variables like session['dept_branch'] and session['dept_head_name'] here
        dept = {
            'dept_branch': session['dept_branch'],
            'dept_head_name': session['dept_head_name']
        }
        return render_template('index.html', dept=dept)
    else:
        return redirect(url_for('dept_login'))

#staff index nav
@app.route("/staff_index")
def staff_index():
    if 'loggedin' in session and session['loggedin']:
        # You can access session variables like session['staff_branch'] and session['staff_name'] here
        staff = {
            'staff_branch': session['staff_branch'],
            'staff_name': session['staff_name']
        }
        return render_template('staff_index.html', staff=staff)
    else:
        return redirect(url_for('staff_login'))




#attendance navigation
@app.route("/attendance")
def attendance():
        return render_template("attendance.html") 

#student view navigation
@app.route('/student_view')
def student_view():
    if 'loggedin' not in session:
        return redirect(url_for('login'))
    
    mysql_connection = mysql.connector.connect(**db_config)
    cursor = mysql_connection.cursor(dictionary=True)
    
    try:
        cursor.execute('SELECT * FROM student_db WHERE branch = %s', (session['dept_branch'],))
        student_dbs = cursor.fetchall()
        
        if student_dbs:
            return render_template('student_view.html', student_dbs=student_dbs)
        else:
            return render_template('student_view.html', student_dbs=[])
    
    except Error as e:
        print(f"Database error: {e}")
        return render_template('error.html', error='Database error occurred.')


#staff view
@app.route('/staff_view', methods=['POST', 'GET'])
def staff_view():
    if 'loggedin' not in session:
        return redirect(url_for('login'))
    
    try:
        mysql_connection = mysql.connector.connect(**db_config)
        cursor = mysql_connection.cursor(dictionary=True)
        
        # Fetching staff_id, staff_name, and staff_branch from faculty_db
        cursor.execute('SELECT staff_id, staff_name, staff_branch FROM faculty_db WHERE staff_branch = %s', (session['dept_branch'],))
        staff_dbs = cursor.fetchall()
        
        # Debug: print the query results to check the data
        print("staff_dbs:", staff_dbs)
        
        return render_template('staff_view.html', staff_dbs=staff_dbs)
    
    except mysql.connector.Error as e:
        print(f"Database error: {e}")
        return render_template('error.html', error='Database error occurred.')

    except Exception as e:
        print(f"Error: {e}")
        return render_template('error.html', error='An unexpected error occurred.')
        
#subject view
@app.route("/subject_view")
def subject_view():
    db = mysql.connector.connect(**db_config)
    cursor = db.cursor()
    cursor.execute("SELECT * FROM subject_log")
    subject_dbs = cursor.fetchall()
    cursor.close()
    db.close()
    return render_template("subject_view.html", subject_dbs=subject_dbs)

#add_student navigation
@app.route("/add_student")
def add_student():
    return render_template("add_student.html")

#add_staff navigation
@app.route("/add_staff")
def add_staff():
    return render_template("add_staff.html")


@app.route("/data_attendance")
def data_attendance():
    # Check if the user is logged in as a department
    if 'loggedin' not in session or not session['loggedin']:
        # Redirect to login page if not logged in
        return redirect('/dept_login')
    
    # Get the logged-in department's branch from the session
    dept_branch = session['dept_branch']

    # Establish a connection to the database
    mysql_connection = mysql.connector.connect(**db_config)
    cursor = mysql_connection.cursor()

    # Query the subject_log table to get subject codes that match the department's branch
    cursor.execute('SELECT subject_code FROM subject_log WHERE branch_allot = %s', (dept_branch,))
    # Fetch all results
    subject_codes = cursor.fetchall()

    # Close the cursor and connection
    cursor.close()
    mysql_connection.close()

    # Render the data in HTML
    # Passing the list of subject codes to the template to display in a dropdown
    return render_template('data_attendance.html', subject_codes=subject_codes)



db = mysql.connector.connect(**db_config)  
root_folder = os.path.join(os.getcwd(), 'photos')  

#add_subject navigation
@app.route("/submit_form", methods=["GET", "POST"])
# Path to the root folder for saving image
def submit_form():
    if request.method == 'POST':
        # Retrieve data from the form
        usn = request.form.get('usn')
        name = request.form.get('name')
        branch = request.form.get('branch')
        sem = request.form.get('sem')

        # Define the regular expression patterns for USN and name validation
        usn_pattern = r'^\d{1}[a-zA-Z]{2}\d{2}[a-zA-Z]{2}\d{3}$'
        name_pattern = r'^[a-zA-Z\s]+$'
    

        # Validate the USN and name format
        if not re.match(usn_pattern, usn):
            flash("Invalid USN format. Please enter a valid USN in the format: int(1)char(2)int(2)char(2)int(3).")
            return render_template('add_student.html')
        
        if not re.match(name_pattern, name):
            flash("Invalid name format. Name must contain only letters and spaces.")
            return render_template('add_student.html')

        # Check for duplicate USN in the database
        cursor = db.cursor()
        cursor.execute("SELECT COUNT(*) FROM student_db WHERE usn = %s", (usn,))
        count = cursor.fetchone()[0]

        if count > 0:
            # If the USN already exists, notify the user and render the form page again
            flash(f"USN {usn} already exists. Please enter a different USN.")
            return render_template('add_student.html')

        # Proceed with inserting data into the database
        cursor.execute("INSERT INTO student_db (usn, name, branch, sem) VALUES (%s, %s, %s, %s)", (usn, name, branch, sem))
        db.commit()
        cursor.close()

        # Capture images using the capture_images function
        image_paths = capture_images(usn)

        # Render the student view template with context data
        return render_template('student_view.html', usn=usn, name=name, branch=branch, sem=sem, image_paths=image_paths)

        # Capture images using the capture_images function
        image_paths = capture_images(usn)

        # Render the student view template with context data
        return render_template('student_view.html', usn=usn, name=name, branch=branch, sem=sem, image_paths=image_paths)

def capture_images(usn):
    cap = cv2.VideoCapture(0)
    image_paths = []

    for i in range(5):
        ret, frame = cap.read()
        if ret:
            image_name = f'{usn}_{i + 1}.png'
            image_path = os.path.join(root_folder, image_name)
            cv2.imwrite(image_path, frame)
            image_paths.append(image_path)
            cv2.imshow('Captured Image', frame)
            cv2.waitKey(500)  # Wait for 500 ms

    cap.release()
    cv2.destroyAllWindows()

    return image_paths  # Return the list of image paths

@app.route("/staff_form", methods=["GET", "POST"])
def staff_form():
    if request.method == 'POST':
        # Get form data
        staff_id = request.form['staff_id']
        staff_name = request.form['staff_name']
        staff_branch = request.form['staff_branch']
        staff_passwd = request.form['staff_passwd']
        
        # Define regex patterns for staff ID and password validation
        staff_id_pattern = r'^4HG[a-zA-Z]{2}\d{3}$'  # Format: 4HG char(2) int(3)
        password_pattern = r'^(?=.*[A-Z])(?=.*\d)(?=.*[\W_]).{8,}$'  # At least one uppercase letter, one digit, one special character, min 8 chars
        
        # Validate staff ID format
        if not re.match(staff_id_pattern, staff_id):
            flash("Invalid staff ID format. Please use the format: '4HG'char(2)int(3).")
            return render_template("add_staff.html")  # Adjust as needed

        # Validate password format
        if not re.match(password_pattern, staff_passwd):
            flash("Invalid password format. Password must be at least 8 characters long, and contain at least one uppercase letter, one digit, and one special character.")
            return render_template("add_staff.html")  # Adjust as needed
        
        # Check for duplicate staff ID in the database
        cursor = db.cursor()
        cursor.execute("SELECT COUNT(*) FROM faculty_db WHERE staff_id = %s", (staff_id,))
        count = cursor.fetchone()[0]
        
        if count > 0:
            # If the staff ID already exists, notify the user
            flash("Staff ID already exists. Please use a different staff ID.")
            return render_template("add_staff.html")  # Adjust as needed
        
        # If all validations pass and no duplicate staff ID, insert data into faculty_db
        cursor.execute("INSERT INTO faculty_db (staff_id, staff_name, staff_branch, staff_passwd) VALUES (%s, %s, %s, %s)",
                       (staff_id, staff_name, staff_branch, staff_passwd))
        
        # Commit the transaction
        db.commit()
        
        # Close the cursor
        cursor.close()
        
        # Redirect or render the appropriate template (staff_view.html)
        return render_template("staff_view.html")

    # Render the staff form template for GET requests
    return render_template("add_staff.html")

#add subject
@app.route("/add_subject", methods=["GET", "POST"])
def add_subject():
    if 'loggedin' not in session or not session['loggedin']:
        return redirect(url_for('dept_login'))
    dept_branch = session['dept_branch']
    mysql_connection = mysql.connector.connect(**db_config)
    cursor = mysql_connection.cursor()
    ##same
    cursor.execute('SELECT staff_name FROM faculty_db WHERE staff_branch = %s', (dept_branch,))
    staff_names = cursor.fetchall()

    
    cursor.execute('SELECT class_time FROM class_time WHERE class_branch = %s', (dept_branch,))
    class_times = cursor.fetchall()
    cursor.close()
    
    mysql_connection.close()
    return render_template('add_subject.html', staff_names=staff_names, class_times=class_times)

#delete subject data nav
@app.route("/delete_subject_nav", methods=["GET", "POST"])
def delete_subject_nav():
    if 'loggedin' not in session or not session['loggedin']:
        return redirect(url_for('dept_login'))
    dept_branch = session['dept_branch']
    mysql_connection = mysql.connector.connect(**db_config)
    cursor = mysql_connection.cursor()
    ##same
    cursor.execute('SELECT subject_code FROM subject_log WHERE branch_allot = %s', (dept_branch,))
    subject_codes = cursor.fetchall()
    cursor.close()
    
    mysql_connection.close()
    return render_template('delete_subject_allotment.html', subject_codes=subject_codes)

#delete staff data nav
@app.route("/delete_staff_nav", methods=["GET", "POST"])
def delete_staff_nav():
    if 'loggedin' not in session or not session['loggedin']:
        return redirect(url_for('dept_login'))
    dept_branch = session['dept_branch']
    mysql_connection = mysql.connector.connect(**db_config)
    cursor = mysql_connection.cursor()
    ##same
    cursor.execute('SELECT staff_name FROM faculty_db WHERE staff_branch = %s', (dept_branch,))
    staff_names = cursor.fetchall()
    cursor.close()
    
    mysql_connection.close()
    return render_template('delete_staff.html', staff_names=staff_names)



#attendance data view
@app.route("/attendance_data_view", methods=["GET", "POST"])
def attendance_data_view():
    try:
        # Connect to MySQL database
        db = mysql.connector.connect(**db_config)
        cursor = db.cursor()

        # Fetch start_time and end_time from subject_log table
        cursor.execute("SELECT start_time, end_time FROM subject_log")
        result = cursor.fetchone()

        if not result:
            return "Error: No data found in subject_log.", 500

        start_time = datetime.strptime(result[0], "%H:%M:%S").time()
        end_time = datetime.strptime(result[1], "%H:%M:%S").time()

        # Fetch data from attendance_log within the specified time range
        cursor.execute("SELECT usn, time FROM attendance_log")
        attendance_data = cursor.fetchall()

        # Filter the data based on the time range
        filtered_data = [row for row in attendance_data if start_time <= datetime.strptime(row[1], "%H:%M:%S").time() <= end_time]

        # Count the repetitions of each USN within a 3-month duration
        usn_counts = Counter([row[0] for row in filtered_data])

        # Calculate the count * 10 for each USN
        usn_scores = {usn: count * 10 for usn, count in usn_counts.items()}

        # Prepare a list of dictionaries containing individual student data
        student_dbs = []
        for usn, score in usn_scores.items():
            # Fetch additional student details from the database based on USN
            cursor.execute("SELECT name, branch, sem FROM student_db WHERE usn = %s", (usn,))
            student_details = cursor.fetchone()
            if student_details:
                name, branch, sem = student_details
                student_dbs.append({"usn": usn, "name": name, "branch": branch, "sem": sem, "attendance": score})

        # Render the HTML page with the calculated data
        return render_template("attendance_data_view.html", student_dbs=student_dbs)

    except Exception as e:
        print(f"An error occurred: {e}")
        return "Error occurred while processing the request.", 500

    finally:
        # Close database connection
        cursor.close()
        db.close()


#staff view assign to subject adding
@app.route("/staff_allotment", methods=["GET", "POST"])
# Path to the root folder for saving image
def staff_allotment():
    if request.method == 'POST':
        # Retrieve data from the form
        selected_subject_code = request.form.get('selected_subject_code')
        selected_staff_name = request.form.get('selected_staff_name')
        selected_branch = request.form.get('selected_branch')
        selected_sem = request.form.get('selected_sem')
        selected_start_time = request.form.get('selected_start_time')
        # Define the regular expression patterns for USN and name validation
        selected_subject_code_pattern = r"\d{2}[A-Za-z]{2,3}\d{2,3}"
        
        # Validate the USN and name format
        if not re.match( selected_subject_code_pattern,selected_subject_code):
            flash("Invalid subject code format. Please enter a valid subject code format")
            return render_template('add_subject.html')

        # Check if the subject code already exists in the subject_log table
        cursor = db.cursor()
        cursor.execute("SELECT * FROM subject_log WHERE subject_code = %s", (selected_subject_code,))
        existing_subject = cursor.fetchone()
        cursor.close()

        if existing_subject:
            # Subject code already exists, send a message to the HTML page
            flash("Subject code already exists in the subject log.")
            return render_template('add_subject.html')

                # Add 45 minutes to the selected_start_time
        try:
            selected_start_time_obj = datetime.strptime(selected_start_time, '%H:%M:%S')
            added_time_obj = selected_start_time_obj + timedelta(minutes=45)
            added_time = added_time_obj.strftime('%H:%M:%S')
        except ValueError:
            flash("Invalid start time format")
            return render_template('add_subject.html')

        cursor = db.cursor()
        cursor.execute("INSERT INTO subject_log (subject_code, subject_faculty, branch_allot, sem_allot, start_time, end_time) VALUES (%s, %s, %s, %s, %s, %s)", (selected_subject_code, selected_staff_name, selected_branch, selected_sem, selected_start_time, added_time))
        db.commit()
        cursor.close()

        # Return a response after successful database operation
        return render_template('subject_view.html')

    # Return a response for GET request or other cases
    return render_template('staff_allotment_form.html')

    

@app.route("/delete_subject_data", methods=['POST'])
def delete_subject_data():
    if 'loggedin' not in session or not session['loggedin']:
        return redirect(url_for('dept_login'))

    selected_subject_code = request.form['selected_subject_code']

    mysql_connection = mysql.connector.connect(**db_config)
    cursor = mysql_connection.cursor()

    try:
        cursor.execute('DELETE FROM subject_log WHERE subject_code = %s', (selected_subject_code,))
        
        mysql_connection.commit()

        cursor.close()
        mysql_connection.close()

        return redirect(url_for('subject_view'))

    except Exception as e:
        mysql_connection.rollback()
        return render_template('error.html', error=str(e))



#thigsgshhsdgws
@app.route("/tryy")
def tryy():
    return render_template("try.html")


import mysql.connector
# Define a function to fetch start and end times from the database
def fetch_start_end_times():

    # Connect to the MySQL database using a context manager
    with mysql.connector.connect(**db_config) as conn:
        with conn.cursor() as cursor:
            # Define the query to retrieve start and end times
            query = "SELECT start_time, end_time FROM subject_log"

            # Execute the query
            cursor.execute(query)

            # Fetch the first row
            row = cursor.fetchone()

            if row:
                start_time_str, end_time_str = row
                
                # Convert string times to datetime objects
                current_date = datetime.now().date()
                start_time = datetime.combine(current_date, datetime.strptime(start_time_str, '%H:%M:%S').time())
                end_time = datetime.combine(current_date, datetime.strptime(end_time_str, '%H:%M:%S').time())

                return start_time, end_time

    return None, None

# Function to fetch start and end times from the database
def fetch_start_end_times():
    # Connect to MySQL database
    conn = mysql.connector.connect(
        host="localhost",
        user="root",
        password="",
        database="face_rec_db"
    )
    cursor = conn.cursor()

    try:
        # Fetch start and end times from subject_log
        cursor.execute("SELECT start_time, end_time FROM subject_log")
        result = cursor.fetchone()  # Fetch one result

        # Process the result
        if result:
            # Convert start and end times to datetime.time objects
            start_time = datetime.strptime(result[0], "%H:%M:%S").time()
            end_time = datetime.strptime(result[1], "%H:%M:%S").time()
            return start_time, end_time
        else:
            print("No data found in subject_log.")
            return None, None
    except mysql.connector.Error as e:
        print(f"Database error: {e}")
        return None, None
    finally:
        # Close the cursor and database connection
        cursor.close()
        conn.close()


# Assuming db_config is properly defined

@app.route("/run_prg", methods=['POST'])
def prg_run():
    # Connect to MySQL database
    db = mysql.connector.connect(**db_config)
    cursor = db.cursor()

    try:
        # Fetch start and end times from the database
        cursor.execute("SELECT start_time, end_time FROM subject_log")
        result = cursor.fetchone()  # Fetch one result

        # Process the result and check if start and end times were fetched
        if not result:
            print("No data found in subject_log.")
            return "Error: No data found in subject_log.", 500

        # Convert start and end times to datetime.time objects
        start_time = datetime.strptime(result[0], "%H:%M:%S").time()
        end_time = datetime.strptime(result[1], "%H:%M:%S").time()

        # Open video capture
        video_capture = cv2.VideoCapture(0)

        # Check if video capture is opened
        if not video_capture.isOpened():
            print("Failed to open video capture device.")
            return "Error: Failed to open video capture device.", 500

        # Load known faces from folder
        folder_path = "photos/"
        known_face_encodings = []
        known_face_names = []

        for filename in os.listdir(folder_path):
            if filename.endswith((".jpg", ".jpeg", ".png")):
                image_path = os.path.join(folder_path, filename)
                image = face_recognition.load_image_file(image_path)

                # Get face encodings
                encodings = face_recognition.face_encodings(image)

                # Check if any face encodings were found
                if encodings:
                    encoding = encodings[0]
                    # Remove file extension from filename to use as the name
                    name = os.path.splitext(filename)[0]
                    known_face_encodings.append(encoding)
                    known_face_names.append(name)
                else:
                    print(f"No faces found in image: {filename}")

        # Define recognition and rest periods
        recognition_time = 5 * 60  # Recognize for 5 minutes (300 seconds)
        rest_time = 5 * 60  # Rest for 5 minutes (300 seconds)
        total_time = 4 * (recognition_time + rest_time)  # Total period of 4 hours

        # Define the current date
        current_date = datetime.now().strftime("%Y-%m-%d")

        # Initialize a set to store the names of recognized individuals during each recognition period
        recognized_names_during_period = set()

        # Main loop for video capture
        while True:
            # Get the current time
            current_time = datetime.now()

            # Check if the current time is within the desired time frame
            if start_time <= current_time.time() <= end_time:
                # Calculate the elapsed time during this cycle
                cycle_start_time = datetime.now()
                elapsed_time = 0

                while elapsed_time < total_time:
                    # Calculate the elapsed time
                    elapsed_time = (datetime.now() - cycle_start_time).total_seconds()

                    # Check if we are in the recognition period
                    if elapsed_time % (recognition_time + rest_time) < recognition_time:
                        # Recognition period
                        while (datetime.now() - cycle_start_time).total_seconds() % (recognition_time + rest_time) < recognition_time:
                            # Read frame from video capture
                            ret, frame = video_capture.read()
                            if not ret:
                                print("Failed to capture frame from camera.")
                                break

                            # Resize frame
                            small_frame = cv2.resize(frame, (0, 0), fx=0.25, fy=0.25)

                            # Convert frame to RGB color space
                            rgb_small_frame = cv2.cvtColor(small_frame, cv2.COLOR_BGR2RGB)

                            # Recognize faces
                            face_locations = face_recognition.face_locations(rgb_small_frame)
                            face_encodings = face_recognition.face_encodings(rgb_small_frame, face_locations)

                            for face_encoding in face_encodings:
                                # Compare faces and find the best match
                                matches = face_recognition.compare_faces(known_face_encodings, face_encoding)
                                face_distance = face_recognition.face_distance(known_face_encodings, face_encoding)
                                best_match_index = np.argmin(face_distance)

                                if matches[best_match_index]:
                                    # Get the name of the best match
                                    name = known_face_names[best_match_index]

                                    # Display text on the frame
                                    font = cv2.FONT_HERSHEY_SIMPLEX
                                    bottom_left_corner_of_text = (10, 100)
                                    font_scale = 1.5
                                    font_color = (255, 0, 0)
                                    thickness = 3
                                    line_type = 2
                                    cv2.putText(frame, f"{name} Present", bottom_left_corner_of_text, font, font_scale, font_color, thickness, line_type)

                                    # Add the recognized person's name to the set
                                    recognized_names_during_period.add(name)

                            # Display the frame
                            cv2.imshow("Camera", frame)

                            # Quit loop if 'q' key is pressed
                            if cv2.waitKey(1) & 0xFF == ord("q"):
                                break

                        # Recognition period ends
                        print("Recognition period ended.")

                        # Record attendance for recognized individuals
                        for name in recognized_names_during_period:
                            current_time = datetime.now().strftime("%H:%M:%S")
                            cursor.execute(
                                "INSERT INTO attendance_log (usn, time, log_date) VALUES (%s, %s, %s)",
                                (name, current_time, current_date)
                            )
                            db.commit()

                        # Clear the set for the next recognition period
                        recognized_names_during_period.clear()

                        # Rest period begins
                        print("Rest period, no recognition.")
                        # Sleep for the duration of the rest period
                        time.sleep(rest_time)

                # Sleep until the next recognition time
                remaining_time = (start_time + timedelta(days=1) - current_time).total_seconds()
                if remaining_time > 0:
                    time.sleep(remaining_time)
            else:
                # Sleep until the recognition period starts
                remaining_time = (start_time - current_time.time()).total_seconds()
                if remaining_time > 0:
                    time.sleep(remaining_time)

    except Exception as e:
        print(f"An error occurred: {e}")

    finally:
        # Cleanup and close resources
        if 'video_capture' in locals():
            video_capture.release()
        cv2.destroyAllWindows()
        cursor.close()
        db.close()

    return render_template("attendance.html")
    
#run the flask server
if __name__ == "__main__":
    app.run(host="0.0.0.0", debug=True)
