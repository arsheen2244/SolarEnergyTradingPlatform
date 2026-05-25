import sqlite3
import os
from werkzeug.security import generate_password_hash

DB_PATH = os.path.join(os.path.dirname(__file__), 'urrja.db')

def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()

    # Enable foreign keys
    cursor.execute("PRAGMA foreign_keys = ON;")

    # 1. Users Table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        email TEXT,
        role TEXT NOT NULL DEFAULT 'user',
        balance REAL DEFAULT 1000.0
    );
    ''')

    # 2. Houses/Devices Table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS houses (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        house_name TEXT NOT NULL,
        device_token TEXT UNIQUE NOT NULL,
        status TEXT DEFAULT 'offline',
        battery_capacity REAL DEFAULT 1200.0, -- Wh (e.g. 100Ah 12V Battery)
        ip_address TEXT,
        last_seen DATETIME,
        FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE SET NULL
    );
    ''')

    # 3. Energy Readings (Telemetry Log)
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS energy_readings (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        house_id INTEGER,
        battery_voltage REAL,
        battery_current REAL,
        power REAL,
        battery_soc REAL,
        available_surplus REAL,
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (house_id) REFERENCES houses (id) ON DELETE CASCADE
    );
    ''')

    # 4. Energy Listings (Sellers)
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS listings (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        seller_house_id INTEGER,
        energy_amount_wh REAL NOT NULL,
        remaining_energy_wh REAL NOT NULL,
        price_per_wh REAL NOT NULL,
        status TEXT DEFAULT 'available', -- 'available', 'matched', 'completed', 'cancelled'
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (seller_house_id) REFERENCES houses (id) ON DELETE CASCADE
    );
    ''')

    # 5. Buy Requests (Buyers)
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS buy_requests (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        buyer_house_id INTEGER,
        energy_amount_wh REAL NOT NULL,
        remaining_energy_wh REAL NOT NULL,
        max_price_per_wh REAL NOT NULL,
        status TEXT DEFAULT 'pending', -- 'pending', 'matched', 'completed', 'cancelled'
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (buyer_house_id) REFERENCES houses (id) ON DELETE CASCADE
    );
    ''')

    # 6. Transactions
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS transactions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        listing_id INTEGER,
        buy_request_id INTEGER,
        seller_house_id INTEGER,
        buyer_house_id INTEGER,
        energy_amount_wh REAL NOT NULL,
        total_price REAL NOT NULL,
        status TEXT DEFAULT 'initiated', -- 'initiated', 'transferring', 'completed', 'failed'
        started_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        completed_at DATETIME,
        FOREIGN KEY (listing_id) REFERENCES listings (id) ON DELETE SET NULL,
        FOREIGN KEY (buy_request_id) REFERENCES buy_requests (id) ON DELETE SET NULL,
        FOREIGN KEY (seller_house_id) REFERENCES houses (id) ON DELETE SET NULL,
        FOREIGN KEY (buyer_house_id) REFERENCES houses (id) ON DELETE SET NULL
    );
    ''')

    # 7. System and Device Logs
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        log_level TEXT NOT NULL, -- 'INFO', 'WARNING', 'ERROR'
        message TEXT NOT NULL,
        source TEXT NOT NULL, -- 'server', 'node_X'
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
    );
    ''')

    conn.commit()
    
    # Check if we need to seed the database with mock data
    cursor.execute("SELECT COUNT(*) FROM users;")
    if cursor.fetchone()[0] == 0:
        seed_mock_data(cursor)
        conn.commit()

    conn.close()
    print("Database initialized successfully.")

def seed_mock_data(cursor):
    print("Seeding database with mock users and houses...")
    
    # Create default users: admin, seller, buyer
    users = [
        ('admin', generate_password_hash('admin123'), 'admin@urrja.org', 'admin', 5000.0),
        ('house1_owner', generate_password_hash('urrja123'), 'house1@urrja.org', 'user', 1000.0),
        ('house2_owner', generate_password_hash('urrja123'), 'house2@urrja.org', 'user', 500.0),
        ('house3_owner', generate_password_hash('urrja123'), 'house3@urrja.org', 'user', 800.0)
    ]
    cursor.executemany('''
        INSERT INTO users (username, password_hash, email, role, balance)
        VALUES (?, ?, ?, ?, ?);
    ''', users)

    # Fetch user IDs
    cursor.execute("SELECT id, username FROM users;")
    user_map = {row['username']: row['id'] for row in cursor.fetchall()}

    # Create houses corresponding to users
    houses = [
        (user_map['house1_owner'], 'Smart Villa 101', 'token_node_101', 'offline', 1200.0),
        (user_map['house2_owner'], 'Eco Cottage 202', 'token_node_202', 'offline', 1000.0),
        (user_map['house3_owner'], 'Solar Duplex 303', 'token_node_303', 'offline', 1500.0)
    ]
    cursor.executemany('''
        INSERT INTO houses (user_id, house_name, device_token, status, battery_capacity)
        VALUES (?, ?, ?, ?, ?);
    ''', houses)

    # Insert system logs
    cursor.execute('''
        INSERT INTO logs (log_level, message, source)
        VALUES ('INFO', 'System seeded with default users and community houses.', 'server');
    ''')

if __name__ == '__main__':
    init_db()
