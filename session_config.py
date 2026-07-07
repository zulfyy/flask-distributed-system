import os
from dotenv import load_dotenv

# Cari file .env di working directory dan load ke os.environ.
# Aman dipasang permanen: kalau file .env nggak ada (misal di prod pakai Doppler),
# fungsi ini diem aja dan os.getenv() tetap baca dari env yang udah disuntik duluan.
# Default override=False juga bikin dia nggak akan nimpa env var yang udah ke-set.
load_dotenv()

import redis
from flask_session import Session
from datetime import timedelta


def init_shared_session(app):
    secret = os.getenv("APP_SECRET_KEY")
    if not secret:
        raise RuntimeError("APP_SECRET_KEY belum ke-set — cek .env lokal / Doppler sync")

    redis_url = os.getenv("REDIS_HOST")
    if not redis_url:
        raise RuntimeError("REDIS_HOST belum ke-set — cek .env lokal / Doppler sync")

    app.secret_key = secret
    app.config['SESSION_TYPE'] = 'redis'
    app.config['SESSION_PERMANENT'] = True
    app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(minutes=30)
    app.config['SESSION_REDIS'] = redis.from_url(redis_url)
    app.config['SESSION_USE_SIGNER'] = True          # cookie cuma isi session-id yg di-sign, bukan raw
    # default None (bukan domain produksi) — biar dev lokal/testing pakai IP atau
    # localhost otomatis jalan pakai host-only cookie tanpa perlu override manual.
    # Di prod, wajib di-set eksplisit lewat env COOKIE_DOMAIN=.akarstack.me
    cookie_domain = os.getenv("COOKIE_DOMAIN", "").strip()
    app.config['SESSION_COOKIE_NAME'] = 'akarstack_session'
    app.config['SESSION_COOKIE_DOMAIN'] = cookie_domain if cookie_domain else None

    app_mode = os.getenv("APP_MODE", "DEVELOPMENT").strip().upper()
    app.config['SESSION_COOKIE_SECURE'] = app_mode == "PRODUCTION"
    app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
    Session(app)

    if app_mode == "PRODUCTION" and not cookie_domain:
        app.logger.warning(
            "APP_MODE=PRODUCTION tapi COOKIE_DOMAIN kosong — "
            "session TIDAK akan ke-share lintas service/subdomain!"
        )