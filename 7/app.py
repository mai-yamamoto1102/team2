
import pymysql
pymysql.install_as_MySQLdb()
from flask import Flask, request, jsonify, render_template, session, redirect, url_for
from flask_mysqldb import MySQL
import datetime
import json
from functools import wraps
from datetime import timedelta
import os


app = Flask(__name__)

# MySQL配置
app.config['DB_HOST'] = os.environ.get('DB_HOST')
app.config['DB_USER'] = os.environ.get('DB_USER')
app.config['DB_PASSWORD'] = os.environ.get('DB_PASSWORD')
app.config['DB_NAME'] = os.environ.get('DB_NAME')
app.config['MYSQL_CURSORCLASS'] = 'DictCursor'


# 初始化MySQL
mysql = MySQL(app)

# 设置Session密钥
app.secret_key = 'attendance_secret_key'
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(hours=24)  # 设置24小时

# 添加时间格式化辅助函数
def format_time_value(time_value):
    """
    Convert time value to string format, handling both timedelta and time objects
    """
    if not time_value:
        return None
    
    if isinstance(time_value, str):
        return time_value
    elif isinstance(time_value, datetime.time):
        return time_value.strftime('%H:%M:%S')
    elif isinstance(time_value, datetime.timedelta):
        # Convert timedelta to time format
        total_seconds = int(time_value.total_seconds())
        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        seconds = total_seconds % 60
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
    else:
        return None

# 登录验证装饰器
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'employee_id' not in session:
            return redirect(url_for('login_page'))
        return f(*args, **kwargs)
    return decorated_function

# 角色验证装饰器
def role_required(roles):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if 'role' not in session or session['role'] not in roles:
                return jsonify(success=False, message="権限がありません"), 403
            return f(*args, **kwargs)
        return decorated_function
    return decorator

# 首页 - 登录页面
@app.route('/')
def login_page():
    if 'employee_id' in session:
        if session['role'] == 'employee':
            return redirect(url_for('employee_page'))
        elif session['role'] == 'manager':
            return redirect(url_for('manager_page'))
        elif session['role'] == 'soumu':
            return redirect(url_for('soumu_page'))
    return render_template('login.html')


# 登录API
@app.route('/api/login', methods=['POST'])
def login():
    data = request.get_json()
    employee_id = data.get('employee_id')
    password = data.get('password')

    # 数据库连接
    cur = mysql.connection.cursor()
    # 查询匹配的用户
    sql = """
    SELECT employee_id, CONCAT(last_name, ' ', first_name) as full_name, role 
    FROM employees 
    WHERE employee_id = %s AND password = %s
    """
    cur.execute(sql, (employee_id, password))
    user = cur.fetchone()
    cur.close()

    if user:
        # 用户存在，设置session
        session.permanent = True  # 使session遵循PERMANENT_SESSION_LIFETIME设置
        session['employee_id'] = user['employee_id']
        session['name'] = user['full_name']
        session['role'] = user['role']
        
        # 返回用户信息和角色
        return jsonify(success=True, user={
            'employee_id': user['employee_id'],
            'name': user['full_name'],
            'role': user['role']
        })
    else:
        # 登录失败
        return jsonify(success=False, message="社員番号またはパスワードが正しくありません。")

# 登出API
@app.route('/api/logout', methods=['POST'])
def logout():
    # 清除session
    session.clear()
    return jsonify(success=True)

# 员工页面
@app.route('/employee')
@login_required
@role_required(['employee'])
def employee_page():
    return render_template('employee.html')

# 管理者页面
@app.route('/manager')
@login_required
@role_required(['manager'])
def manager_page():
    return render_template('manager.html')

# 总务页面
@app.route('/soumu')
@login_required
@role_required(['soumu'])
def soumu_page():
    return render_template('soumu.html')

