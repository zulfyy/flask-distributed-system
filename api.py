from flask import Flask, render_template, request, flash, redirect, session, url_for, jsonify
from flask_session import Session
from datetime import timedelta
import redis
# from flask_sqlalchemy import SQLAlchemy
import psycopg
import os

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY_FLASK", "dev_secret_key001")
app.config['SESSION_TYPE'] = 'redis' 
app.config['SESSION_PERMANENT'] = True
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(minutes=30)
redis_url = os.getenv("REDIS_HOST", "redis://localhost:6379")
app.config['SESSION_REDIS'] = redis.from_url(redis_url)

DB_URI = os.getenv("DATABASE_HOST", default=f"postgresql://user_upload:%40password_aman@localhost:5432/upload_db")

# app.config['SQLALCHEMY_DATABASE_URI'] = 'postgresql+psycopg://user_upload:@password_aman@pg-cluster-rw:5432/upload_db'


'''
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
    # Wajib di Cloud-Native: Cegah error "Server closed the connection unexpectedly" saat auto-failover
    'pool_pre_ping': True, 
    
    # Sesuaikan dengan PgBouncer. Jika PgBouncer memakai mode 'transaction', 
    # pool_size di sisi aplikasi bisa dibuat moderat.
    'pool_size': 10,
    'max_overflow': 20,
    
    # Tutup dan buat ulang koneksi tiap 1 jam agar tidak ada koneksi "zombie"
    'pool_recycle': 3600, 
}
'''

Session(app)  # init Flask-Session
# db = SQLAlchemy(app)


def login_required(f):
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'is_login' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated


@app.route('/login/', methods=['GET','POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        try:
            with psycopg.connect(DB_URI) as conn:
                with conn.cursor() as cur:
                    query = "SELECT * FROM account where username=%s AND password=%s";
                    cur.execute(query, (username, password))

                    user = cur.fetchone()
                    if user:
                        session['username'] = username
                        session['is_login'] = True
                        # return redirect(url_for('dashboard'))  # arahkan ke halaman lain
                        return jsonify({
                            "status": "Login Berhasil",
                            "data": {
                                "id": user[0],
                                "username": user[1],
                                "is_login": session.get('is_login'),
                                "created_at": user[3]
                            }
                        }), 200
                    else:
                        return jsonify({"status": "Gagal", "pesan": "Username atau password salah!"}), 401
            print('hi')

        except Exception as e:
            return jsonify({"status": "Error Sistem", "pesan": str(e)}), 500

    return render_template("api/login.html")

@app.route('/dashboard')
@login_required
def dashboard():
    return 'hi'

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False)

