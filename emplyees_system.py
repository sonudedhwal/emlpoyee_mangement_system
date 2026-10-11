"""
Employee Management System - single file
Run:  streamlit run employee_system.py
Needs: pip install streamlit pandas scikit-learn mysql-connector-python
XAMPP MySQL must be running (default user root, empty password).
"""

import datetime

import mysql.connector
import pandas as pd
import streamlit as st
from sklearn.linear_model import LinearRegression

# ==========================================
# DATABASE CONFIGURATION (XAMPP defaults)
# ==========================================

DB_CONFIG = {
    "host": "localhost",
    "user": "root",
    "password": "",
    "database": "employee_management",
}


def _server_connection():
    """Connection without selecting a database (used to create it)."""
    return mysql.connector.connect(
        host=DB_CONFIG["host"],
        user=DB_CONFIG["user"],
        password=DB_CONFIG["password"],
    )


def get_connection():
    return mysql.connector.connect(**DB_CONFIG)


def init_db():
    """Create the database and all tables if they do not exist."""
    conn = _server_connection()
    cur = conn.cursor()
    cur.execute("CREATE DATABASE IF NOT EXISTS employee_management")
    conn.commit()
    cur.close()
    conn.close()

    conn = get_connection()
    cur = conn.cursor()

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS employees (
            id INT AUTO_INCREMENT PRIMARY KEY,
            name VARCHAR(100) NOT NULL,
            email VARCHAR(100),
            phone VARCHAR(20),
            department VARCHAR(50),
            designation VARCHAR(50),
            gender VARCHAR(10),
            age INT,
            join_date DATE,
            salary DECIMAL(12,2),
            status VARCHAR(20) DEFAULT 'Active',
            attendance DECIMAL(5,2) DEFAULT 0,
            avg_work_hours DECIMAL(5,2) DEFAULT 0,
            tasks_completion DECIMAL(5,2) DEFAULT 0,
            last_rating DECIMAL(5,2) DEFAULT 0,
            final_score DECIMAL(5,2) NULL,
            predicted_score DECIMAL(5,2) NULL
        )
        """
    )

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS daily_attendance (
            id INT AUTO_INCREMENT PRIMARY KEY,
            employee_id INT NOT NULL,
            work_date DATE NOT NULL,
            check_in TIME,
            check_out TIME,
            status VARCHAR(20) DEFAULT 'Present',
            UNIQUE KEY uniq_emp_day (employee_id, work_date),
            FOREIGN KEY (employee_id) REFERENCES employees(id) ON DELETE CASCADE
        )
        """
    )

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS daily_tasks (
            id INT AUTO_INCREMENT PRIMARY KEY,
            employee_id INT NOT NULL,
            task_date DATE NOT NULL,
            title VARCHAR(200) NOT NULL,
            description TEXT,
            priority VARCHAR(10) DEFAULT 'Medium',
            status VARCHAR(20) DEFAULT 'Pending',
            hours_spent DECIMAL(5,2) DEFAULT 0,
            FOREIGN KEY (employee_id) REFERENCES employees(id) ON DELETE CASCADE
        )
        """
    )

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS leave_requests (
            id INT AUTO_INCREMENT PRIMARY KEY,
            employee_id INT NOT NULL,
            leave_type VARCHAR(30),
            start_date DATE,
            end_date DATE,
            reason TEXT,
            status VARCHAR(20) DEFAULT 'Pending',
            FOREIGN KEY (employee_id) REFERENCES employees(id) ON DELETE CASCADE
        )
        """
    )

    conn.commit()
    cur.close()
    conn.close()


def _query_df(sql, params=None):
    conn = get_connection()
    try:
        return pd.read_sql(sql, conn, params=params)
    finally:
        conn.close()


def _execute(sql, params=None):
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(sql, params or ())
        conn.commit()
        cur.close()
    finally:
        conn.close()


# ==========================================
# EMPLOYEES
# ==========================================