# 出勤API
@app.route('/api/clock-in', methods=['POST'])
@login_required
def clock_in():
    employee_id = session['employee_id']
    today_date = datetime.datetime.now().date()
    clock_time = datetime.datetime.now().time()
    
    # 检查今天是否已经打卡
    cur = mysql.connection.cursor()
    cur.execute("SELECT * FROM attendance_records WHERE employee_id = %s AND date = %s", 
                (employee_id, today_date))
    existing_record = cur.fetchone()
    
    if existing_record:
        cur.close()
        return jsonify(success=False, message="本日は既に出勤打刻されています。")
    
    # 获取员工姓名
    cur.execute("SELECT CONCAT(last_name, ' ', first_name) as full_name FROM employees WHERE employee_id = %s", 
                (employee_id,))
    employee_name = cur.fetchone()['full_name']
    
    # 添加新打卡记录
    cur.execute("""
    INSERT INTO attendance_records (employee_id, employee_name, date, clock_in) 
    VALUES (%s, %s, %s, %s)
    """, (employee_id, employee_name, today_date, clock_time))
    
    mysql.connection.commit()
    cur.close()
    
    return jsonify(success=True, message=f"出勤打刻が完了しました。時間: {clock_time.strftime('%H:%M:%S')}")

# 退勤API
@app.route('/api/clock-out', methods=['POST'])
@login_required
def clock_out():
    employee_id = session['employee_id']
    today_date = datetime.datetime.now().date()
    clock_time = datetime.datetime.now().time()
    
    cur = mysql.connection.cursor()
    
    # 检查今天是否已打卡
    cur.execute("""
    SELECT * FROM attendance_records 
    WHERE employee_id = %s AND date = %s
    """, (employee_id, today_date))
    
    record = cur.fetchone()
    
    if not record:
        cur.close()
        return jsonify(success=False, message="出勤打刻がありません。")
    
    if record['clock_out']:
        cur.close()
        return jsonify(success=False, message="本日は既に退勤打刻されています。")
    
    # 处理clock_in字段，确保转换为time对象
    clock_in = record['clock_in']
    if isinstance(clock_in, datetime.time):
        clock_in_time = clock_in
    elif isinstance(clock_in, str):
        try:
            clock_in_time = datetime.datetime.strptime(clock_in, '%H:%M:%S').time()
        except ValueError:
            clock_in_time = datetime.datetime.strptime(clock_in, '%H:%M:%S.%f').time()
    elif isinstance(clock_in, datetime.timedelta):
        # 处理timedelta类型
        total_seconds = int(clock_in.total_seconds())
        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        seconds = total_seconds % 60
        clock_in_time = datetime.time(hours, minutes, seconds)
    else:
        cur.close()
        return jsonify(success=False, message="出勤時間データが不正です。")
    
    # 计算工作时间
    clock_in_str = clock_in_time.strftime('%H:%M:%S')
    clock_out_str = clock_time.strftime('%H:%M:%S')
    
    # 将时间字符串转换为datetime对象进行计算
    today_str = today_date.strftime('%Y-%m-%d')
    clock_in_dt = datetime.datetime.strptime(f"{today_str} {clock_in_str}", '%Y-%m-%d %H:%M:%S')
    clock_out_dt = datetime.datetime.strptime(f"{today_str} {clock_out_str}", '%Y-%m-%d %H:%M:%S')
    
    # 如果退勤时间早于出勤时间，表示跨天了，加一天
    if clock_out_dt < clock_in_dt:
        clock_out_dt = clock_out_dt + datetime.timedelta(days=1)
    
    time_diff = clock_out_dt - clock_in_dt
    hours = time_diff.total_seconds() / 3600  # 转换为小时
    
    # 更新退勤时间和工作时间
    cur.execute("""
    UPDATE attendance_records 
    SET clock_out = %s, hours = %s 
    WHERE employee_id = %s AND date = %s
    """, (clock_time, round(hours, 2), employee_id, today_date))
    
    mysql.connection.commit()
    cur.close()
    
    return jsonify(success=True, message=f"退勤打刻が完了しました。時間: {clock_out_str}")

