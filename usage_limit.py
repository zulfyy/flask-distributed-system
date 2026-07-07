import os
import uuid
from functools import wraps
from flask import session, jsonify, current_app
import psycopg

# batas pemakaian per role, reset tiap hari (tanggal berubah). None = unlimited (admin).
LIMITS = {'anon': 3, 'user': 5, 'admin': None}


def _pg_connect():
    """Konek ke Postgres yang sama dipakai auth_service.py, baca dari env yang sama."""
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


def _get_role():
    return session.get('role', 'anon')


def _get_anon_id():
    if 'anon_id' not in session:
        session['anon_id'] = uuid.uuid4().hex
    return session['anon_id']


def _usage_key(feature, anon_id):
    return f"usage:{feature}:anon:{anon_id}"


# ---------------------------------------------------------------------------
# Anon: tetap di Redis (session-scoped). Batasan ini emang bisa dilewatin
# dengan clear cookies / incognito - itu wajar & diterima, standar industri
# buat quota anonim. Yang PENTING dijaga ketat itu quota user (login).
# ---------------------------------------------------------------------------

def _peek_anon(feature, limit):
    identity = _get_anon_id()
    redis_client = current_app.config['SESSION_REDIS']
    raw = redis_client.get(_usage_key(feature, identity))
    used = int(raw) if raw else 0
    return {'role': 'anon', 'used': min(used, limit), 'limit': limit, 'exceeded': used >= limit}


def _increment_anon(feature, limit):
    identity = _get_anon_id()
    redis_client = current_app.config['SESSION_REDIS']
    key = _usage_key(feature, identity)

    raw = redis_client.get(key)
    used = int(raw) if raw else 0
    if used >= limit:
        return {'role': 'anon', 'used': used, 'limit': limit, 'exceeded': True}

    current = redis_client.incr(key)
    if current == 1:
        redis_client.expire(key, 60 * 60 * 24)
    return {'role': 'anon', 'used': current, 'limit': limit, 'exceeded': current >= limit}


# ---------------------------------------------------------------------------
# User/admin: persisten di Postgres, terikat ke user_id. Gak bisa direset
# cuma dengan logout/login karena bukan session/Redis key, tapi row di DB
# yang nempel ke akun - reset otomatis begitu usage_date != hari ini.
# ---------------------------------------------------------------------------

def _peek_user_db(feature, user_id, limit):
    with _pg_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT count FROM usage_log WHERE user_id=%s AND feature=%s AND usage_date=CURRENT_DATE",
                (user_id, feature)
            )
            row = cur.fetchone()
    used = row[0] if row else 0
    return {'role': _get_role(), 'used': min(used, limit), 'limit': limit, 'exceeded': used >= limit}


def _increment_user_db(feature, user_id, limit):
    with _pg_connect() as conn:
        with conn.cursor() as cur:
            # pastiin row hari ini ada (idempotent kalau udah ada)
            cur.execute("""
                INSERT INTO usage_log (user_id, feature, usage_date, count)
                VALUES (%s, %s, CURRENT_DATE, 0)
                ON CONFLICT (user_id, feature, usage_date) DO NOTHING
            """, (user_id, feature))

            # lock row ini biar aman kalau ada 2 request barengan (race condition)
            cur.execute(
                "SELECT count FROM usage_log WHERE user_id=%s AND feature=%s AND usage_date=CURRENT_DATE FOR UPDATE",
                (user_id, feature)
            )
            used = cur.fetchone()[0]

            if used >= limit:
                conn.commit()
                return {'role': _get_role(), 'used': used, 'limit': limit, 'exceeded': True}

            cur.execute(
                "UPDATE usage_log SET count = count + 1 WHERE user_id=%s AND feature=%s AND usage_date=CURRENT_DATE RETURNING count",
                (user_id, feature)
            )
            used = cur.fetchone()[0]
            conn.commit()
    return {'role': _get_role(), 'used': used, 'limit': limit, 'exceeded': used >= limit}


