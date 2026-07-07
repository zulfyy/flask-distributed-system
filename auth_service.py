from flask import Flask, render_template, request, redirect, session, url_for, flash
import psycopg
import bcrypt
import os
from session_config import init_shared_session
from home_routes import home_bp

app = Flask(__name__)
init_shared_session(app)
app.register_blueprint(home_bp)

# PENTING: jangan bikin connection string manual pakai f-string kalau password
# bisa mengandung karakter spesial (spasi, @, :, /, dll) - itu bakal salah
# parse (contoh: DB_PASSWORD=@password_aman bikin URI punya 2 karakter '@',
# parser bisa salah potong userinfo/host, persis error getaddrinfo yang
# pernah muncul sebelumnya). Pakai keyword args - psycopg handle password
# mentah tanpa perlu di-encode sama sekali.

def get_conn():
    full_uri = os.getenv("DATABASE_HOST")
    if full_uri:
        return psycopg.connect(full_uri)
    return psycopg.connect(
        host=os.getenv("DB_HOST", "localhost"),
        port=os.getenv("DB_PORT", "5432"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
        dbname=os.getenv("DB_NAME"),
    )


def ensure_schema():
    # Sengaja RAISE (bukan cuma print) kalau gagal - biar container CRASH pas
    # Postgres belum ready (misal race pas cold-start cluster / CNPG belum
    # selesai bootstrap). Kubernetes bakal restart pod ini otomatis pakai
    # backoff bawaan sampai koneksi sukses & tabel kebuat. Kalau exception
    # cuma di-print & fungsi lanjut normal, pod ini keliatan "Running" padahal
    # tabel 'account' gak pernah ada - baru ketauan pas user coba login &
    # dapet error Postgres mentah, dan gak akan pernah kebenerin sendiri
    # sampai pod di-restart manual.
    with get_conn() as conn:
        with conn.cursor() as cur:
            # Gunakan ID gembok yang sama (1001)
            cur.execute("SELECT pg_advisory_lock(1001)")

            cur.execute("""
                CREATE TABLE IF NOT EXISTS account (
                    id SERIAL PRIMARY KEY,
                    username VARCHAR(50) UNIQUE NOT NULL,
                    password_hash TEXT NOT NULL,
                    role VARCHAR(10) NOT NULL DEFAULT 'user' CHECK (role IN ('anon','user','admin')),
                    created_at TIMESTAMP DEFAULT NOW()
                );
            """)
            cur.execute("SELECT pg_advisory_unlock(1001)")
            conn.commit()


def ensure_default_admin():
    admin_user = os.getenv("ADMIN_USERNAME", "admin")
    admin_pass = os.getenv("ADMIN_DEFAULT_PASSWORD")

    if not admin_pass:
        print("[seed] ADMIN_DEFAULT_PASSWORD ga di-set, skip bikin admin default")
        return

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM account WHERE username=%s", (admin_user,))
            if cur.fetchone():
                return
            password_hash = bcrypt.hashpw(admin_pass.encode(), bcrypt.gensalt()).decode()
            cur.execute(
                "INSERT INTO account (username, password_hash, role) VALUES (%s, %s, 'admin')",
                (admin_user, password_hash)
            )
            conn.commit()
            print(f"[seed] admin default '{admin_user}' dibuat")


ensure_schema()
ensure_default_admin()


def _safe_next(next_url):
    """Cegah open redirect: cuma izinin path relatif ('/ocr/'), bukan URL absolut ke domain lain."""
    if not next_url or not next_url.startswith('/') or next_url.startswith('//'):
        return '/'
    return next_url


@app.route('/auth/login', methods=['GET', 'POST'])
def login():
    next_url = _safe_next(request.values.get('next', '/'))
    tab = request.values.get('tab', 'login')

    if request.method == 'POST':
        next_url = _safe_next(request.form.get('next', '/'))
        username = request.form.get('username')
        password = request.form.get('password')

        try:
            with get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "SELECT id, username, password_hash, role FROM account WHERE username=%s",
                        (username,)
                    )
                    user = cur.fetchone()

            valid = user and bcrypt.checkpw(password.encode(), user[2].encode())

            if valid:
                session['user_id'] = user[0]
                session['username'] = user[1]
                session['role'] = user[3]
                session['is_login'] = True
                return redirect(next_url)
            else:
                flash('Username atau password salah.')
                return redirect(url_for('login', next=next_url, tab='login'))

        except Exception as e:
            flash(f'Terjadi kesalahan sistem: {e}')
            return redirect(url_for('login', next=next_url, tab='login'))

    return render_template('login.html', next=next_url, tab=tab)


@app.route('/auth/register', methods=['POST'])
def register():
    next_url = _safe_next(request.form.get('next', '/'))
    username = request.form.get('username')
    password = request.form.get('password')

    if not username or not password:
        flash('Username dan password wajib diisi.')
        return redirect(url_for('login', next=next_url, tab='register'))

    password_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()

    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO account (username, password_hash, role) VALUES (%s, %s, 'user')",
                    (username, password_hash)
                )
                conn.commit()
        flash('Akun dibuat, silakan login.')
        return redirect(url_for('login', next=next_url, tab='login'))

    except psycopg.errors.UniqueViolation:
        flash('Username sudah dipakai.')
        return redirect(url_for('login', next=next_url, tab='register'))
    except Exception as e:
        flash(f'Terjadi kesalahan sistem: {e}')
        return redirect(url_for('login', next=next_url, tab='register'))


@app.route('/auth/logout')
def logout():
    next_url = _safe_next(request.args.get('next', '/'))
    # simpen anon_id dulu sebelum clear. Kalau ikut kehapus, request abis
    # logout bakal dapet anon_id BARU -> quota Redis anon reset gratis,
    # bisa di-farming cuma dengan login/logout berulang.
    anon_id = session.get('anon_id')
    session.clear()
    if anon_id:
        session['anon_id'] = anon_id
    return redirect(next_url)


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5005, debug=False)