# 获取个人出退勤记录API
@app.route('/api/attendance-records', methods=['GET'])
@login_required
def get_attendance_records():
    employee_id = session['employee_id']
    month = request.args.get('month')  # YYYY-MM格式
    
    cur = mysql.connection.cursor()
    
    if month:
        # 指定月份的记录
        cur.execute("""
        SELECT record_id, date, clock_in, clock_out, hours 
        FROM attendance_records 
        WHERE employee_id = %s AND DATE_FORMAT(date, '%%Y-%%m') = %s 
        ORDER BY date DESC
        """, (employee_id, month))
    else:
        # 所有记录
        cur.execute("""
        SELECT record_id, date, clock_in, clock_out, hours 
        FROM attendance_records 
        WHERE employee_id = %s 
        ORDER BY date DESC
        """, (employee_id,))
    
    records = cur.fetchall()
    cur.close()
    
    # 处理日期为可JSON序列化的格式
    result_records = []
    for record in records:
        record_dict = dict(record)
        record_dict['date'] = record_dict['date'].strftime('%Y-%m-%d')
        record_dict['clock_in'] = format_time_value(record_dict['clock_in'])
        record_dict['clock_out'] = format_time_value(record_dict['clock_out'])
        result_records.append(record_dict)
    
    return jsonify(success=True, records=result_records)

# 获取今日打卡状态API
@app.route('/api/today-status', methods=['GET'])
@login_required
def get_today_status():
    employee_id = session['employee_id']
    today = datetime.datetime.now().date()
    
    cur = mysql.connection.cursor()
    cur.execute("""
    SELECT clock_in, clock_out 
    FROM attendance_records 
    WHERE employee_id = %s AND date = %s
    """, (employee_id, today))
    
    record = cur.fetchone()
    cur.close()
    
    status = {
        'has_clock_in': False,
        'has_clock_out': False,
        'clock_in_time': None,
        'clock_out_time': None
    }
    
    if record:
        status['has_clock_in'] = True
        status['clock_in_time'] = format_time_value(record['clock_in'])
        
        if record['clock_out']:
            status['has_clock_out'] = True
            status['clock_out_time'] = format_time_value(record['clock_out'])
    
    return jsonify(success=True, status=status)

# 管理员获取所有员工记录API
@app.route('/api/all-employee-records', methods=['GET'])
@login_required
@role_required(['manager', 'soumu'])
def get_all_employee_records():
    month = request.args.get('month')  # YYYY-MM格式
    employee_id = request.args.get('employee_id')  # 可选参数，指定员工
    
    cur = mysql.connection.cursor()
    
    # 构建查询
    query = """
    SELECT ar.record_id, ar.employee_id, ar.employee_name, 
           ar.date, ar.clock_in, ar.clock_out, ar.hours
    FROM attendance_records ar
    JOIN employees e ON ar.employee_id = e.employee_id
    WHERE 1=1
    """
    params = []
    
    # 如果指定了月份
    if month:
        query += " AND DATE_FORMAT(ar.date, '%%Y-%%m') = %s"
        params.append(month)
    
    # 如果指定了员工ID且不是"all"
    if employee_id and employee_id != 'all':
        query += " AND ar.employee_id = %s"
        params.append(employee_id)
    
    # 如果是管理者，可能需要限制只能查看普通员工的记录
    # 但在这里，我们允许manager查看所有记录
    
    query += " ORDER BY ar.date DESC, ar.employee_id"
    
    cur.execute(query, params)
    records = cur.fetchall()
    
    # 处理日期为可JSON序列化的格式
    result_records = []
    for record in records:
        record_dict = dict(record)
        record_dict['date'] = record_dict['date'].strftime('%Y-%m-%d')
        record_dict['clock_in'] = format_time_value(record_dict['clock_in'])
        record_dict['clock_out'] = format_time_value(record_dict['clock_out'])
        result_records.append(record_dict)
    
    # 获取员工列表，用于下拉选择框
    cur.execute("SELECT employee_id, CONCAT(last_name, ' ', first_name) as name FROM employees ORDER BY employee_id")
    employees = cur.fetchall()
    
    cur.close()
    
    return jsonify(success=True, records=result_records, employees=employees)

