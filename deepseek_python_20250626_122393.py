import sqlite3
from flask import Flask, render_template, request, redirect, url_for, session, flash
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user
from twilio.rest import Client
import stripe
from flask_babel import Babel, _
import os
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = 'your_super_secret_key'

# Configurations
app.config['UPLOAD_FOLDER'] = 'static/menu_images'
app.config['BABEL_DEFAULT_LOCALE'] = 'fr'
app.config['SUPPORTED_LANGUAGES'] = ['fr', 'en']

# Initialize extensions
login_manager = LoginManager(app)
babel = Babel(app)
stripe.api_key = "sk_test_your_stripe_key"
twilio_client = Client("your_twilio_sid", "your_twilio_token")

# Database setup
def init_db():
    conn = sqlite3.connect('restaurant.db')
    cursor = conn.cursor()
    
    # Create tables
    cursor.executescript('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            role TEXT NOT NULL
        );
        
        CREATE TABLE IF NOT EXISTS reservations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT NOT NULL,
            phone TEXT NOT NULL,
            guests INTEGER NOT NULL,
            date TEXT NOT NULL,
            time TEXT NOT NULL,
            table_id INTEGER,
            special_request TEXT,
            is_proposal BOOLEAN DEFAULT 0,
            status TEXT DEFAULT 'pending',
            FOREIGN KEY (table_id) REFERENCES tables(id)
        );
        
        CREATE TABLE IF NOT EXISTS tables (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            number TEXT NOT NULL UNIQUE,
            capacity INTEGER NOT NULL,
            location TEXT NOT NULL,
            status TEXT DEFAULT 'available'
        );
        
        CREATE TABLE IF NOT EXISTS menu (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            description TEXT,
            price REAL NOT NULL,
            category TEXT NOT NULL,
            is_spicy BOOLEAN DEFAULT 0,
            is_special BOOLEAN DEFAULT 0,
            image_path TEXT
        );
        
        CREATE TABLE IF NOT EXISTS reviews (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            reservation_id INTEGER,
            rating INTEGER CHECK(rating BETWEEN 1 AND 5),
            comment TEXT,
            FOREIGN KEY (reservation_id) REFERENCES reservations(id)
        );
    ''')
    
    # Add admin user if not exists
    try:
        cursor.execute("INSERT INTO users (username, password, role) VALUES (?, ?, ?)",
                      ('admin', 'securepassword', 'admin'))
    except sqlite3.IntegrityError:
        pass
    
    conn.commit()
    conn.close()

# User class for authentication
class User(UserMixin):
    pass

@login_manager.user_loader
def load_user(user_id):
    conn = sqlite3.connect('restaurant.db')
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,))
    user_data = cursor.fetchone()
    conn.close()
    
    if user_data:
        user = User()
        user.id = user_data[0]
        return user
    return None

# Routes
@app.route('/')
def home():
    return render_template('index.html')

@app.route('/reserve', methods=['GET', 'POST'])
def reserve():
    if request.method == 'POST':
        # Process reservation form
        name = request.form['name']
        email = request.form['email']
        phone = request.form['phone']
        guests = int(request.form['guests'])
        date = request.form['date']
        time = request.form['time']
        table_id = request.form.get('table_id')
        special_request = request.form.get('special_request', '')
        is_proposal = 1 if 'is_proposal' in request.form else 0
        
        # Save to database
        conn = sqlite3.connect('restaurant.db')
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO reservations (name, email, phone, guests, date, time, table_id, special_request, is_proposal)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (name, email, phone, guests, date, time, table_id, special_request, is_proposal))
        
        # Update table status
        if table_id:
            cursor.execute("UPDATE tables SET status = 'reserved' WHERE id = ?", (table_id,))
        
        conn.commit()
        conn.close()
        
        # Send SMS confirmation
        try:
            twilio_client.messages.create(
                body=f"Merci pour votre réservation chez Dragon Pearl Lyon! Nous vous attendons le {date} à {time}.",
                from_="+33612345678",
                to=phone
            )
        except Exception as e:
            print(f"Failed to send SMS: {e}")
        
        flash('Votre réservation a été confirmée!', 'success')
        return redirect(url_for('home'))
    
    # GET request - show available tables
    conn = sqlite3.connect('restaurant.db')
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM tables WHERE status = 'available'")
    available_tables = cursor.fetchall()
    conn.close()
    
    return render_template('reserve.html', tables=available_tables)

@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        conn = sqlite3.connect('restaurant.db')
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE username = ? AND password = ?", (username, password))
        user = cursor.fetchone()
        conn.close()
        
        if user:
            user_obj = User()
            user_obj.id = user[0]
            login_user(user_obj)
            return redirect(url_for('admin_dashboard'))
        else:
            flash('Identifiants incorrects', 'danger')
    
    return render_template('admin/login.html')

@app.route('/admin/dashboard')
@login_required
def admin_dashboard():
    conn = sqlite3.connect('restaurant.db')
    cursor = conn.cursor()
    
    # Get stats
    cursor.execute("SELECT COUNT(*) FROM reservations WHERE date(date) = date('now')")
    today_reservations = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM reservations WHERE is_proposal = 1")
    total_proposals = cursor.fetchone()[0]
    
    # Get recent reservations
    cursor.execute("SELECT * FROM reservations ORDER BY date DESC LIMIT 5")
    recent_reservations = cursor.fetchall()
    
    conn.close()
    
    return render_template('admin/dashboard.html',
                         today_reservations=today_reservations,
                         total_proposals=total_proposals,
                         recent_reservations=recent_reservations)

if __name__ == '__main__':
    init_db()
    # Create upload folder if not exists
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    app.run(debug=True)