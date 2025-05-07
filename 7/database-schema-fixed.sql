-- 创建数据库
CREATE DATABASE IF NOT EXISTS attendance_system;
USE attendance_system;

-- 创建员工表
CREATE TABLE IF NOT EXISTS employees (
    employee_id VARCHAR(10) PRIMARY KEY,
    password VARCHAR(100) NOT NULL,
    first_name VARCHAR(50) NOT NULL,
    last_name VARCHAR(50) NOT NULL,
    role ENUM('soumu', 'manager', 'employee') NOT NULL
);

-- 创建出退勤记录表
CREATE TABLE IF NOT EXISTS attendance_records (
    record_id INT AUTO_INCREMENT PRIMARY KEY,
    employee_id VARCHAR(10) NOT NULL,
    employee_name VARCHAR(100) NOT NULL,
    date DATE NOT NULL,
    clock_in TIME,
    clock_out TIME,
    hours DECIMAL(5,2),
    FOREIGN KEY (employee_id) REFERENCES employees(employee_id),
    UNIQUE KEY (employee_id, date)
);

-- 插入初始用户数据
INSERT INTO employees (employee_id, password, first_name, last_name, role) VALUES
('1001', 'pass1001', '太郎', '山田', 'manager'),
('1002', 'pass1002', '次郎', '佐藤', 'employee'),
('1003', 'pass1003', '三郎', '鈴木', 'employee'),
('1004', 'pass1004', '花子', '高橋', 'soumu');