# 管理员编辑打卡记录API
@app.route('/api/edit-record', methods=['POST'])
@login_required
@role_required(['manager', 'soumu'])
def edit_record():
    data = request.get_json()
    record_id = data.get('record_id')
    clock_in = data.get('clock_in')
    clock_out = data.get('clock_out')
    
    cur = mysql.connection.cursor()
    
    # 首先检查记录是否存在
    cur.execute("SELECT * FROM attendance_records WHERE record_id = %s", (record_id,))
    record = cur.fetchone()
    
    if not record:
        cur.close()
        return jsonify(success=False, message="記録が存在しません。")
    
    # 计算工作时间
    hours = None
    if clock_in and clock_out:
        date = record['date']
        date_str = date.strftime('%Y-%m-%d')
        
        # 将时间字符串转换为datetime对象进行计算
        clock_in_dt = datetime.datetime.strptime(f"{date_str} {clock_in}", '%Y-%m-%d %H:%M:%S')
        clock_out_dt = datetime.datetime.strptime(f"{date_str} {clock_out}", '%Y-%m-%d %H:%M:%S')
        
        # 如果退勤时间早于出勤时间，表示跨天了，加一天
        if clock_out_dt < clock_in_dt:
            clock_out_dt = clock_out_dt + datetime.timedelta(days=1)
        
        time_diff = clock_out_dt - clock_in_dt
        hours = time_diff.total_seconds() / 3600  # 转换为小时
    
    # 更新记录
    cur.execute("""
    UPDATE attendance_records 
    SET clock_in = %s, clock_out = %s, hours = %s 
    WHERE record_id = %s
    """, (clock_in, clock_out, round(hours, 2) if hours else None, record_id))
    
    mysql.connection.commit()
    cur.close()
    
    return jsonify(success=True, message="記録が更新されました。")

# 删除打卡记录API
@app.route('/api/delete-record', methods=['POST'])
@login_required
@role_required(['manager', 'soumu'])
def delete_record():
    data = request.get_json()
    record_id = data.get('record_id')
    
    cur = mysql.connection.cursor()
    
    # 获取待删除记录信息
    cur.execute("""
    SELECT ar.employee_id, e.role FROM attendance_records ar 
    JOIN employees e ON ar.employee_id = e.employee_id 
    WHERE ar.record_id = %s
    """, (record_id,))
    record = cur.fetchone()
    
    if not record:
        cur.close()
        return jsonify(success=False, message="記録が存在しません。")
    
    # 权限检查：总务只能删除管理者和自己的记录，不能删除普通员工的记录
    if session['role'] == 'soumu' and record['role'] == 'employee':
        cur.close()
        return jsonify(success=False, message="総務は管理者と総務の記録のみ削除できます。")
    
    # 管理员可以删除所有记录
    cur.execute("DELETE FROM attendance_records WHERE record_id = %s", (record_id,))
    mysql.connection.commit()
    cur.close()
    
    return jsonify(success=True, message="記録が削除されました。")

# 修改密码API
@app.route('/api/change-password', methods=['POST'])
@login_required
def change_password():
    data = request.get_json()
    current_password = data.get('current_password')
    new_password = data.get('new_password')
    
    if not current_password or not new_password:
        return jsonify(success=False, message="パスワードを入力してください。")
    
    cur = mysql.connection.cursor()
    
    # 验证当前密码
    cur.execute("""
    SELECT employee_id FROM employees 
    WHERE employee_id = %s AND password = %s
    """, (session['employee_id'], current_password))
    
    user = cur.fetchone()
    
    if not user:
        cur.close()
        return jsonify(success=False, message="現在のパスワードが正しくありません。")
    
    # 更新密码
    cur.execute("""
    UPDATE employees SET password = %s 
    WHERE employee_id = %s
    """, (new_password, session['employee_id']))
    
    mysql.connection.commit()
    cur.close()
    
    return jsonify(success=True, message="パスワードが変更されました。")