def add_employee(name, email, phone, department, designation, gender, age,
                 join_date, salary):
    _execute(
        """
        INSERT INTO employees
        (name, email, phone, department, designation, gender, age, join_date, salary)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
        """,
        (name, email, phone, department, designation, gender, age,
         join_date, salary),
    )


def get_employees():
    return _query_df("SELECT * FROM employees ORDER BY id")


def search_employees(name):
    df = _query_df(
        "SELECT * FROM employees WHERE name LIKE %s OR department LIKE %s",
        (f"%{name}%", f"%{name}%"),
    )
    return df.to_dict("records")


def delete_employee(employee_id):
    _execute("DELETE FROM employees WHERE id = %s", (int(employee_id),))


def update_status(employee_id, status):
    _execute("UPDATE employees SET status = %s WHERE id = %s",
             (status, int(employee_id)))


def update_prediction(employee_id, prediction):
    _execute("UPDATE employees SET predicted_score = %s WHERE id = %s",
             (float(prediction), int(employee_id)))


def update_final_score(employee_id, score):
    _execute("UPDATE employees SET final_score = %s WHERE id = %s",
             (float(score), int(employee_id)))


# ==========================================
# DAILY ATTENDANCE
# ==========================================

def mark_attendance(employee_id, work_date, check_in, check_out, status):
    _execute(
        """
        INSERT INTO daily_attendance (employee_id, work_date, check_in, check_out, status)
        VALUES (%s,%s,%s,%s,%s)
        ON DUPLICATE KEY UPDATE
            check_in = VALUES(check_in),
            check_out = VALUES(check_out),
            status = VALUES(status)
        """,
        (int(employee_id), work_date, check_in, check_out, status),
    )
    refresh_employee_metrics(employee_id)


def get_attendance(work_date=None):
    if work_date:
        return _query_df(
            """
            SELECT a.id, e.name, e.department, a.work_date,
                   a.check_in, a.check_out, a.status
            FROM daily_attendance a
            JOIN employees e ON e.id = a.employee_id
            WHERE a.work_date = %s
            ORDER BY e.name
            """,
            (work_date,),
        )
    return _query_df(
        """
        SELECT a.id, e.name, e.department, a.work_date,
               a.check_in, a.check_out, a.status
        FROM daily_attendance a
        JOIN employees e ON e.id = a.employee_id
        ORDER BY a.work_date DESC, e.name
        """
    )


# ==========================================
# DAILY TASKS
# ==========================================

def add_task(employee_id, task_date, title, description, priority, hours_spent):
    _execute(
        """
        INSERT INTO daily_tasks
        (employee_id, task_date, title, description, priority, hours_spent)
        VALUES (%s,%s,%s,%s,%s,%s)
        """,
        (int(employee_id), task_date, title, description, priority,
         float(hours_spent)),
    )
    refresh_employee_metrics(employee_id)


def get_tasks(employee_id=None, task_date=None):
    sql = """
        SELECT t.id, e.name, t.task_date, t.title, t.description,
               t.priority, t.status, t.hours_spent
        FROM daily_tasks t
        JOIN employees e ON e.id = t.employee_id
        WHERE 1=1
    """
    params = []
    if employee_id:
        sql += " AND t.employee_id = %s"
        params.append(int(employee_id))
    if task_date:
        sql += " AND t.task_date = %s"
        params.append(task_date)
    sql += " ORDER BY t.task_date DESC, t.id DESC"
    return _query_df(sql, tuple(params))


def update_task_status(task_id, status):
    _execute("UPDATE daily_tasks SET status = %s WHERE id = %s",
             (status, int(task_id)))
    df = _query_df("SELECT employee_id FROM daily_tasks WHERE id = %s",
                   (int(task_id),))
    if len(df) > 0:
        refresh_employee_metrics(int(df.iloc[0]["employee_id"]))


# ==========================================
# LEAVE REQUESTS
# ==========================================

def add_leave(employee_id, leave_type, start_date, end_date, reason):
    _execute(
        """
        INSERT INTO leave_requests
        (employee_id, leave_type, start_date, end_date, reason)
        VALUES (%s,%s,%s,%s,%s)
        """,
        (int(employee_id), leave_type, start_date, end_date, reason),
    )


