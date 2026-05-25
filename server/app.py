import os
import sqlite3
from datetime import datetime
from flask import Flask, request, jsonify, render_template, redirect, url_for, session, flash
from werkzeug.security import check_password_hash, generate_password_hash
from database import init_db, get_db_connection

app = Flask(__name__)
app.secret_key = 'urrja_secret_key_for_session_management'

# Initialize database on app startup
init_db()

# --- Helper Functions ---
def log_event(level, message, source='server'):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO logs (log_level, message, source) VALUES (?, ?, ?);",
        (level, message, source)
    )
    conn.commit()
    conn.close()

def match_listings_and_requests():
    """
    Automated P2P Matching Engine.
    Matches available seller listings with pending buyer requests.
    Calculates overlapping quantities and locks energy transfer.
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # 1. Fetch available listings (cheapest first, then oldest)
    cursor.execute('''
        SELECT l.*, h.user_id as seller_user_id, h.id as seller_house_id
        FROM listings l
        JOIN houses h ON l.seller_house_id = h.id
        WHERE l.status = 'available' AND l.remaining_energy_wh > 0
        ORDER BY l.price_per_wh ASC, l.created_at ASC;
    ''')
    listings = [dict(row) for row in cursor.fetchall()]

    # 2. Fetch pending buy requests (highest offer first, then oldest)
    cursor.execute('''
        SELECT r.*, h.user_id as buyer_user_id, h.id as buyer_house_id, u.balance as buyer_balance
        FROM buy_requests r
        JOIN houses h ON r.buyer_house_id = h.id
        JOIN users u ON h.user_id = u.id
        WHERE r.status = 'pending' AND r.remaining_energy_wh > 0
        ORDER BY r.max_price_per_wh DESC, r.created_at ASC;
    ''')
    requests_list = [dict(row) for row in cursor.fetchall()]

    matches_made = 0

    for req in requests_list:
        if req['remaining_energy_wh'] <= 0:
            continue
            
        buyer_house_id = req['buyer_house_id']
        buyer_user_id = req['buyer_user_id']
        buyer_balance = req['buyer_balance']

        for lst in listings:
            if lst['remaining_energy_wh'] <= 0:
                continue
            
            seller_house_id = lst['seller_house_id']
            seller_user_id = lst['seller_user_id']

            # Rule 1: A house cannot trade with itself
            if buyer_house_id == seller_house_id:
                continue

            # Rule 2: Price agreement (Seller price <= Buyer max price)
            if lst['price_per_wh'] > req['max_price_per_wh']:
                continue

            # Calculate matched trade energy
            matched_energy = min(lst['remaining_energy_wh'], req['remaining_energy_wh'])
            if matched_energy <= 0.01:
                continue

            trade_price = lst['price_per_wh']
            total_price = matched_energy * trade_price

            # Rule 3: Check buyer's financial balance
            if buyer_balance < total_price:
                # Buyer cannot afford. Log event and cancel request
                cursor.execute(
                    "UPDATE buy_requests SET status = 'cancelled' WHERE id = ?;",
                    (req['id'],)
                )
                cursor.execute(
                    "INSERT INTO logs (log_level, message, source) VALUES (?, ?, ?);",
                    ('WARNING', f"Buy request #{req['id']} cancelled: insufficient user balance.", 'server')
                )
                break # Move to next request since this one is cancelled

            # Initiate transaction
            cursor.execute('''
                INSERT INTO transactions (listing_id, buy_request_id, seller_house_id, buyer_house_id, energy_amount_wh, total_price, status)
                VALUES (?, ?, ?, ?, ?, ?, 'initiated');
            ''', (lst['id'], req['id'], seller_house_id, buyer_house_id, matched_energy, total_price))
            
            transaction_id = cursor.lastrowid

            # Deduct remaining energy amounts
            new_lst_remaining = lst['remaining_energy_wh'] - matched_energy
            lst_status = 'matched' if new_lst_remaining <= 0.01 else 'available'
            cursor.execute(
                "UPDATE listings SET remaining_energy_wh = ?, status = ? WHERE id = ?;",
                (new_lst_remaining, lst_status, lst['id'])
            )
            lst['remaining_energy_wh'] = new_lst_remaining # Update local array state

            new_req_remaining = req['remaining_energy_wh'] - matched_energy
            req_status = 'matched' if new_req_remaining <= 0.01 else 'pending'
            cursor.execute(
                "UPDATE buy_requests SET remaining_energy_wh = ?, status = ? WHERE id = ?;",
                (new_req_remaining, req_status, req['id'])
            )
            req['remaining_energy_wh'] = new_req_remaining # Update local state
            buyer_balance -= total_price # Update local balance for subsequent loops

            # Update statuses of houses
            cursor.execute("UPDATE houses SET status = 'transferring' WHERE id IN (?, ?);", (seller_house_id, buyer_house_id))

            cursor.execute(
                "INSERT INTO logs (log_level, message, source) VALUES (?, ?, ?);",
                ('INFO', f"Matched Listing #{lst['id']} & Request #{req['id']}: Traded {matched_energy:.1f}Wh @ {trade_price:.2f}/Wh. Transaction ID: #{transaction_id}.", 'server')
            )
            
            matches_made += 1
            if req['remaining_energy_wh'] <= 0.01:
                break # Request fully fulfilled, move to next request

    conn.commit()
    conn.close()
    return matches_made

# --- HTTP UI Routes ---

@app.route('/')
def index():
    if 'user_id' in session:
        return redirect(url_for('dashboard'))
    return redirect(url_for('login_page'))

@app.route('/login', methods=['GET', 'POST'])
def login_page():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        conn = get_db_connection()
        user = conn.execute("SELECT * FROM users WHERE username = ?;", (username,)).fetchone()
        conn.close()
        
        if user and check_password_hash(user['password_hash'], password):
            session['user_id'] = user['id']
            session['username'] = user['username']
            session['role'] = user['role']
            flash('Successfully logged in!', 'success')
            return redirect(url_for('dashboard'))
        else:
            flash('Invalid username or password.', 'error')
            
    return render_template('login.html')

@app.route('/signup', methods=['POST'])
def signup_action():
    username = request.form.get('username')
    email = request.form.get('email')
    password = request.form.get('password')
    house_name = request.form.get('house_name')
    
    if not username or not password or not house_name:
        flash('Username, password, and house name are required.', 'error')
        return redirect(url_for('login_page'))
        
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Check duplicate
    exists = cursor.execute("SELECT id FROM users WHERE username = ?;", (username,)).fetchone()
    if exists:
        flash('Username already exists.', 'error')
        conn.close()
        return redirect(url_for('login_page'))
        
    hashed_pwd = generate_password_hash(password)
    
    try:
        # Create user
        cursor.execute(
            "INSERT INTO users (username, password_hash, email, role, balance) VALUES (?, ?, ?, 'user', 1000.0);",
            (username, hashed_pwd, email)
        )
        user_id = cursor.lastrowid
        
        # Create corresponding House node with random device token for prototype
        device_token = f"token_node_{username}_{hash(username) & 0xffff}"
        cursor.execute(
            "INSERT INTO houses (user_id, house_name, device_token, status) VALUES (?, ?, ?, 'offline');",
            (user_id, house_name, device_token)
        )
        conn.commit()
        flash(f'Account created! Your Device Token is: {device_token}. Keep it safe for flashing your ESP32.', 'success')
    except Exception as e:
        flash(f'Error registering user: {str(e)}', 'error')
    finally:
        conn.close()
        
    return redirect(url_for('login_page'))

@app.route('/logout')
def logout():
    session.clear()
    flash('Logged out.', 'info')
    return redirect(url_for('login_page'))

@app.route('/dashboard')
def dashboard():
    if 'user_id' not in session:
        return redirect(url_for('login_page'))
    return render_template('dashboard.html', active_tab='dashboard')

@app.route('/seller')
def seller():
    if 'user_id' not in session:
        return redirect(url_for('login_page'))
    return render_template('seller.html', active_tab='seller')

@app.route('/marketplace')
def marketplace():
    if 'user_id' not in session:
        return redirect(url_for('login_page'))
    return render_template('marketplace.html', active_tab='marketplace')

@app.route('/devices')
def devices():
    if 'user_id' not in session:
        return redirect(url_for('login_page'))
    return render_template('devices.html', active_tab='devices')

@app.route('/transactions')
def transactions():
    if 'user_id' not in session:
        return redirect(url_for('login_page'))
    return render_template('transactions.html', active_tab='transactions')

@app.route('/admin')
def admin():
    if 'user_id' not in session:
        return redirect(url_for('login_page'))
    if session.get('role') != 'admin':
        flash('Access denied: Administrator privileges required.', 'error')
        return redirect(url_for('dashboard'))
    return render_template('admin.html', active_tab='admin')


# --- REST API Endpoints ---

@app.route('/api/user/profile')
def api_profile():
    if 'user_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    
    conn = get_db_connection()
    user = conn.execute("SELECT id, username, email, role, balance FROM users WHERE id = ?;", (session['user_id'],)).fetchone()
    house = conn.execute("SELECT * FROM houses WHERE user_id = ?;", (session['user_id'],)).fetchone()
    
    user_dict = dict(user) if user else {}
    house_dict = dict(house) if house else {}
    
    conn.close()
    return jsonify({
        'user': user_dict,
        'house': house_dict
    })

@app.route('/api/listings', methods=['GET', 'POST'])
def api_listings():
    if 'user_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
        
    conn = get_db_connection()
    
    if request.method == 'POST':
        # Create listing
        data = request.get_json() or {}
        energy = float(data.get('energy', 0))
        price = float(data.get('price', 0))
        
        if energy <= 0 or price <= 0:
            return jsonify({'error': 'Invalid energy or price values.'}), 400
            
        house = conn.execute("SELECT id FROM houses WHERE user_id = ?;", (session['user_id'],)).fetchone()
        if not house:
            return jsonify({'error': 'No registered house found for this user.'}), 400
            
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO listings (seller_house_id, energy_amount_wh, remaining_energy_wh, price_per_wh, status)
            VALUES (?, ?, ?, ?, 'available');
        ''', (house['id'], energy, energy, price))
        conn.commit()
        
        log_event('INFO', f"Listing created: {energy} Wh @ {price}/Wh by House #{house['id']}.")
        
        conn.close()
        # Trigger matching engine
        match_listings_and_requests()
        return jsonify({'status': 'Listing created successfully.'})
        
    # GET listings
    # Show active listings
    rows = conn.execute('''
        SELECT l.*, h.house_name, u.username as owner
        FROM listings l
        JOIN houses h ON l.seller_house_id = h.id
        JOIN users u ON h.user_id = u.id
        WHERE l.status = 'available'
        ORDER BY l.created_at DESC;
    ''').fetchall()
    
    listings = [dict(r) for r in rows]
    conn.close()
    return jsonify({'listings': listings})

@app.route('/api/buy_requests', methods=['GET', 'POST'])
def api_buy_requests():
    if 'user_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
        
    conn = get_db_connection()
    
    if request.method == 'POST':
        # Create buy request
        data = request.get_json() or {}
        energy = float(data.get('energy', 0))
        max_price = float(data.get('max_price', 0))
        
        if energy <= 0 or max_price <= 0:
            return jsonify({'error': 'Invalid energy or price values.'}), 400
            
        house = conn.execute("SELECT id FROM houses WHERE user_id = ?;", (session['user_id'],)).fetchone()
        if not house:
            return jsonify({'error': 'No registered house found for this user.'}), 400
            
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO buy_requests (buyer_house_id, energy_amount_wh, remaining_energy_wh, max_price_per_wh, status)
            VALUES (?, ?, ?, ?, 'pending');
        ''', (house['id'], energy, energy, max_price))
        conn.commit()
        
        log_event('INFO', f"Buy request created: {energy} Wh @ max {max_price}/Wh by House #{house['id']}.")
        
        conn.close()
        # Trigger matching engine
        match_listings_and_requests()
        return jsonify({'status': 'Buy request created successfully.'})
        
    # GET requests
    rows = conn.execute('''
        SELECT r.*, h.house_name, u.username as owner
        FROM buy_requests r
        JOIN houses h ON r.buyer_house_id = h.id
        JOIN users u ON h.user_id = u.id
        WHERE r.status = 'pending'
        ORDER BY r.created_at DESC;
    ''').fetchall()
    
    requests_list = [dict(r) for r in rows]
    conn.close()
    return jsonify({'requests': requests_list})

@app.route('/api/transactions')
def api_transactions():
    if 'user_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
        
    conn = get_db_connection()
    
    # Optional filter: ?limit=10 or user-specific transactions
    limit = request.args.get('limit', 50, type=int)
    
    rows = conn.execute('''
        SELECT t.*, 
               sh.house_name as seller_house, su.username as seller_owner,
               bh.house_name as buyer_house, bu.username as buyer_owner
        FROM transactions t
        JOIN houses sh ON t.seller_house_id = sh.id
        JOIN users su ON sh.user_id = su.id
        JOIN houses bh ON t.buyer_house_id = bh.id
        JOIN users bu ON bh.user_id = bu.id
        ORDER BY t.started_at DESC
        LIMIT ?;
    ''', (limit,)).fetchall()
    
    txs = [dict(r) for r in rows]
    conn.close()
    return jsonify({'transactions': txs})

@app.route('/api/devices')
def api_devices():
    if 'user_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
        
    conn = get_db_connection()
    rows = conn.execute('''
        SELECT h.*, u.username as owner,
               (SELECT battery_soc FROM energy_readings WHERE house_id = h.id ORDER BY timestamp DESC LIMIT 1) as last_soc,
               (SELECT power FROM energy_readings WHERE house_id = h.id ORDER BY timestamp DESC LIMIT 1) as last_power,
               (SELECT available_surplus FROM energy_readings WHERE house_id = h.id ORDER BY timestamp DESC LIMIT 1) as last_surplus,
               (SELECT timestamp FROM energy_readings WHERE house_id = h.id ORDER BY timestamp DESC LIMIT 1) as last_reading_time
        FROM houses h
        JOIN users u ON h.user_id = u.id;
    ''').fetchall()
    
    devices = [dict(r) for r in rows]
    conn.close()
    return jsonify({'devices': devices})

@app.route('/api/admin/overview')
def api_admin_overview():
    if 'user_id' not in session or session.get('role') != 'admin':
        return jsonify({'error': 'Unauthorized'}), 401
        
    conn = get_db_connection()
    
    total_users = conn.execute("SELECT COUNT(*) FROM users;").fetchone()[0]
    total_houses = conn.execute("SELECT COUNT(*) FROM houses;").fetchone()[0]
    total_energy_traded = conn.execute("SELECT SUM(energy_amount_wh) FROM transactions WHERE status = 'completed';").fetchone()[0] or 0.0
    total_revenue = conn.execute("SELECT SUM(total_price) FROM transactions WHERE status = 'completed';").fetchone()[0] or 0.0
    
    active_trans = conn.execute("SELECT COUNT(*) FROM transactions WHERE status IN ('initiated', 'transferring');").fetchone()[0]
    completed_trans = conn.execute("SELECT COUNT(*) FROM transactions WHERE status = 'completed';").fetchone()[0]
    
    # Recent logs
    log_rows = conn.execute("SELECT * FROM logs ORDER BY timestamp DESC LIMIT 20;").fetchall()
    system_logs = [dict(r) for r in log_rows]
    
    conn.close()
    
    return jsonify({
        'stats': {
            'total_users': total_users,
            'total_houses': total_houses,
            'total_energy_traded': round(total_energy_traded, 1),
            'total_revenue': round(total_revenue, 2),
            'active_trades': active_trans,
            'completed_trades': completed_trans
        },
        'logs': system_logs
    })

# --- ESP32 Node API (Hardware Interface) ---

@app.route('/api/node/telemetry', methods=['POST'])
def api_node_telemetry():
    """
    HTTP POST Endpoint for ESP32 energy nodes.
    Receives JSON telemetry, updates node status, handles transfer state changes.
    """
    data = request.get_json() or {}
    device_token = data.get('device_token')
    
    if not device_token:
        return jsonify({'error': 'Missing device token.'}), 400
        
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # 1. Verify house token
    house = cursor.execute("SELECT * FROM houses WHERE device_token = ?;", (device_token,)).fetchone()
    if not house:
        conn.close()
        return jsonify({'error': 'Invalid device token.'}), 401
        
    house_id = house['id']
    voltage = float(data.get('voltage', 0))
    current = float(data.get('current', 0))
    power = float(data.get('power', 0))
    soc = float(data.get('soc', 0))
    surplus = float(data.get('surplus', 0))
    ip_addr = request.remote_addr
    
    # 2. Record telemetry in energy_readings
    cursor.execute('''
        INSERT INTO energy_readings (house_id, battery_voltage, battery_current, power, battery_soc, available_surplus)
        VALUES (?, ?, ?, ?, ?, ?);
    ''', (house_id, voltage, current, power, soc, surplus))

    # 3. Update house networking metadata and set online status (unless transferring)
    current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    new_status = house['status']
    if new_status not in ['transferring', 'offline']:
        new_status = 'online'
    elif new_status == 'offline':
        new_status = 'online'
        
    cursor.execute('''
        UPDATE houses 
        SET status = ?, ip_address = ?, last_seen = ? 
        WHERE id = ?;
    ''', (new_status, ip_addr, current_time, house_id))

    # 4. Check for active P2P transactions involving this house
    # We need to process trade states (Initiated -> Transferring -> Completed)
    response_cmd = 'idle'
    tx_id = None
    duration = 30 # Simulated transfer duration in seconds

    # A. Check if this house is a Seller with a transaction that is 'initiated'
    # If initiated, we command the Seller to start transferring energy.
    tx_init = cursor.execute('''
        SELECT * FROM transactions 
        WHERE seller_house_id = ? AND status = 'initiated' 
        LIMIT 1;
    ''', (house_id,)).fetchone()

    if tx_init:
        # Move transaction state to transferring
        cursor.execute(
            "UPDATE transactions SET status = 'transferring', started_at = ? WHERE id = ?;",
            (current_time, tx_init['id'])
        )
        # Set seller house status to transferring
        cursor.execute("UPDATE houses SET status = 'transferring' WHERE id = ?;", (house_id,))
        # Set buyer house status to transferring
        cursor.execute("UPDATE houses SET status = 'transferring' WHERE id = ?;", (tx_init['buyer_house_id'],))
        
        cursor.execute(
            "INSERT INTO logs (log_level, message, source) VALUES (?, ?, ?);",
            ('INFO', f"Transaction #{tx_init['id']} transfer started. Activating output load relay at Seller House #{house_id}.", f"node_{house_id}")
        )
        response_cmd = 'transfer_start'
        tx_id = tx_init['id']
    else:
        # B. Check if this house is currently 'transferring' and verify time elapsed
        tx_trans = cursor.execute('''
            SELECT * FROM transactions 
            WHERE (seller_house_id = ? OR buyer_house_id = ?) AND status = 'transferring'
            LIMIT 1;
        ''', (house_id, house_id)).fetchone()

        if tx_trans:
            # Check elapsed time
            started_time = datetime.strptime(tx_trans['started_at'], '%Y-%m-%d %H:%M:%S')
            elapsed = (datetime.now() - started_time).total_seconds()
            
            if elapsed >= duration:
                # Simulated transfer duration finished! Settle funds and complete trade.
                tx_id = tx_trans['id']
                energy = tx_trans['energy_amount_wh']
                price = tx_trans['total_price']
                seller_id = tx_trans['seller_house_id']
                buyer_id = tx_trans['buyer_house_id']

                # Settle balances in users table
                # Fetch user ids
                seller_user = cursor.execute("SELECT user_id FROM houses WHERE id = ?;", (seller_id,)).fetchone()
                buyer_user = cursor.execute("SELECT user_id FROM houses WHERE id = ?;", (buyer_id,)).fetchone()

                if seller_user and buyer_user:
                    # Subtract from buyer
                    cursor.execute("UPDATE users SET balance = balance - ? WHERE id = ?;", (price, buyer_user['user_id']))
                    # Add to seller
                    cursor.execute("UPDATE users SET balance = balance + ? WHERE id = ?;", (price, seller_user['user_id']))

                # Complete Transaction
                cursor.execute(
                    "UPDATE transactions SET status = 'completed', completed_at = ? WHERE id = ?;",
                    (current_time, tx_id)
                )
                
                # Reset house statuses back to online
                cursor.execute("UPDATE houses SET status = 'online' WHERE id IN (?, ?);", (seller_id, buyer_id))
                
                cursor.execute(
                    "INSERT INTO logs (log_level, message, source) VALUES (?, ?, ?);",
                    ('INFO', f"Transaction #{tx_id} completed. Transferred {energy:.1f}Wh. Settled transaction volume of {price:.2f} tokens.", 'server')
                )
                
                if house_id == seller_id:
                    response_cmd = 'transfer_stop'
            else:
                # Still transferring
                if house_id == tx_trans['seller_house_id']:
                    response_cmd = 'transfer_start'
                    tx_id = tx_trans['id']

    conn.commit()
    conn.close()
    
    return jsonify({
        'status': 'ok',
        'command': response_cmd,
        'transaction_id': tx_id,
        'duration': duration
    })

# Main execution
if __name__ == '__main__':
    # Listen on all interfaces so ESP32 on the network can connect
    app.run(host='0.0.0.0', port=5000, debug=True)