def _ensure_usage_log_schema():
    """
    Tabel usage_log dulu dibikin manual (makanya butuh GRANT tambahan biar
    kepake app user - lihat komentar historis di rembg_flask.py). Sekarang
    dibikin di sini, oleh app user itu sendiri, jadi otomatis jadi owner -
    gak butuh GRANT manual lagi & reproducible kalau Postgres-nya fresh
    (PVC baru / cluster baru).

    Dipanggil sekali pas module ini di-import (oleh ocr.py & rembg_flask.py).
    Sengaja RAISE kalau gagal (bukan try/except+print) - biar pod yang
    import module ini CRASH & di-restart otomatis sama Kubernetes kalau
    Postgres/tabel account belum ready, konsisten sama pola di
    auth_service.py & rembg_flask.py. Kalau ditelen diem-diem, quota
    check bakal lempar 500 ke user tiap kali OCR/rembg dipanggil, dan gak
    akan pernah kebenerin sendiri.
    """
    with _pg_connect() as conn:
        with conn.cursor() as cur:
            # Kunci biar pod lain ngantri kalau lagi barengan bikin tabel
            cur.execute("SELECT pg_advisory_lock(1001)")
                
            # 1. Pastikan tabel account ada duluan (karena jadi referensi FK)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS account (
                    id SERIAL PRIMARY KEY,
                    username VARCHAR(50) UNIQUE NOT NULL,
                    password_hash TEXT NOT NULL,
                    role VARCHAR(10) NOT NULL DEFAULT 'user' CHECK (role IN ('anon','user','admin')),
                    created_at TIMESTAMP DEFAULT NOW()
                )
            """)

            cur.execute("""
                CREATE TABLE IF NOT EXISTS usage_log (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER NOT NULL REFERENCES account(id) ON DELETE CASCADE,
                    feature VARCHAR(30) NOT NULL,
                    usage_date DATE NOT NULL,
                    count INTEGER NOT NULL DEFAULT 0,
                    UNIQUE (user_id, feature, usage_date)
                );
            """)
            cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_usage_log_lookup
                ON usage_log (user_id, feature, usage_date);
            """)

            cur.execute("SELECT pg_advisory_unlock(1001)")
            conn.commit()


_ensure_usage_log_schema()


# ---------------------------------------------------------------------------
# Entry point publik dipakai route (ocr.py dll) - sama kayak sebelumnya
# ---------------------------------------------------------------------------

def peek_usage(feature):
    """Lihat status kuota TANPA nambah counter. Aman dipanggil pas render GET."""
    role = _get_role()
    limit = LIMITS.get(role)
    if limit is None:
        return {'role': role, 'used': 0, 'limit': None, 'exceeded': False}

    if role == 'anon':
        return _peek_anon(feature, limit)

    user_id = session.get('user_id')
    if not user_id:
        # role bukan anon tapi user_id gak ada di session (kondisi ganjil) - fallback aman
        return {'role': role, 'used': 0, 'limit': limit, 'exceeded': False}
    return _peek_user_db(feature, user_id, limit)


def increment_usage(feature):
    """Nambah counter pemakaian. Panggil ini cuma pas proses beneran mau dieksekusi."""
    role = _get_role()
    limit = LIMITS.get(role)
    if limit is None:
        return {'role': role, 'used': 0, 'limit': None, 'exceeded': False}

    if role == 'anon':
        return _increment_anon(feature, limit)

    user_id = session.get('user_id')
    if not user_id:
        return {'role': role, 'used': 0, 'limit': limit, 'exceeded': False}
    return _increment_user_db(feature, user_id, limit)


def usage_limit(feature):
    """
    Versi decorator, buat endpoint API/JSON murni (misal dipanggil dari fetch/curl,
    bukan submit form HTML biasa). Kalau endpoint-nya form HTML, mending cek manual
    di dalam route pakai peek_usage()/increment_usage() biar bisa flash()+redirect,
    bukan ngirim JSON mentah ke browser.
    """
    def decorator(f):
        @wraps(f)
        def wrapped(*args, **kwargs):
            usage = increment_usage(feature)
            if usage['exceeded']:
                pesan = f"Kuota {feature} habis ({usage['limit']}x/hari)."
                if usage['role'] == 'anon':
                    pesan += " Login dulu buat kuota lebih banyak."
                return jsonify({"status": "Gagal", "pesan": pesan}), 429
            return f(*args, **kwargs)
        return wrapped
    return decorator