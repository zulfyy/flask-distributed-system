from flask import Flask, render_template, request, flash, redirect, session, url_for, send_file
from PIL import Image
from rembg import remove, new_session
import io
import os
import uuid
import psycopg
from session_config import init_shared_session
from usage_limit import peek_usage, increment_usage

app = Flask(__name__)
init_shared_session(app)
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}

app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024

UPLOAD_FOLDER = 'uploads'
RESULT_FOLDER = 'results'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(RESULT_FOLDER, exist_ok=True)

# load model sekali aja waktu server nyala, jangan tiap request
# soalnya load model ini berat, bisa bikin lemot kalo dipanggil terus
rembg_session = new_session('u2net')
#rembg_session = new_session('isnet-general-use')


def get_conn():
    """Konek ke Postgres yang sama dipakai auth_service.py / usage_limit.py."""
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


def ensure_history_schema():
    """
    Tabel riwayat hasil rembg - CUMA dipakai buat user yang login (user_id NOT NULL).
    Anon sengaja gak ditrack di sini (dibiarkan seperti sebelumnya: file tetap kebuat
    di disk dengan uuid random, tapi gak ada catatan kepemilikan/riwayat/hapus untuk anon).
    Dibuat oleh user DB app sendiri (bukan superuser terpisah), jadi otomatis jadi owner -
    gak butuh GRANT tambahan kayak kasus usage_log dulu.

    Sengaja RAISE kalau gagal (bukan cuma print) - biar container crash & di-restart
    otomatis sama Kubernetes kalau Postgres belum ready pas cold-start. Kalau exception
    ditelen di sini, pod ini keliatan sehat padahal tabel riwayat gak pernah kebuat.
    """
    with get_conn() as conn:
        with conn.cursor() as cur:
            # Pake gembok 1001 juga
            cur.execute("SELECT pg_advisory_lock(1001)")
            # 1. Pastikan tabel account ada dulu (karena rembg_history butuh FK)
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
                CREATE TABLE IF NOT EXISTS rembg_history (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER NOT NULL REFERENCES account(id) ON DELETE CASCADE,
                    file_id VARCHAR(64) NOT NULL,
                    original_filename TEXT,
                    created_at TIMESTAMP DEFAULT NOW()
                );
            """)
            cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_rembg_history_user
                ON rembg_history (user_id, created_at DESC);
            """)
            cur.execute("SELECT pg_advisory_unlock(1001)")
            conn.commit()


ensure_history_schema()


def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def remove_background(image_pil):
    try:
        if image_pil.mode != 'RGB':
            image_pil = image_pil.convert('RGB')

        hasil = remove(
            image_pil,
            session=rembg_session,
            alpha_matting=True,
            alpha_matting_foreground_threshold=240,
            alpha_matting_background_threshold=10,
            alpha_matting_erode_size=5
        )
        return hasil
    except Exception as e:
        print(f"gagal hapus background: {e}")
        return image_pil


def _get_user_history(user_id, limit=12):
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