# 获取所有员工列表API (用于下拉选择框)
@app.route('/api/employee-list', methods=['GET'])
@login_required
@role_required(['manager', 'soumu'])
def get_employee_list():
    cur = mysql.connection.cursor()
    
    # 获取所有员工列表
    cur.execute("SELECT employee_id, CONCAT(last_name, ' ', first_name) as name FROM employees ORDER BY employee_id")
    employees = cur.fetchall()
    
    cur.close()
    
    return jsonify(success=True, employees=employees)

@app.route('/api/employee-role/<employee_id>', methods=['GET'])
@login_required
@role_required(['manager', 'soumu'])
def get_employee_role(employee_id):
    cur = mysql.connection.cursor()
    
    # Get the employee's role
    cur.execute("SELECT role FROM employees WHERE employee_id = %s", (employee_id,))
    employee = cur.fetchone()
    
    cur.close()
    
    if employee:
        return jsonify(success=True, role=employee['role'])
    else:
        return jsonify(success=False, message="社員が見つかりません。")

@app.route('/api/add-employee', methods=['POST'])
@login_required
@role_required(['soumu'])
def add_employee():
    data = request.get_json()
    employee_id = data.get('employee_id')
    first_name = data.get('first_name')
    last_name = data.get('last_name')
    password = data.get('password')
    role = data.get('role')
    
    # Validation
    if not all([employee_id, first_name, last_name, password, role]):
        return jsonify(success=False, message="すべての項目を入力してください。")
    
    if role not in ['employee', 'manager', 'soumu']:
        return jsonify(success=False, message="無効な権限です。")
    
    # Check if employee_id already exists
    cur = mysql.connection.cursor()
    cur.execute("SELECT employee_id FROM employees WHERE employee_id = %s", (employee_id,))
    existing_employee = cur.fetchone()
    
    if existing_employee:
        cur.close()
        return jsonify(success=False, message="この社員番号は既に存在します。")
    
    # Add new employee
    try:
        cur.execute("""
        INSERT INTO employees (employee_id, first_name, last_name, password, role) 
        VALUES (%s, %s, %s, %s, %s)
        """, (employee_id, first_name, last_name, password, role))
        mysql.connection.commit()
        cur.close()
        return jsonify(success=True, message="社員を追加しました。")
    except Exception as e:
        cur.close()
        return jsonify(success=False, message=f"エラーが発生しました: {str(e)}")

# 社员删除API
@app.route('/api/delete-employee', methods=['POST'])
@login_required
@role_required(['soumu'])
def delete_employee():
    data = request.get_json()
    employee_id = data.get('employee_id')
    
    if not employee_id:
        return jsonify(success=False, message="社員番号が指定されていません。")
    
    # Make sure user is not deleting their own account
    if employee_id == session['employee_id']:
        return jsonify(success=False, message="自分自身のアカウントは削除できません。")
    
    cur = mysql.connection.cursor()
    
    # Delete related attendance records first (due to foreign key constraint)
    try:
        cur.execute("DELETE FROM attendance_records WHERE employee_id = %s", (employee_id,))
        cur.execute("DELETE FROM employees WHERE employee_id = %s", (employee_id,))
        mysql.connection.commit()
        cur.close()
        return jsonify(success=True, message="社員を削除しました。")
    except Exception as e:
        cur.close()
        return jsonify(success=False, message=f"エラーが発生しました: {str(e)}")

# 获取社员列表API (包含完整信息，用于管理界面)
@app.route('/api/employee-full-list', methods=['GET'])
@login_required
@role_required(['soumu'])
def get_employee_full_list():
    cur = mysql.connection.cursor()
    
    # Get all employees
    cur.execute("""
    SELECT employee_id, first_name, last_name, CONCAT(last_name, ' ', first_name) as full_name, role
    FROM employees ORDER BY employee_id
    """)
    employees = cur.fetchall()
    cur.close()
    
    # Map role values to display names
    for emp in employees:
        if emp['role'] == 'soumu':
            emp['role_display'] = '総務'
        elif emp['role'] == 'manager':
            emp['role_display'] = '管理者'
        elif emp['role'] == 'employee':
            emp['role_display'] = '一般'
    
    return jsonify(success=True, employees=employees)

if __name__ == '__main__':
    app.run(debug=True)