from flask import Flask, request, jsonify, render_template, session, redirect, url_for
import pymysql
import datetime
import json
from functools import wraps
from datetime import timedelta
import os


app = Flask(__name__)

# 数据库连接函数 - 替代Flask-MySQLdb
def get_db_connection():
    """创建并返回数据库连接"""
    connection = pymysql.connect(
        host=os.getenv('DB_HOST', 'team2-mysql-version1.mysql.database.azure.com'),
        user=os.getenv('DB_USER', 'azureuser'),  # 注意：需要包含@服务器名
        password=os.getenv('DB_PASSWORD', 'Password1234'),
        database=os.getenv('DB_NAME', 'attendance_system'),
        ssl={
            'ca': os.getenv('MYSQL_SSL_CA', 'DigiCertGlobalRootCA.crt.pem')
        },
        cursorclass=pymysql.cursors.DictCursor
    )
    return connection

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


@app.route('/test-db')
def test_db():
    """增强版数据库连接测试函数 - 提供详细的连接诊断信息"""
    try:
        # 获取数据库连接
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # 检查基本连接
        cursor.execute('SELECT 1 as connection_test')
        basic_result = cursor.fetchone()
        
        # 检查SSL状态
        cursor.execute('SHOW STATUS LIKE "Ssl_cipher"')
        ssl_result = cursor.fetchone()
        ssl_status = ssl_result.get('Value', 'Not using SSL') if ssl_result else 'Not using SSL'
        
        # 获取服务器信息
        cursor.execute('SELECT VERSION() as version, DATABASE() as current_db')
        server_info = cursor.fetchone()
        
        # 获取数据库时区
        cursor.execute('SELECT @@time_zone as time_zone')
        timezone = cursor.fetchone()
        
        cursor.close()
        conn.close()
        
        # 收集证书信息
        cert_path = os.getenv('MYSQL_SSL_CA', 'DigiCertGlobalRootCA.crt.pem')
        cert_exists = os.path.exists(cert_path) if cert_path else False
        
        return jsonify({
            'success': True,
            'message': "数据库连接成功！",
            'connection_test': basic_result,
            'server_info': server_info,
            'ssl_status': {
                'using_ssl': ssl_status != 'Not using SSL',
                'ssl_cipher': ssl_status,
            },
            'timezone': timezone,
            'ssl_cert': {
                'configured': cert_path != 'Not configured',
                'exists': cert_exists,
                'path': cert_path
            }
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f"数据库连接失败：{str(e)}",
            'error_type': type(e).__name__
        })

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
    try:
        data = request.get_json()
        employee_id = data.get('employee_id')
        password = data.get('password')

        # 获取数据库连接
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # 查询匹配的用户
        sql = """
        SELECT employee_id, CONCAT(last_name, ' ', first_name) as full_name, role 
        FROM employees 
        WHERE employee_id = %s AND password = %s
        """
        cursor.execute(sql, (employee_id, password))
        user = cursor.fetchone()
        cursor.close()
        conn.close()

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
    except Exception as e:
        print(f"登录错误: {str(e)}")
        return jsonify(success=False, message=f"エラーが発生しました: {str(e)}"), 500

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
    try:
        employee_id = session['employee_id']
        today_date = datetime.datetime.now().date()
        clock_time = datetime.datetime.now().time()
        
        # 获取数据库连接
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # 检查今天是否已经打卡
        cursor.execute("SELECT * FROM attendance_records WHERE employee_id = %s AND date = %s", 
                    (employee_id, today_date))
        existing_record = cursor.fetchone()
        
        if existing_record:
            cursor.close()
            conn.close()
            return jsonify(success=False, message="本日は既に出勤打刻されています。")
        
        # 获取员工姓名
        cursor.execute("SELECT CONCAT(last_name, ' ', first_name) as full_name FROM employees WHERE employee_id = %s", 
                    (employee_id,))
        employee_name = cursor.fetchone()['full_name']
        
        # 添加新打卡记录
        cursor.execute("""
        INSERT INTO attendance_records (employee_id, employee_name, date, clock_in) 
        VALUES (%s, %s, %s, %s)
        """, (employee_id, employee_name, today_date, clock_time))
        
        conn.commit()
        cursor.close()
        conn.close()
        
        return jsonify(success=True, message=f"出勤打刻が完了しました。時間: {clock_time.strftime('%H:%M:%S')}")
    except Exception as e:
        print(f"出勤打卡错误: {str(e)}")
        return jsonify(success=False, message=f"エラーが発生しました: {str(e)}"), 500

