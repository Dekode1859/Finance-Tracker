import sqlite3
import pandas as pd
from datetime import datetime, timedelta, date
import calendar

def init_db():
    """Initialize SQLite database"""
    conn = sqlite3.connect('transactions.db')
    c = conn.cursor()
    
    # Create users table
    c.execute('''
    CREATE TABLE IF NOT EXISTS users (
        user_id TEXT PRIMARY KEY,
        email TEXT UNIQUE,
        name TEXT,
        last_login TEXT,
        created_at TEXT
    )
    ''')
    
    # Create transactions table with user_id field
    c.execute('''
    CREATE TABLE IF NOT EXISTS transactions (
        transaction_id TEXT PRIMARY KEY,
        user_id TEXT,
        transaction_date TEXT,
        transaction_amount REAL,
        transaction_type TEXT,
        transaction_description TEXT,
        available_balance REAL,
        account_number TEXT,
        email_body TEXT,
        processed_date TEXT,
        FOREIGN KEY (user_id) REFERENCES users(user_id)
    )
    ''')
    
    # Create settings table to store user preferences like payroll date
    # Add user_id to make settings user-specific
    c.execute('''
    CREATE TABLE IF NOT EXISTS settings (
        setting_id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id TEXT,
        setting_key TEXT,
        setting_value TEXT,
        updated_at TEXT,
        FOREIGN KEY (user_id) REFERENCES users(user_id),
        UNIQUE(user_id, setting_key)
    )
    ''')
    
    conn.commit()
    return conn

def save_user(conn, user_id, email, name=None):
    """Save or update user information"""
    c = conn.cursor()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    # Check if user exists
    c.execute("SELECT 1 FROM users WHERE user_id = ?", (user_id,))
    exists = c.fetchone()
    
    if exists:
        # Update existing user
        c.execute('''
        UPDATE users 
        SET email = ?, name = ?, last_login = ?
        WHERE user_id = ?
        ''', (email, name, now, user_id))
    else:
        # Insert new user
        c.execute('''
        INSERT INTO users (user_id, email, name, last_login, created_at)
        VALUES (?, ?, ?, ?, ?)
        ''', (user_id, email, name, now, now))
    
    conn.commit()
    return user_id

def get_user_by_email(conn, email):
    """Get user information by email"""
    c = conn.cursor()
    c.execute("SELECT user_id, email, name, last_login, created_at FROM users WHERE email = ?", (email,))
    result = c.fetchone()
    
    if result:
        return {
            'user_id': result[0],
            'email': result[1],
            'name': result[2],
            'last_login': result[3],
            'created_at': result[4]
        }
    return None

def save_setting(conn, user_id, key, value):
    """Save a setting to the database for a specific user"""
    c = conn.cursor()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    c.execute('''
    INSERT OR REPLACE INTO settings (user_id, setting_key, setting_value, updated_at)
    VALUES (?, ?, ?, ?)
    ''', (user_id, key, value, now))
    
    conn.commit()

def get_setting(conn, user_id, key, default=None):
    """Get a setting from the database for a specific user"""
    c = conn.cursor()
    c.execute("SELECT setting_value FROM settings WHERE user_id = ? AND setting_key = ?", (user_id, key))
    result = c.fetchone()
    
    if result:
        return result[0]
    return default

def get_all_user_settings(conn, user_id):
    """Get all settings for a specific user"""
    c = conn.cursor()
    c.execute("""
    SELECT setting_id, user_id, setting_key, setting_value, updated_at 
    FROM settings 
    WHERE user_id = ?
    ORDER BY setting_key
    """, (user_id,))
    
    results = c.fetchall()
    
    if results:
        settings = []
        for row in results:
            settings.append({
                'setting_id': row[0],
                'user_id': row[1],
                'setting_key': row[2],
                'setting_value': row[3],
                'updated_at': row[4]
            })
        return settings
    return []

def save_transactions_to_db(conn, user_id, transactions):
    """Save transactions to SQLite database for a specific user"""
    c = conn.cursor()
    saved_count = 0
    
    for transaction in transactions:
        transaction['processed_date'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # Check if transaction already exists for this user
        c.execute("SELECT 1 FROM transactions WHERE transaction_id = ? AND user_id = ?", 
                 (transaction['transaction_id'], user_id))
        exists = c.fetchone()
        
        if not exists:
            # Insert with simplified fields - empty strings for description and account_number
            c.execute('''
            INSERT INTO transactions 
            (transaction_id, user_id, transaction_date, transaction_amount, transaction_type, 
             transaction_description, available_balance, account_number, email_body, processed_date)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                transaction['transaction_id'],
                user_id,
                transaction['transaction_date'],
                transaction['transaction_amount'],
                transaction['transaction_type'],
                transaction['transaction_description'],  # Empty string
                transaction['available_balance'],
                transaction['account_number'],  # Empty string
                transaction['email_body'],
                transaction['processed_date']
            ))
            saved_count += 1
    
    conn.commit()
    return saved_count

def get_transactions_from_db(conn, user_id):
    """Get all transactions from database for a specific user"""
    df = pd.read_sql_query("SELECT * FROM transactions WHERE user_id = ?", conn, params=(user_id,))
    return df

def clear_transactions_db(conn, user_id):
    """Clear all transactions from the database for a specific user"""
    c = conn.cursor()
    c.execute("DELETE FROM transactions WHERE user_id = ?", (user_id,))
    conn.commit()

def get_current_month_dates():
    """Get start and end dates for current month"""
    today = date.today()
    start_of_month = date(today.year, today.month, 1)
    # For end date, use today
    return start_of_month, today

def get_payroll_date_range(payroll_day, months_back=0):
    """
    Calculate date range based on payroll date
    Returns start_date and end_date for the specified period
    """
    today = date.today()
    
    # Calculate the reference month (current month - months_back)
    if months_back > 0:
        # Calculate the target month by subtracting months_back
        year = today.year - ((today.month - months_back - 1) // 12)
        month = ((today.month - months_back - 1) % 12) + 1
    else:
        year = today.year
        month = today.month
    
    # Get the last day of the reference month
    _, last_day = calendar.monthrange(year, month)
    
    # Ensure payroll_day is valid for the month
    payroll_day = min(payroll_day, last_day)
    
    # Create the payroll date for the reference month
    payroll_date = date(year, month, payroll_day)
    
    # If we're looking at the current month and today is before payroll date,
    # we need to use the previous month's payroll date as the start
    if months_back == 0 and today < payroll_date:
        # Go back one more month for the start date
        prev_month = month - 1
        prev_year = year
        if prev_month == 0:
            prev_month = 12
            prev_year -= 1
        _, prev_last_day = calendar.monthrange(prev_year, prev_month)
        payroll_day = min(payroll_day, prev_last_day)
        start_date = date(prev_year, prev_month, payroll_day)
    else:
        start_date = payroll_date
    
    # Calculate the end date (next month's payroll date - 1 day)
    next_month = month + 1
    next_year = year
    if next_month > 12:
        next_month = 1
        next_year += 1
    
    _, next_last_day = calendar.monthrange(next_year, next_month)
    next_payroll_day = min(payroll_day, next_last_day)
    
    # End date is the day before the next payroll date
    end_date = date(next_year, next_month, next_payroll_day) - timedelta(days=1)
    
    # If end_date is in the future, use today instead
    if end_date > today:
        end_date = today
    
    return start_date, end_date 