from flask import Flask, render_template, request, flash, redirect, session, url_for
from paddleocr import PaddleOCR
from PIL import Image
import numpy as np
import cv2
import os
import socket
from session_config import init_shared_session
from usage_limit import peek_usage, increment_usage

# --- BIKIN PADDLEPADDLE JADI RAMAH CPU SERVER ---
os.environ["FLAGS_use_mkldnn"] = "0"
os.environ["FLAGS_enable_pir_api"] = "0"

app = Flask(__name__)
init_shared_session(app)
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024

# nyala cuma kalau di-set eksplisit di env, biar ga ke-expose default di prod
SHOW_DEBUG_INFO = os.getenv("SHOW_DEBUG_INFO", "false").lower() == "true"
WORKER_ID = socket.gethostname()

ocr_engine = PaddleOCR(
    text_detection_model_name='PP-OCRv6_small_det',
    text_recognition_model_name='PP-OCRv6_small_rec',
    use_doc_orientation_classify=False,
    use_doc_unwarping=False,
    use_textline_orientation=False,
    device='cpu',
    enable_mkldnn=False, # Untuk older cpu
)


def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def run_ocr(image_np_rgb, std_dev):
    if std_dev > 50:
        processed_img = cv2.cvtColor(image_np_rgb, cv2.COLOR_RGB2BGR)
    else:
        gray = cv2.cvtColor(image_np_rgb, cv2.COLOR_RGB2GRAY)
        resized = cv2.resize(gray, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
        _, thresh_img = cv2.threshold(resized, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        processed_img = cv2.cvtColor(thresh_img, cv2.COLOR_GRAY2BGR)

    results = ocr_engine.predict(processed_img)
    texts = []
    for res in results:
        rec_texts = res.get('rec_texts', []) if hasattr(res, 'get') else res['rec_texts']
        texts.extend(rec_texts)
    return " ".join(texts)


@app.route('/ocr/', methods=['GET', 'POST'])
def upload_file():
    if request.method == 'POST':
        if 'file' not in request.files or request.files['file'].filename == '':
            flash('Pilih gambar dulu sebelum scan.')
            return redirect(request.url)

        file = request.files['file']
        if not allowed_file(file.filename):
            flash('File type not allowed. Please use: PNG, JPG, JPEG, GIF')
            return redirect(request.url)

        # cek & tambah kuota SEBELUM proses berat dijalanin
        usage = increment_usage('ocr')
        if usage['exceeded']:
            pesan = f"Kuota OCR habis ({usage['limit']}x/hari untuk role {usage['role']})."
            if usage['role'] == 'anon':
                pesan += " Login dulu buat kuota lebih banyak."
            flash(pesan)
            return redirect(request.url)

        try:
            image = Image.open(file.stream).convert('RGB')
            image_np = np.array(image)
            gray_check = cv2.cvtColor(image_np, cv2.COLOR_RGB2GRAY)
            std_dev = gray_check.std()

            text = run_ocr(image_np, std_dev)
            if not text.strip():
                flash('Nggak ada teks yang berhasil dideteksi dari gambar ini. Coba gambar dengan kontras lebih jelas.')

            session['ocr_result'] = text

        except Exception as e:
            flash(f'Error memproses gambar: {str(e)}')
            return redirect(request.url)

        return redirect(url_for('upload_file'))

    result_text = session.pop('ocr_result', None)
    usage = peek_usage('ocr')

    resp = app.make_response(render_template(
        'ocr.html',
        result=result_text,
        usage=usage,
        is_login=session.get('is_login', False),
        username=session.get('username'),
        role=session.get('role', 'anon'),
        worker_id=WORKER_ID if SHOW_DEBUG_INFO else None,
    ))
    if SHOW_DEBUG_INFO:
        resp.headers['X-Worker-Id'] = WORKER_ID
    return resp


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5002, debug=False)