# 退勤API
@app.route('/api/clock-out', methods=['POST'])
@login_required
def clock_out():
    try:
        employee_id = session['employee_id']
        today_date = datetime.datetime.now().date()
        clock_time = datetime.datetime.now().time()
        
        # 获取数据库连接
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # 检查今天是否已打卡
        cursor.execute("""
        SELECT * FROM attendance_records 
        WHERE employee_id = %s AND date = %s
        """, (employee_id, today_date))
        
        record = cursor.fetchone()
        
        if not record:
            cursor.close()
            conn.close()
            return jsonify(success=False, message="出勤打刻がありません。")
        
        if record['clock_out']:
            cursor.close()
            conn.close()
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
            cursor.close()
            conn.close()
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
        cursor.execute("""
        UPDATE attendance_records 
        SET clock_out = %s, hours = %s 
        WHERE employee_id = %s AND date = %s
        """, (clock_time, round(hours, 2), employee_id, today_date))
        
        conn.commit()
        cursor.close()
        conn.close()
        
        return jsonify(success=True, message=f"退勤打刻が完了しました。時間: {clock_out_str}")
    except Exception as e:
        print(f"退勤打卡错误: {str(e)}")
        return jsonify(success=False, message=f"エラーが発生しました: {str(e)}"), 500

# 获取个人出退勤记录API
@app.route('/api/attendance-records', methods=['GET'])
@login_required
def get_attendance_records():
    try:
        employee_id = session['employee_id']
        month = request.args.get('month')  # YYYY-MM格式
        
        # 获取数据库连接
        conn = get_db_connection()
        cursor = conn.cursor()
        
        if month:
            # 指定月份的记录
            cursor.execute("""
            SELECT record_id, date, clock_in, clock_out, hours 
            FROM attendance_records 
            WHERE employee_id = %s AND DATE_FORMAT(date, '%%Y-%%m') = %s 
            ORDER BY date DESC
            """, (employee_id, month))
        else:
            # 所有记录
            cursor.execute("""
            SELECT record_id, date, clock_in, clock_out, hours 
            FROM attendance_records 
            WHERE employee_id = %s 
            ORDER BY date DESC
            """, (employee_id,))
        
        records = cursor.fetchall()
        cursor.close()
        conn.close()
        
        # 处理日期为可JSON序列化的格式
        result_records = []
        for record in records:
            record_dict = dict(record)
            record_dict['date'] = record_dict['date'].strftime('%Y-%m-%d')
            record_dict['clock_in'] = format_time_value(record_dict['clock_in'])
            record_dict['clock_out'] = format_time_value(record_dict['clock_out'])
            result_records.append(record_dict)
        
        return jsonify(success=True, records=result_records)
    except Exception as e:
        print(f"获取出勤记录错误: {str(e)}")
        return jsonify(success=False, message=f"エラーが発生しました: {str(e)}"), 500