def get_leaves():
    return _query_df(
        """
        SELECT l.id, e.name, l.leave_type, l.start_date, l.end_date,
               l.reason, l.status
        FROM leave_requests l
        JOIN employees e ON e.id = l.employee_id
        ORDER BY l.id DESC
        """
    )


def update_leave_status(leave_id, status):
    _execute("UPDATE leave_requests SET status = %s WHERE id = %s",
             (status, int(leave_id)))


# ==========================================
# AUTO-CALCULATED METRICS (used by ML)
# ==========================================

def refresh_employee_metrics(employee_id):
    """Recalculate attendance %, avg work hours and task completion %."""
    employee_id = int(employee_id)

    att = _query_df(
        """
        SELECT
            COUNT(*) AS total_days,
            SUM(CASE WHEN status IN ('Present','Work From Home','Half Day') THEN 1 ELSE 0 END) AS present_days
        FROM daily_attendance WHERE employee_id = %s
        """,
        (employee_id,),
    )
    total_days = int(att.iloc[0]["total_days"] or 0)
    present_days = int(att.iloc[0]["present_days"] or 0)
    attendance_pct = (present_days / total_days * 100) if total_days else 0

    hrs = _query_df(
        """
        SELECT AVG(TIME_TO_SEC(TIMEDIFF(check_out, check_in)) / 3600) AS avg_hours
        FROM daily_attendance
        WHERE employee_id = %s AND check_in IS NOT NULL AND check_out IS NOT NULL
        """,
        (employee_id,),
    )
    avg_hours = float(hrs.iloc[0]["avg_hours"] or 0)

    tasks = _query_df(
        """
        SELECT COUNT(*) AS total,
               SUM(CASE WHEN status = 'Completed' THEN 1 ELSE 0 END) AS done
        FROM daily_tasks WHERE employee_id = %s
        """,
        (employee_id,),
    )
    total_tasks = int(tasks.iloc[0]["total"] or 0)
    done_tasks = int(tasks.iloc[0]["done"] or 0)
    completion_pct = (done_tasks / total_tasks * 100) if total_tasks else 0

    _execute(
        """
        UPDATE employees
        SET attendance = %s, avg_work_hours = %s, tasks_completion = %s
        WHERE id = %s
        """,
        (round(attendance_pct, 2), round(max(avg_hours, 0), 2),
         round(completion_pct, 2), employee_id),
    )


# ==========================================
# PAGE CONFIGURATION
# ==========================================

st.set_page_config(
    page_title="Employee Management System",
    page_icon="🏢",
    layout="wide",
)

st.title("🏢 Employee Management System")
st.write("Python + Streamlit + MySQL + XAMPP + AI/ML")

# Create database and tables automatically on first run
try:
    init_db()
except Exception as e:
    st.error(f"Could not connect to MySQL. Is XAMPP running? Error: {e}")
    st.stop()

FEATURES = [
    "attendance",
    "avg_work_hours",
    "tasks_completion",
    "last_rating",
]

# ==========================================
# SIDEBAR
# ==========================================

menu = st.sidebar.selectbox(
    "Select Module",
    [
        "Dashboard",
        "Add Employee",
        "View Employees",
        "Search Employee",
        "Daily Attendance",
        "Daily Tasks",
        "Leave Management",
        "Update Status / Delete",
        "AI/ML Performance Prediction",
    ],
)


def employee_picker(label="Select Employee", key=None):
    """Dropdown of employees, returns (id, name) or (None, None)."""
    df = get_employees()
    if len(df) == 0:
        st.info("No employees yet. Add an employee first.")
        return None, None
    options = {f"{row['id']} - {row['name']}": row["id"] for _, row in df.iterrows()}
    choice = st.selectbox(label, list(options.keys()), key=key)
    return int(options[choice]), choice


# ==========================================
# DASHBOARD
# ==========================================