def _history_owner(file_id):
    """None kalau file_id ini gak tercatat di rembg_history (berarti anon/untracked -
    boleh diakses tanpa login, sama seperti perilaku sebelumnya). Kalau tercatat,
    return user_id pemiliknya - dipakai buat nge-gate akses gambar."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT user_id FROM rembg_history WHERE file_id=%s LIMIT 1", (file_id,))
            row = cur.fetchone()
    return row[0] if row else None


@app.route('/rembg', methods=['GET', 'POST'])
@app.route('/rembg/', methods=['GET', 'POST'])
def upload_file():
    if request.method == 'POST':
        if 'file' not in request.files:
            flash('No file part')
            return redirect(request.url)

        file = request.files['file']

        if file.filename == '':
            flash('No selected file')
            return redirect(request.url)

        if not allowed_file(file.filename):
            flash('File type not allowed. Please use: PNG, JPG, JPEG, GIF, WEBP')
            return redirect(request.url)

        # cek & tambah kuota SEBELUM proses berat dijalanin (sama pola kayak ocr.py)
        usage = increment_usage('rembg')
        if usage['exceeded']:
            pesan = f"Kuota hapus background habis ({usage['limit']}x/hari untuk role {usage['role']})."
            if usage['role'] == 'anon':
                pesan += " Login dulu buat kuota lebih banyak."
            flash(pesan)
            return redirect(request.url)

        try:
            image = Image.open(file.stream).convert('RGB')
            image_no_bg = remove_background(image)

            file_id = uuid.uuid4().hex

            original_path = os.path.join(UPLOAD_FOLDER, f"{file_id}_original.png")
            result_path = os.path.join(RESULT_FOLDER, f"{file_id}_result.png")

            image.save(original_path, format='PNG')
            image_no_bg.save(result_path, format='PNG')

            # simpan id cookie only, biar cookie ga kegedean
            session['file_id'] = file_id
            session['filename'] = file.filename

            # Cuma user login yang hasilnya ditrack jadi riwayat (bisa didownload lagi
            # nanti & bisa dihapus manual). Anon dibiarkan seperti semula: file tetap ada
            # di disk lewat file_id di session, tapi gak ada pencatatan kepemilikan.
            user_id = session.get('user_id')
            if user_id:
                try:
                    with get_conn() as conn:
                        with conn.cursor() as cur:
                            cur.execute(
                                """INSERT INTO rembg_history (user_id, file_id, original_filename)
                                   VALUES (%s, %s, %s)""",
                                (user_id, file_id, file.filename)
                            )
                            conn.commit()
                except Exception as e:
                    # kegagalan nyimpen riwayat jangan sampe gagalin hasil yang udah jadi
                    print(f"[rembg_history] gagal simpan riwayat: {e}")

            return redirect(url_for('upload_file'))

        except Exception as e:
            flash(f'Error processing image: {str(e)}')
            return redirect(request.url)

    file_id = session.get('file_id', None)
    filename = session.get('filename', None)

    original_img = None
    result_img = None
    if file_id:
        original_img = url_for('serve_image', kind='original', file_id=file_id)
        result_img = url_for('serve_image', kind='result', file_id=file_id)

    is_login = session.get('is_login', False)
    history = _get_user_history(session['user_id']) if is_login and session.get('user_id') else []

    return render_template('remove_bg.html',
                            original_image=original_img,
                            result_image=result_img,
                            is_login=is_login,
                            username=session.get('username'),
                            role=session.get('role', 'anon'),
                            filename=filename,
                            usage=peek_usage('rembg'),
                            history=history)


@app.route('/rembg/image/<kind>/<file_id>')
def serve_image(kind, file_id):
    folder = UPLOAD_FOLDER if kind == 'original' else RESULT_FOLDER
    suffix = '_original.png' if kind == 'original' else '_result.png'
    path = os.path.join(folder, f"{file_id}{suffix}")
    if not os.path.exists(path):
        flash('Image not found')
        return redirect(url_for('upload_file'))

    # Kalau file_id ini tercatat sebagai riwayat milik user login, cuma pemiliknya
    # sendiri (sesuai session user_id) yang boleh liat - anon/user lain gak bisa
    # buka cuma dengan nebak/nyalin URL file_id-nya. Kalau gak tercatat (anon,
    # ephemeral, belum di-history), tetap bisa diakses tanpa login seperti semula.
    owner_id = _history_owner(file_id)
    if owner_id is not None and session.get('user_id') != owner_id:
        flash('Gambar ini butuh login sebagai pemiliknya.')
        return redirect(url_for('upload_file'))

    return send_file(path, mimetype='image/png')


@app.route('/rembg/download')
def download():
    file_id = session.get('file_id', None)
    original_filename = session.get('filename', 'image')

    if file_id:
        result_path = os.path.join(RESULT_FOLDER, f"{file_id}_result.png")
        if not os.path.exists(result_path):
            flash('No image to download')
            return redirect(url_for('upload_file'))

        filename_without_ext = os.path.splitext(original_filename)[0]
        download_filename = f"{filename_without_ext}_no_bg.png"

        return send_file(
            result_path,
            mimetype='image/png',
            as_attachment=True,
            download_name=download_filename
        )
    else:
        flash('No image to download')
        return redirect(url_for('upload_file'))


@app.route('/rembg/history/download/<int:history_id>')
def download_history(history_id):
    # sama kayak /rembg/download: cuma login yang boleh, dan cuma pemilik row-nya.
    if not session.get('is_login') or not session.get('user_id'):
        flash('Login dulu untuk download hasil.')
        return redirect(url_for('upload_file'))

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT user_id, file_id, original_filename FROM rembg_history WHERE id=%s",
                (history_id,)
            )
            row = cur.fetchone()

    if not row or row[0] != session['user_id']:
        flash('Riwayat tidak ditemukan.')
        return redirect(url_for('upload_file'))

    _, file_id, original_filename = row
    result_path = os.path.join(RESULT_FOLDER, f"{file_id}_result.png")
    if not os.path.exists(result_path):
        flash('File hasil sudah tidak ada.')
        return redirect(url_for('upload_file'))

    filename_without_ext = os.path.splitext(original_filename or 'image')[0]
    return send_file(
        result_path,
        mimetype='image/png',
        as_attachment=True,
        download_name=f"{filename_without_ext}_no_bg.png"
    )


@app.route('/rembg/history/delete/<int:history_id>', methods=['POST'])
def delete_history(history_id):
    # Hapus cuma bisa dilakukan pemilik riwayatnya sendiri (dicek by user_id, bukan
    # cuma percaya history_id dari form - biar user A gak bisa hapus punya user B).
    if not session.get('is_login') or not session.get('user_id'):
        flash('Login dulu.')
        return redirect(url_for('upload_file'))

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT user_id, file_id FROM rembg_history WHERE id=%s",
                (history_id,)
            )
            row = cur.fetchone()

            if not row or row[0] != session['user_id']:
                flash('Riwayat tidak ditemukan.')
                return redirect(url_for('upload_file'))

            file_id = row[1]
            cur.execute("DELETE FROM rembg_history WHERE id=%s", (history_id,))
            conn.commit()

    for folder, suffix in [(UPLOAD_FOLDER, '_original.png'), (RESULT_FOLDER, '_result.png')]:
        path = os.path.join(folder, f"{file_id}{suffix}")
        if os.path.exists(path):
            os.remove(path)

    flash('Riwayat dihapus.')
    return redirect(url_for('upload_file'))


@app.route('/rembg/clear')
def clear():
    file_id = session.get('file_id')
    # Cuma hapus file fisik kalau sesi ini ANON. Kalau user login, file_id ini
    # udah kecatet di rembg_history - hapus di sini bakal bikin row riwayat
    # nunjuk ke file yang udah gak ada (ini penyebab "gambar hilang tak bisa
    # diakses" yang kejadian). Buat user login, delete permanen cuma boleh
    # lewat tombol Hapus di riwayat (delete_history), bukan dari "Upload Lagi".
    if file_id and not session.get('is_login'):
        for folder, suffix in [(UPLOAD_FOLDER, '_original.png'), (RESULT_FOLDER, '_result.png')]:
            path = os.path.join(folder, f"{file_id}{suffix}")
            if os.path.exists(path):
                os.remove(path)
    session.pop('file_id', None)
    session.pop('filename', None)
    return redirect(url_for('upload_file'))


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False)