# 获取今日打卡状态API
@app.route('/api/today-status', methods=['GET'])
@login_required
def get_today_status():
    try:
        employee_id = session['employee_id']
        today = datetime.datetime.now().date()
        
        # 获取数据库连接
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
        SELECT clock_in, clock_out 
        FROM attendance_records 
        WHERE employee_id = %s AND date = %s
        """, (employee_id, today))
        
        record = cursor.fetchone()
        cursor.close()
        conn.close()
        
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
    except Exception as e:
        print(f"获取今日状态错误: {str(e)}")
        return jsonify(success=False, message=f"エラーが発生しました: {str(e)}"), 500

# 管理员获取所有员工记录API
@app.route('/api/all-employee-records', methods=['GET'])
@login_required
@role_required(['manager', 'soumu'])
def get_all_employee_records():
    try:
        month = request.args.get('month')  # YYYY-MM格式
        employee_id = request.args.get('employee_id')  # 可选参数，指定员工
        
        # 获取数据库连接
        conn = get_db_connection()
        cursor = conn.cursor()
        
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
        
        cursor.execute(query, params)
        records = cursor.fetchall()
        
        # 处理日期为可JSON序列化的格式
        result_records = []
        for record in records:
            record_dict = dict(record)
            record_dict['date'] = record_dict['date'].strftime('%Y-%m-%d')
            record_dict['clock_in'] = format_time_value(record_dict['clock_in'])
            record_dict['clock_out'] = format_time_value(record_dict['clock_out'])
            result_records.append(record_dict)
        
        # 获取员工列表，用于下拉选择框
        cursor.execute("SELECT employee_id, CONCAT(last_name, ' ', first_name) as name FROM employees ORDER BY employee_id")
        employees = cursor.fetchall()
        
        cursor.close()
        conn.close()
        
        return jsonify(success=True, records=result_records, employees=employees)
    except Exception as e:
        print(f"获取所有员工记录错误: {str(e)}")
        return jsonify(success=False, message=f"エラーが発生しました: {str(e)}"), 500

# 管理员编辑打卡记录API
@app.route('/api/edit-record', methods=['POST'])
@login_required
@role_required(['manager', 'soumu'])
def edit_record():
    try:
        data = request.get_json()
        record_id = data.get('record_id')
        clock_in = data.get('clock_in')
        clock_out = data.get('clock_out')
        
        # 获取数据库连接
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # 首先检查记录是否存在
        cursor.execute("SELECT * FROM attendance_records WHERE record_id = %s", (record_id,))
        record = cursor.fetchone()
        
        if not record:
            cursor.close()
            conn.close()
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
        cursor.execute("""
        UPDATE attendance_records 
        SET clock_in = %s, clock_out = %s, hours = %s 
        WHERE record_id = %s
        """, (clock_in, clock_out, round(hours, 2) if hours else None, record_id))
        
        conn.commit()
        cursor.close()
        conn.close()
        
        return jsonify(success=True, message="記録が更新されました。")
    except Exception as e:
        print(f"编辑记录错误: {str(e)}")
        return jsonify(success=False, message=f"エラーが発生しました: {str(e)}"), 500

# 删除打卡记录API
@app.route('/api/delete-record', methods=['POST'])
@login_required
@role_required(['manager', 'soumu'])
def delete_record():
    try:
        data = request.get_json()
        record_id = data.get('record_id')
        
        # 获取数据库连接
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # 获取待删除记录信息
        cursor.execute("""
        SELECT ar.employee_id, e.role FROM attendance_records ar 
        JOIN employees e ON ar.employee_id = e.employee_id 
        WHERE ar.record_id = %s
        """, (record_id,))
        record = cursor.fetchone()
        
        if not record:
            cursor.close()
            conn.close()
            return jsonify(success=False, message="記録が存在しません。")
        
        # 权限检查：总务只能删除管理者和自己的记录，不能删除普通员工的记录
        if session['role'] == 'soumu' and record['role'] == 'employee':
            cursor.close()
            conn.close()
            return jsonify(success=False, message="総務は管理者と総務の記録のみ削除できます。")
        
        # 管理员可以删除所有记录
        cursor.execute("DELETE FROM attendance_records WHERE record_id = %s", (record_id,))
        conn.commit()
        cursor.close()
        conn.close()
        
        return jsonify(success=True, message="記録が削除されました。")
    except Exception as e:
        print(f"删除记录错误: {str(e)}")
        return jsonify(success=False, message=f"エラーが発生しました: {str(e)}"), 500

# 修改密码API
@app.route('/api/change-password', methods=['POST'])
@login_required
def change_password():
    try:
        data = request.get_json()
        current_password = data.get('current_password')
        new_password = data.get('new_password')
        
        if not current_password or not new_password:
            return jsonify(success=False, message="パスワードを入力してください。")
        
        # 获取数据库连接
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # 验证当前密码
        cursor.execute("""
        SELECT employee_id FROM employees 
        WHERE employee_id = %s AND password = %s
        """, (session['employee_id'], current_password))
        
        user = cursor.fetchone()
        
        if not user:
            cursor.close()
            conn.close()
            return jsonify(success=False, message="現在のパスワードが正しくありません。")
        
        # 更新密码
        cursor.execute("""
        UPDATE employees SET password = %s 
        WHERE employee_id = %s
        """, (new_password, session['employee_id']))
        
        conn.commit()
        cursor.close()
        conn.close()
        
        return jsonify(success=True, message="パスワードが変更されました。")
    except Exception as e:
        print(f"修改密码错误: {str(e)}")
        return jsonify(success=False, message=f"エラーが発生しました: {str(e)}"), 500

# 获取所有员工列表API (用于下拉选择框)
@app.route('/api/employee-list', methods=['GET'])
@login_required
@role_required(['manager', 'soumu'])
def get_employee_list():
    try:
        # 获取数据库连接
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # 获取所有员工列表
        cursor.execute("SELECT employee_id, CONCAT(last_name, ' ', first_name) as name FROM employees ORDER BY employee_id")
        employees = cursor.fetchall()
        
        cursor.close()
        conn.close()
        
        return jsonify(success=True, employees=employees)
    except Exception as e:
        print(f"获取员工列表错误: {str(e)}")
        return jsonify(success=False, message=f"エラーが発生しました: {str(e)}"), 500

@app.route('/api/employee-role/<employee_id>', methods=['GET'])
@login_required
@role_required(['manager', 'soumu'])
def get_employee_role(employee_id):
    try:
        # 获取数据库连接
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Get the employee's role
        cursor.execute("SELECT role FROM employees WHERE employee_id = %s", (employee_id,))
        employee = cursor.fetchone()
        
        cursor.close()
        conn.close()
        
        if employee:
            return jsonify(success=True, role=employee['role'])
        else:
            return jsonify(success=False, message="社員が見つかりません。")
    except Exception as e:
        print(f"获取员工角色错误: {str(e)}")
        return jsonify(success=False, message=f"エラーが発生しました: {str(e)}"), 500

@app.route('/api/add-employee', methods=['POST'])
@login_required
@role_required(['soumu'])
def add_employee():
    try:
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
        
        # 获取数据库连接
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Check if employee_id already exists
        cursor.execute("SELECT employee_id FROM employees WHERE employee_id = %s", (employee_id,))
        existing_employee = cursor.fetchone()
        
        if existing_employee:
            cursor.close()
            conn.close()
            return jsonify(success=False, message="この社員番号は既に存在します。")
        
        # Add new employee
        try:
            cursor.execute("""
            INSERT INTO employees (employee_id, first_name, last_name, password, role) 
            VALUES (%s, %s, %s, %s, %s)
            """, (employee_id, first_name, last_name, password, role))
            conn.commit()
            cursor.close()
            conn.close()
            return jsonify(success=True, message="社員を追加しました。")
        except Exception as e:
            cursor.close()
            conn.close()
            return jsonify(success=False, message=f"エラーが発生しました: {str(e)}")
    except Exception as e:
        print(f"添加员工错误: {str(e)}")
        return jsonify(success=False, message=f"エラーが発生しました: {str(e)}"), 500

# 社员删除API（续）
@app.route('/api/delete-employee', methods=['POST'])
@login_required
@role_required(['soumu'])
def delete_employee():
    try:
        data = request.get_json()
        employee_id = data.get('employee_id')
        
        if not employee_id:
            return jsonify(success=False, message="社員番号が指定されていません。")
        
        # Make sure user is not deleting their own account
        if employee_id == session['employee_id']:
            return jsonify(success=False, message="自分自身のアカウントは削除できません。")
        
        # 获取数据库连接
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Delete related attendance records first (due to foreign key constraint)
        try:
            cursor.execute("DELETE FROM attendance_records WHERE employee_id = %s", (employee_id,))
            cursor.execute("DELETE FROM employees WHERE employee_id = %s", (employee_id,))
            conn.commit()
            cursor.close()
            conn.close()
            return jsonify(success=True, message="社員を削除しました。")
        except Exception as e:
            cursor.close()
            conn.close()
            return jsonify(success=False, message=f"エラーが発生しました: {str(e)}")
    except Exception as e:
        print(f"删除员工错误: {str(e)}")
        return jsonify(success=False, message=f"エラーが発生しました: {str(e)}"), 500

# 获取社员列表API (包含完整信息，用于管理界面)
@app.route('/api/employee-full-list', methods=['GET'])
@login_required
@role_required(['soumu'])
def reset_password():
    """
    社員のパスワードを初期値「password」にリセットします。
    """
    data = request.get_json()
    employee_id = data.get('employee_id')
    if not employee_id:
        return jsonify(success=False, message="社員番号が指定されていません。"), 400

    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                "UPDATE employees SET password = %s WHERE employee_id = %s",
                ('password', employee_id)
            )
        conn.commit()
        return jsonify(success=True, message="パスワードを初期化しました。")
    except Exception as e:
        return jsonify(success=False, message=f"初期化に失敗しました: {e}"), 500
    finally:
        conn.close()

def get_employee_full_list():
    try:
        # 获取数据库连接
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Get all employees
        cursor.execute("""
        SELECT employee_id, first_name, last_name, CONCAT(last_name, ' ', first_name) as full_name, role
        FROM employees ORDER BY employee_id
        """)
        employees = cursor.fetchall()
        cursor.close()
        conn.close()
        
        # Map role values to display names
        for emp in employees:
            if emp['role'] == 'soumu':
                emp['role_display'] = '総務'
            elif emp['role'] == 'manager':
                emp['role_display'] = '管理者'
            elif emp['role'] == 'employee':
                emp['role_display'] = '一般'
        
        return jsonify(success=True, employees=employees)
    except Exception as e:
        print(f"获取员工完整列表错误: {str(e)}")
        return jsonify(success=False, message=f"エラーが発生しました: {str(e)}"), 500

# 添加调试端点，用于详细测试数据库连接
@app.route('/debug-db')
def debug_db():
    """详细调试数据库连接"""
    result = {
        "connection_attempts": [],
        "queries": [],
        "config": {},
        "ssl_info": {}
    }
    
    # 记录配置信息（移除敏感信息）
    result["config"] = {
        "host": os.getenv('DB_HOST', 'team2-mysql-version1.mysql.database.azure.com'),
        "user": os.getenv('DB_USER', 'azureuser@team2-mysql-version1').split('@')[0] + '@...' 
                if '@' in os.getenv('DB_USER', 'azureuser@team2-mysql-version1') 
                else os.getenv('DB_USER', 'azureuser@team2-mysql-version1'),
        "database": os.getenv('DB_NAME', 'attendance_system'),
        "ssl_ca": os.getenv('MYSQL_SSL_CA', 'DigiCertGlobalRootCA.crt.pem')
    }
    
    # 检查SSL证书
    ssl_ca_path = os.getenv('MYSQL_SSL_CA', 'DigiCertGlobalRootCA.crt.pem')
    result["ssl_info"] = {
        "path": ssl_ca_path,
        "exists": os.path.exists(ssl_ca_path) if ssl_ca_path else False,
        "size_bytes": os.path.getsize(ssl_ca_path) if ssl_ca_path and os.path.exists(ssl_ca_path) else 0
    }
    
    # 尝试连接
    connection_attempt = {"step": "初始化连接", "success": False, "error": None}
    try:
        # 尝试获取连接
        connection_attempt["step"] = "获取数据库连接"
        conn = get_db_connection()
        connection_attempt["success"] = True
        result["connection_attempts"].append(connection_attempt)
        
        # 尝试执行简单查询
        query_attempt = {"query": "SELECT 1", "success": False, "error": None, "result": None}
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT 1 as test")
            query_attempt["result"] = cursor.fetchone()
            query_attempt["success"] = True
            result["queries"].append(query_attempt)
            
            # 检查SSL状态
            ssl_query = {"query": "SHOW STATUS LIKE 'Ssl_cipher'", "success": False, "error": None, "result": None}
            try:
                cursor.execute("SHOW STATUS LIKE 'Ssl_cipher'")
                ssl_status = cursor.fetchone()
                ssl_query["result"] = ssl_status
                ssl_query["success"] = True
                ssl_query["using_ssl"] = ssl_status.get('Value', '') != '' if ssl_status else False
                result["queries"].append(ssl_query)
            except Exception as e:
                ssl_query["error"] = str(e)
                result["queries"].append(ssl_query)
            
            # 尝试访问employees表
            emp_query = {"query": "SELECT COUNT(*) FROM employees", "success": False, "error": None, "result": None}
            try:
                cursor.execute("SELECT COUNT(*) as count FROM employees")
                emp_count = cursor.fetchone()
                emp_query["result"] = emp_count
                emp_query["success"] = True
                result["queries"].append(emp_query)
            except Exception as e:
                emp_query["error"] = str(e)
                result["queries"].append(emp_query)
            
            cursor.close()
            conn.close()
            
        except Exception as e:
            query_attempt["error"] = str(e)
            result["queries"].append(query_attempt)
        
    except Exception as e:
        connection_attempt["error"] = str(e)
        result["connection_attempts"].append(connection_attempt)
    
    # 确定总体状态
    result["overall_success"] = (
        len(result["connection_attempts"]) > 0 and 
        all(attempt.get("success", False) for attempt in result["connection_attempts"]) and
        len(result["queries"]) > 0 and 
        any(query.get("success", False) for query in result["queries"])
    )
    
    return jsonify(result)

if __name__ == '__main__':
    # 打印配置信息（隐藏密码）
    print("=== 数据库配置信息 ===")
    print(f"主机: {os.getenv('DB_HOST', 'team2-mysql-version1.mysql.database.azure.com')}")
    print(f"用户: {os.getenv('DB_USER', 'azureuser@team2-mysql-version1')}")
    print(f"数据库: {os.getenv('DB_NAME', 'attendance_system')}")
    print(f"SSL证书: {os.getenv('MYSQL_SSL_CA', 'DigiCertGlobalRootCA.crt.pem')}")
    
    # 检查SSL证书是否存在
    ssl_path = os.getenv('MYSQL_SSL_CA', 'DigiCertGlobalRootCA.crt.pem')
    if ssl_path:
        if os.path.exists(ssl_path):
            print(f"SSL证书文件存在: {os.path.abspath(ssl_path)}")
        else:
            print(f"警告: SSL证书文件不存在: {os.path.abspath(ssl_path)}")
    
    # 测试数据库连接
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT 1")
        print("数据库连接测试成功!")
        cursor.close()
        conn.close()
    except Exception as e:
        print(f"数据库连接测试失败: {e}")
    
    # 启动应用
    app.run(debug=True)