if menu == "Dashboard":

    st.header("📊 Employee Dashboard")

    try:
        df = get_employees()
        today = datetime.date.today()

        att_today = get_attendance(today)
        present_today = (
            len(att_today[att_today["status"].isin(["Present", "Work From Home", "Half Day"])])
            if len(att_today) > 0 else 0
        )

        tasks_today = get_tasks(task_date=today)
        pending_tasks = (
            len(tasks_today[tasks_today["status"] != "Completed"])
            if len(tasks_today) > 0 else 0
        )

        leaves = get_leaves()
        pending_leaves = (
            len(leaves[leaves["status"] == "Pending"]) if len(leaves) > 0 else 0
        )

        c1, c2, c3, c4, c5 = st.columns(5)
        c1.metric("Total Employees", len(df))
        c2.metric("Present Today", present_today)
        c3.metric("Pending Tasks Today", pending_tasks)
        c4.metric("Pending Leaves", pending_leaves)
        c5.metric(
            "Avg Task Completion",
            f"{df['tasks_completion'].astype(float).mean():.1f}%" if len(df) > 0 else "0%",
        )

        st.subheader("Today's Attendance")
        if len(att_today) > 0:
            st.dataframe(att_today, use_container_width=True)
        else:
            st.info("No attendance marked today.")

        st.subheader("Today's Tasks")
        if len(tasks_today) > 0:
            st.dataframe(tasks_today, use_container_width=True)
        else:
            st.info("No tasks added today.")

        if len(df) > 0:
            st.subheader("Employees by Department")
            st.bar_chart(df["department"].value_counts())

    except Exception as e:
        st.error(f"Database Error: {e}")

# ==========================================
# ADD EMPLOYEE
# ==========================================

elif menu == "Add Employee":

    st.header("➕ Add New Employee")

    name = st.text_input("Employee Name")
    email = st.text_input("Email")
    phone = st.text_input("Phone")
    department = st.selectbox(
        "Department",
        ["HR", "IT", "Finance", "Sales", "Marketing", "Operations", "Support"],
    )
    designation = st.text_input("Designation")
    gender = st.selectbox("Gender", ["Male", "Female", "Other"])
    age = st.number_input("Age", min_value=18, max_value=70, value=25)
    join_date = st.date_input("Join Date", value=datetime.date.today())
    salary = st.number_input("Monthly Salary", min_value=0.0, value=20000.0, step=500.0)

    if st.button("Save Employee"):
        if name.strip() == "":
            st.warning("Please enter employee name.")
        else:
            try:
                add_employee(
                    name, email, phone, department, designation,
                    gender, age, join_date, salary,
                )
                st.success("Employee added successfully!")
            except Exception as e:
                st.error(f"Database Error: {e}")

# ==========================================
# VIEW EMPLOYEES
# ==========================================

elif menu == "View Employees":

    st.header("👥 All Employees")

    try:
        df = get_employees()
        if len(df) == 0:
            st.info("No employees found.")
        else:
            st.dataframe(df, use_container_width=True)
            st.download_button(
                "Download Employee Data",
                df.to_csv(index=False),
                "employees.csv",
                "text/csv",
            )
    except Exception as e:
        st.error(f"Database Error: {e}")

# ==========================================
# SEARCH EMPLOYEE
# ==========================================

elif menu == "Search Employee":

    st.header("🔎 Search Employee")

    keyword = st.text_input("Enter Employee Name or Department")

    if st.button("Search"):
        try:
            results = search_employees(keyword)
            if results:
                st.dataframe(pd.DataFrame(results), use_container_width=True)
            else:
                st.warning("Employee not found.")
        except Exception as e:
            st.error(f"Database Error: {e}")

# ==========================================
# DAILY ATTENDANCE
# ==========================================

