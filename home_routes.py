from flask import Blueprint, render_template, session, redirect, url_for
import os
import psycopg
from usage_limit import peek_usage

home_bp = Blueprint('home', __name__)


def get_conn():
    """Konek ke Postgres yang sama dipakai auth_service.py / rembg_flask.py / usage_limit.py."""
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


# Daftar fitur ditulis statis di sini (bukan di-query) - meta-extract sengaja
# gak nge-track apapun (stateless), jadi gak punya usage/history buat ditampilin,
# cukup jadi link biasa di landing page & TIDAK muncul di dashboard.
FEATURES = [
    {
        'key': 'rembg',
        'name': 'Remove Background',
        'desc': 'Hapus background gambar otomatis pakai AI (isnet-general-use).',
        'url': '/rembg/',
        'tracked': True,
    },
    {
        'key': 'ocr',
        'name': 'OCR - Scan Teks',
        'desc': 'Ekstrak teks dari gambar (PaddleOCR).',
        'url': '/ocr/',
        'tracked': True,
    },
    {
        'key': 'meta-extract',
        'name': 'Metadata Extractor',
        'desc': 'Lihat info EXIF & metadata gambar (format, ukuran, GPS, dll).',
        'url': '/meta-extract',
        'tracked': False,
    },
]


@home_bp.route('/')
def home():
    return render_template(
        'home.html',
        features=FEATURES,
        is_login=session.get('is_login', False),
        username=session.get('username'),
    )


def _get_rembg_history(user_id, limit=5):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT id, file_id, original_filename, created_at
                   FROM rembg_history WHERE user_id=%s
                   ORDER BY created_at DESC LIMIT %s""",
                (user_id, limit)
            )
            rows = cur.fetchall()
    return [
        {'id': r[0], 'file_id': r[1], 'filename': r[2], 'created_at': r[3]}
        for r in rows
    ]


@home_bp.route('/dashboard')
def dashboard():
    # gated: harus login. next dibawa balik ke sini kalau abis itu diarahkan login dulu.
    if not session.get('is_login') or not session.get('user_id'):
        return redirect(url_for('login', next='/dashboard'))

    usage = {
        'rembg': peek_usage('rembg'),
        'ocr': peek_usage('ocr'),
    }

    try:
        history = _get_rembg_history(session['user_id'])
    except Exception as e:
        print(f"[dashboard] gagal ambil riwayat rembg: {e}")
        history = []

    # dashboard cuma nampilin fitur yang tracked (rembg, ocr) - meta-extract
    # sengaja gak dikasih kartu quota/history karena memang gak ada datanya.
    tracked_features = [f for f in FEATURES if f['tracked']]

    return render_template(
        'dashboard.html',
        username=session.get('username'),
        role=session.get('role', 'user'),
        usage=usage,
        history=history,
        features=tracked_features,
    )