elif menu == "Daily Attendance":

    st.header("🕘 Daily Attendance")

    tab1, tab2 = st.tabs(["Mark Attendance", "Attendance Records"])

    with tab1:
        emp_id, _ = employee_picker(key="att_emp")
        if emp_id:
            work_date = st.date_input("Date", value=datetime.date.today(), key="att_date")
            status = st.selectbox(
                "Status",
                ["Present", "Absent", "Work From Home", "Half Day", "On Leave"],
            )
            check_in = st.time_input("Check-in Time", value=datetime.time(9, 0))
            check_out = st.time_input("Check-out Time", value=datetime.time(18, 0))

            if st.button("Save Attendance"):
                try:
                    if status in ("Absent", "On Leave"):
                        check_in, check_out = None, None
                    mark_attendance(emp_id, work_date, check_in, check_out, status)
                    st.success("Attendance saved.")
                except Exception as e:
                    st.error(f"Database Error: {e}")

    with tab2:
        filter_date = st.date_input("Filter by date", value=datetime.date.today(), key="att_filter")
        show_all = st.checkbox("Show all dates")
        try:
            records = get_attendance(None if show_all else filter_date)
            if len(records) == 0:
                st.info("No attendance records.")
            else:
                st.dataframe(records, use_container_width=True)
                st.download_button(
                    "Download Attendance",
                    records.to_csv(index=False),
                    "attendance.csv",
                    "text/csv",
                )
        except Exception as e:
            st.error(f"Database Error: {e}")

# ==========================================
# DAILY TASKS
# ==========================================

elif menu == "Daily Tasks":

    st.header("📝 Daily Tasks / Work Log")

    tab1, tab2, tab3 = st.tabs(["Assign / Log Task", "View Tasks", "Update Task Status"])

    with tab1:
        emp_id, _ = employee_picker(key="task_emp")
        if emp_id:
            task_date = st.date_input("Task Date", value=datetime.date.today(), key="task_date")
            title = st.text_input("Task Title")
            description = st.text_area("Description")
            priority = st.selectbox("Priority", ["Low", "Medium", "High"], index=1)
            hours_spent = st.number_input("Hours Spent", 0.0, 24.0, 1.0, step=0.5)

            if st.button("Save Task"):
                if title.strip() == "":
                    st.warning("Please enter a task title.")
                else:
                    try:
                        add_task(emp_id, task_date, title, description, priority, hours_spent)
                        st.success("Task saved.")
                    except Exception as e:
                        st.error(f"Database Error: {e}")

    with tab2:
        try:
            tasks = get_tasks()
            if len(tasks) == 0:
                st.info("No tasks found.")
            else:
                st.dataframe(tasks, use_container_width=True)
                st.download_button(
                    "Download Tasks",
                    tasks.to_csv(index=False),
                    "tasks.csv",
                    "text/csv",
                )
        except Exception as e:
            st.error(f"Database Error: {e}")

    with tab3:
        task_id = st.number_input("Task ID", min_value=1, step=1)
        new_status = st.selectbox("New Status", ["Pending", "In Progress", "Completed"])
        if st.button("Update Task"):
            try:
                update_task_status(task_id, new_status)
                st.success("Task status updated.")
            except Exception as e:
                st.error(f"Database Error: {e}")

# ==========================================
# LEAVE MANAGEMENT
# ==========================================

elif menu == "Leave Management":

    st.header("🌴 Leave Management")

    tab1, tab2 = st.tabs(["Apply Leave", "Approve / Reject"])

    with tab1:
        emp_id, _ = employee_picker(key="leave_emp")
        if emp_id:
            leave_type = st.selectbox("Leave Type", ["Casual", "Sick", "Paid", "Unpaid"])
            start_date = st.date_input("Start Date", value=datetime.date.today(), key="l_start")
            end_date = st.date_input("End Date", value=datetime.date.today(), key="l_end")
            reason = st.text_area("Reason")

            if st.button("Submit Leave"):
                if end_date < start_date:
                    st.warning("End date cannot be before start date.")
                else:
                    try:
                        add_leave(emp_id, leave_type, start_date, end_date, reason)
                        st.success("Leave request submitted.")
                    except Exception as e:
                        st.error(f"Database Error: {e}")

    with tab2:
        try:
            leaves = get_leaves()
            if len(leaves) == 0:
                st.info("No leave requests.")
            else:
                st.dataframe(leaves, use_container_width=True)
                leave_id = st.number_input("Leave ID", min_value=1, step=1)
                decision = st.selectbox("Decision", ["Approved", "Rejected", "Pending"])
                if st.button("Update Leave"):
                    update_leave_status(leave_id, decision)
                    st.success("Leave status updated.")
        except Exception as e:
            st.error(f"Database Error: {e}")

# ==========================================
# UPDATE STATUS / DELETE
# ==========================================

elif menu == "Update Status / Delete":

    st.header("⚙️ Update Status / Delete Employee")

    emp_id, _ = employee_picker(key="manage_emp")
    if emp_id:
        new_status = st.selectbox("Employee Status", ["Active", "On Leave", "Resigned", "Terminated"])
        if st.button("Update Status"):
            try:
                update_status(emp_id, new_status)
                st.success("Status updated.")
            except Exception as e:
                st.error(f"Database Error: {e}")

        st.divider()
        st.warning("Deleting an employee also deletes their attendance, tasks and leaves.")
        confirm = st.checkbox("I confirm I want to delete this employee")
        if st.button("Delete Employee"):
            if not confirm:
                st.warning("Please tick the confirmation box first.")
            else:
                try:
                    delete_employee(emp_id)
                    st.success("Employee deleted successfully.")
                except Exception as e:
                    st.error(f"Database Error: {e}")

# ==========================================
# AI / ML PERFORMANCE PREDICTION
# ==========================================

elif menu == "AI/ML Performance Prediction":

    st.header("🤖 AI / ML Employee Performance Prediction")
    st.write(
        "Linear Regression predicts an employee's performance score (0-100) "
        "from attendance, daily work hours, task completion and last rating."
    )

    try:
        df = get_employees()

        for col in FEATURES + ["final_score"]:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")

        with st.expander("Record actual performance score (used for training)"):
            emp_id, _ = employee_picker("Employee", key="score_emp")
            if emp_id:
                actual = st.number_input("Actual Performance Score", 0.0, 100.0, 70.0)
                if st.button("Save Actual Score"):
                    update_final_score(emp_id, actual)
                    st.success("Actual score saved.")
                    st.rerun()

        train_data = df.dropna(subset=FEATURES + ["final_score"])

        if len(train_data) < 3:
            st.info(
                "Enter actual performance scores for at least 3 employees "
                "to train the supervised ML model."
            )
        else:
            model = LinearRegression()
            model.fit(train_data[FEATURES], train_data["final_score"])
            st.success(f"ML model trained on {len(train_data)} employees.")

            st.subheader("Predict Employee Performance")

            emp_id, _ = employee_picker("Employee to predict", key="pred_emp")

            if emp_id:
                if st.button("Auto-fill from daily records"):
                    refresh_employee_metrics(emp_id)
                    st.rerun()

                row = df[df["id"] == emp_id].iloc[0]

                attendance = st.number_input("Attendance (%)", 0.0, 100.0,
                                             float(row["attendance"] or 0))
                avg_hours = st.number_input("Avg Work Hours / Day", 0.0, 24.0,
                                            float(row["avg_work_hours"] or 0))
                completion = st.number_input("Task Completion (%)", 0.0, 100.0,
                                             float(row["tasks_completion"] or 0))
                rating = st.number_input("Last Rating", 0.0, 100.0,
                                         float(row["last_rating"] or 0))

                if st.button("Predict Performance"):
                    input_data = pd.DataFrame(
                        [[attendance, avg_hours, completion, rating]],
                        columns=FEATURES,
                    )
                    prediction = float(model.predict(input_data)[0])
                    prediction = max(0, min(100, prediction))

                    st.success(f"Predicted Performance Score: {prediction:.2f}")

                    if prediction >= 80:
                        st.info("Rating: Excellent")
                    elif prediction >= 60:
                        st.info("Rating: Good")
                    elif prediction >= 40:
                        st.warning("Rating: Needs Improvement")
                    else:
                        st.error("Rating: At Risk")

                    update_prediction(emp_id, prediction)
                    st.info("Prediction saved to MySQL.")

    except Exception as e:
        st.error(f"ML / Database Error: {e}")